import os
import json
import asyncio
import requests
import warnings

# Suppress all urllib3 warnings
warnings.filterwarnings('ignore', category=Warning)
# Extra specific suppressions just in case
warnings.filterwarnings('ignore', message='.*OpenSSL.*')
warnings.filterwarnings('ignore', message='.*urllib3.*')

import multiprocessing
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import urljoin
from tqdm import tqdm
from functools import partial

from playwright.async_api import async_playwright, Page, Browser
from openai import OpenAI

# Configuration
@dataclass
class ScraperConfig:
    start_url: str = "https://puotl.technologypublisher.com/searchresults.aspx?q=&page=0&sort=datecreated&order=desc" # FILL THIS OUT: This is the start URL for the MIT tech transfer site
    university: str = "princeton" # FILL THIS OUT: This is the name of the university
    relative_links: bool = True
    max_pages: int = 40  # 0 means no limit, positive number limits the number of pages to scrape
    max_results: int = 0  # 0 means no limit, positive number limits the number of results to scrape
    debug: bool = False  # Enable verbose debug output
    parallel: bool = True  # Enable parallel processing of detail pages
    jina_api_url: str = 'https://r.jina.ai/'
    jina_api_key: str = os.getenv('JINA_API_KEY')
    deepseek_api_key: str = os.getenv('DEEPSEEK_API_KEY')
    deepseek_base_url: str = os.getenv('DEEPSEEK_BASE_URL')
    selectors = {
        'item_links': ".row h3 > a",
        'next_button': "" # not used, there is no button pagination
    }
    jina_remove_selectors = ''
    jina_target_selectors = '#content'

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
    """Process a single detail page and extract its information. Used for parallel processing."""
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
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)

    async def _process_detail_page(self, browser: Browser, detail_url: str) -> Dict[str, Optional[str]]:
        """Process a single detail page and extract its information."""
        if self.config.debug:
            print(f"\nDebug: Processing detail page: {detail_url}")
            
        try:
            markdown_content = self.extractor.get_markdown_content(detail_url)
            extracted_data = self.extractor.extract_info(markdown_content)
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

    async def scrape(self, start_url: str, university: str) -> List[Dict[str, str]]:
        """Main scraping function for tech transfer site."""
        results = []
        page_count = 0
        should_stop = False

        print(f"\nStarting scrape of {university} tech transfer site: {start_url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            while True and not should_stop:
                # Construct URL for current page
                current_url = start_url.replace("page=0", f"page={page_count}")
                print(f"\nProcessing page {page_count}, URL: {current_url}")
                
                await page.goto(current_url)
                await page.wait_for_load_state("networkidle")
                
                items = await page.query_selector_all(self.config.selectors['item_links'])
                print(f"Found {len(items)} items on current page")
                
                # If no items found, we've reached the end of pagination
                if not items:
                    print("\nNo more items found, ending pagination")
                    break

                # Collect all detail URLs from the current page
                detail_urls = []
                for item in items:
                    # Check if we've hit the max results before adding more URLs
                    if self.config.max_results > 0 and len(results) >= self.config.max_results:
                        should_stop = True
                        break
                        
                    detail_url = await item.get_attribute("href")
                    if self.config.relative_links:
                        detail_url = urljoin(page.url, detail_url)
                    detail_urls.append(detail_url)

                if should_stop:
                    break

                # Process detail pages (parallel or sequential)
                if self.config.parallel:
                    # Process detail pages in parallel
                    num_processes = max(1, multiprocessing.cpu_count() // 2)
                    with multiprocessing.Pool(num_processes) as pool:
                        process_func = partial(process_detail_page, config=self.config)
                        page_results = list(tqdm(
                            pool.imap(process_func, detail_urls),
                            total=len(detail_urls),
                            desc=f"Processing page {page_count} items"
                        ))
                        # Add the results to our main results list
                        results.extend(page_results)
                        self.num_results += len(page_results)
                else:
                    # Process detail pages sequentially
                    page_results = []
                    remaining_slots = self.config.max_results - len(results) if self.config.max_results > 0 else len(detail_urls)
                    urls_to_process = detail_urls[:remaining_slots]  # Only process up to remaining slots
                    
                    for detail_url in tqdm(urls_to_process, desc=f"Processing page {page_count} items"):
                        extracted_data = await self._process_detail_page(browser, detail_url)
                        page_results.append(extracted_data)
                        results.append(extracted_data)
                        self.num_results += 1

                # Save intermediate results
                self._save_results(results, university)

                self.num_pages += 1
                if len(results) >= self.config.max_results and self.config.max_results > 0:
                    print(f"\nReached maximum result limit of {self.config.max_results}")
                    break

                page_count += 1

            await browser.close()
        
        print(f"\nScraping complete! Total items processed: {len(results)}")
        self._save_results(results, university)
        return results

def main():
    config = ScraperConfig()
    scraper = TechTransferScraper(config)

    all_data = asyncio.run(scraper.scrape(config.start_url, config.university))
    print(f"Scraped {len(all_data)} items from {config.university} tech transfer site")

if __name__ == "__main__":
    main() 