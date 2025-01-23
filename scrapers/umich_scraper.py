import os
import json
import asyncio
import requests
import warnings
import multiprocessing
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from urllib.parse import urljoin
from tqdm import tqdm
from functools import partial
from concurrent.futures import ProcessPoolExecutor

from playwright.async_api import async_playwright, Page, Browser
from openai import OpenAI

# Configuration
@dataclass
class ScraperConfig:
    start_urls: List[str] = field(default_factory=lambda: [
        "https://available-inventions.umich.edu/products/life-sciences/list",
        "https://available-inventions.umich.edu/products/engineering-and-physical-sciences/list",
        "https://available-inventions.umich.edu/products/research-tools-and-reagents/list",
        "https://available-inventions.umich.edu/products/hardware/list",
        "https://available-inventions.umich.edu/products/therapeutics/list",
        "https://available-inventions.umich.edu/products/content/list",
        "https://available-inventions.umich.edu/products/diagnostics/list",
        "https://available-inventions.umich.edu/products/medical-devices/list"
    ])
    university: str = "umich"  # FILL THIS OUT: This is the name of the university
    relative_links: bool = True
    max_pages: int = 0  # 0 means no limit, positive number limits the number of pages to scrape
    max_results: int = 0  # 0 means no limit, positive number limits the number of results to scrape
    debug: bool = False  # Enable verbose debug output
    parallel: bool = True  # Enable parallel processing of detail pages
    jina_api_url: str = 'https://r.jina.ai/'
    jina_api_key: str = os.getenv('JINA_API_KEY')
    deepseek_api_key: str = os.getenv('DEEPSEEK_API_KEY')
    deepseek_base_url: str = os.getenv('DEEPSEEK_BASE_URL')
    selectors = {
        'item_links': ".section",
        'next_button': ""  # there is no next button
    }
    jina_remove_selectors = ''
    jina_target_selectors = '#product-detail'

class ContentExtractor:
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.client = OpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url
        )

    def get_markdown_content(self, url: str) -> str:
        """Converts webpage content to markdown using Jina API."""
        url = f"{self.config.jina_api_url}{url}"
        headers = {
            'Authorization': f'Bearer {self.config.jina_api_key}',
            'X-Remove-Selector': self.config.jina_remove_selectors,
            'X-Target-Selector': self.config.jina_target_selectors,
            'X-Return-Format': 'markdown'
        }
        if self.config.debug:
            print(f"\nDebug: Fetching markdown from URL: {url}")
            print(f"Debug: Using headers: {headers}")
            
        response = requests.get(url, headers=headers)
        
        if self.config.debug:
            print("\nDebug: Received markdown content:")
            print("----------------------------------------")
            print(response.text)
            print("----------------------------------------")
            
        return response.text

    def extract_info(self, markdown_content: str) -> Dict[str, str]:
        """Extracts structured information from markdown content using LLM."""
        system_prompt = """
        You are a data extraction assistant.
        Extract the following fields from the content below, if they exist. Leave them blank if they don't exist. Copy text word for word:
          - ip_name (string) <this is the title of the technology>
          - ip_number (string) <this is the number of the technology>
          - published_date (string) <this is the date the technology was published>
          - ip_description (string) <this is the description of the technology, includes details, applications, advantages, and any other relevant information>
          - patents (string, comma-separated if multiple) <this is the patents associated with the technology, can include applications, titles, and any other relevant information>
        
        Fill out the ip_description field with as much detail as possible. Whole paragraphs and sentences should be copied directly if they are relevant. 
        If there is a list that is relevant to the description, copy it directly. 
        Return your answer as valid JSON with keys:
          {
            "ip_name": "...",
            "ip_number": "...",
            "published_date": "...",
            "ip_description": "...",
            "patents": "..."
          }
        """

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Markdown content:\n{markdown_content}"}
            ],
            temperature=0
        )
        
        if self.config.debug:
            print("\nDebug: Received LLM response:")
            print("----------------------------------------")
            print(response.choices[0].message.content)
            print("----------------------------------------")
        
        return self._parse_llm_response(response.choices[0].message.content.strip())

    def _parse_llm_response(self, content: str) -> Dict[str, str]:
        """Parses LLM response and handles potential JSON errors."""
        try:
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:-1])
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"\nERROR: Failed to parse LLM response as JSON: {str(e)}")
            return {
                "ip_name": "",
                "ip_number": "",
                "published_date": "",
                "ip_description": "",
                "patents": ""
            }

def process_detail_page(detail_url: str, config: ScraperConfig) -> Dict[str, Optional[str]]:
    """Process a single detail page and extract its information."""
    if config.debug:
        print(f"\nDebug: Processing detail page: {detail_url}")
        
    extractor = ContentExtractor(config)
    try:
        markdown_content = extractor.get_markdown_content(detail_url)
        extracted_data = extractor.extract_info(markdown_content)
        extracted_data["page_url"] = detail_url
        return extracted_data
    except Exception as e:
        print(f"\nError processing {detail_url}: {str(e)}")
        return {
            "ip_name": "",
            "ip_number": "",
            "published_date": "",
            "ip_description": "",
            "patents": "",
            "page_url": detail_url
        }

class TechTransferScraper:
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.extractor = ContentExtractor(config)
        self.num_pages = 0
        self.num_results = 0

    def _should_stop_scraping(self, ip_number: str) -> bool:
        """Check if we should stop scraping based on IP number."""
        if self.config.max_results > 0 and self.num_results >= self.config.max_results:
            print(f"\nReached maximum result limit of {self.config.max_results}")
            return True
        elif self.config.max_pages > 0 and self.num_pages >= self.config.max_pages:
            print(f"\nReached maximum page limit of {self.config.max_pages}")
            return True
        return False

    def _save_results(self, results: List[Dict[str, str]], university: str) -> None:
        """Saves scraped results to a JSON file."""
        save_dir = Path('data/raw')
        save_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = save_dir / f'{university}_raw.json'
        
        # Load existing results if file exists
        existing_results = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_results = json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not load existing results from {file_path}")
        
        # Combine existing and new results, removing duplicates based on page_url
        seen_urls = {r.get('page_url'): i for i, r in enumerate(existing_results)}
        for result in results:
            url = result.get('page_url')
            if url in seen_urls:
                # Update existing entry
                existing_results[seen_urls[url]] = result
            else:
                # Add new entry
                existing_results.append(result)
                seen_urls[url] = len(existing_results) - 1
        
        # Save combined results
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(existing_results, f, indent=2)

    async def scrape(self, start_url: str, university: str) -> List[Dict[str, str]]:
        """Main scraping function for tech transfer site."""
        results = []
        page_count = 0
        should_stop = False

        # Load existing results to determine where to resume from
        save_dir = Path('data/raw')
        file_path = save_dir / f'{university}_raw.json'
        processed_urls = set()
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_results = json.load(f)
                    processed_urls = {r.get('page_url') for r in existing_results if r.get('page_url')}
                    print(f"\nFound {len(processed_urls)} already processed URLs")
            except json.JSONDecodeError:
                print(f"Warning: Could not load existing results from {file_path}")

        print(f"\nStarting scrape of {university} tech transfer site: {start_url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(start_url)

            # Since all results are on one page, we only need one iteration
            page_count += 1
            print(f"\nProcessing page {page_count}...")
            
            items = await page.query_selector_all(self.config.selectors['item_links'])
            print(f"Found {len(items)} items on current page")
            
            # Calculate how many more items we can process
            remaining_slots = self.config.max_results - self.num_results if self.config.max_results > 0 else len(items)
            if remaining_slots <= 0:
                print(f"\nReached maximum result limit of {self.config.max_results}")
                await browser.close()
                return results

            # Collect URLs up to the remaining slots limit
            detail_urls = []
            for item in items[:remaining_slots]:
                detail_url = await item.get_attribute("href")
                if self.config.relative_links:
                    detail_url = urljoin(page.url, detail_url)
                # Skip already processed URLs
                if detail_url in processed_urls:
                    print(f"Skipping already processed URL: {detail_url}")
                    continue
                detail_urls.append(detail_url)

            if not detail_urls:
                print("No new URLs to process")
                await browser.close()
                return results

            print(f"Processing {len(detail_urls)} new items (max_results limit: {self.config.max_results})")

            # Process detail pages (parallel or sequential)
            if self.config.parallel:
                # Process detail pages in parallel using ProcessPoolExecutor
                with ProcessPoolExecutor() as executor:
                    futures = [
                        executor.submit(process_detail_page, url, self.config)
                        for url in detail_urls
                    ]
                    page_results = []
                    for f in tqdm(futures, total=len(futures), desc=f"Processing page {page_count} items"):
                        try:
                            result = f.result()
                            page_results.append(result)
                        except Exception as e:
                            print(f"Error processing result: {str(e)}")
                            continue
            else:
                # Process detail pages sequentially
                page_results = []
                for detail_url in tqdm(detail_urls, desc=f"Processing page {page_count} items"):
                    if should_stop:
                        break
                    try:
                        result = process_detail_page(detail_url, self.config)
                        page_results.append(result)
                    except Exception as e:
                        print(f"Error processing {detail_url}: {str(e)}")
                        continue

            # Add results and check stop condition
            for result in page_results:
                results.append(result)
                self.num_results += 1
                if self._should_stop_scraping(result.get("ip_number")):
                    print(f"\nReached stop condition with IP number {result.get('ip_number')}.")
                    should_stop = True
                    break

            # Save intermediate results
            self._save_results(results, university)

            await browser.close()
        
        print(f"\nScraping complete! Total items processed: {len(results)}")
        self._save_results(results, university)
        return results

def main():
    config = ScraperConfig()
    scraper = TechTransferScraper(config)

    all_data = []
    for start_url in config.start_urls:
        print(f"\nProcessing start URL: {start_url}")
        data = asyncio.run(scraper.scrape(start_url, config.university))
        all_data.extend(data)
    
    print(f"Scraped {len(all_data)} total items from {config.university} tech transfer site")

if __name__ == "__main__":
    main() 