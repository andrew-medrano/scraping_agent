import os
import json
import asyncio
import requests
import warnings
import multiprocessing
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import urljoin
from tqdm import tqdm
from functools import partial

# Suppress the specific urllib3 NotOpenSSLWarning
import urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.NotOpenSSLWarning)

from playwright.async_api import async_playwright, Page, Browser
from openai import OpenAI

# Configuration
@dataclass
class ScraperConfig:
    relative_links: bool = True
    jina_api_url: str = 'https://r.jina.ai/'
    jina_api_key: str = os.getenv('JINA_API_KEY')
    deepseek_api_key: str = os.getenv('DEEPSEEK_API_KEY')
    deepseek_base_url: str = os.getenv('DEEPSEEK_BASE_URL')
    selectors = {
        'item_links': ".view__item .teaser__title > a",
        'next_button': ".pager__item--next > .pager__link"
    }
    jina_remove_selectors = '.node__sidebar, #similar-technologies, #footer, .su-masthead, .su-global-footer'

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
            'X-Return-Format': 'markdown'
        }
        response = requests.get(url, headers=headers)
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
          - patents (string, comma-separated if multiple) <this is the patents associated with the technology>
        
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

    def _should_stop_scraping(self, ip_number: str) -> bool:
        """Check if we should stop scraping based on IP number."""
        if not ip_number or not ip_number.startswith('S'):
            return False
        try:
            num = int(ip_number[1:])
            return num <= 17
        except ValueError:
            return False

    def _save_results(self, results: List[Dict[str, str]], university: str) -> None:
        """Saves scraped results to a JSON file."""
        save_dir = Path('data/raw')
        save_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = save_dir / f'{university}_raw.json'
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)

    async def scrape(self, start_url: str, university: str) -> List[Dict[str, str]]:
        """Main scraping function for tech transfer site."""
        results = []
        page_count = 0
        should_stop = False

        print(f"\nStarting scrape of {university} tech transfer site: {start_url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(start_url)

            while True and not should_stop:
                page_count += 1
                print(f"\nProcessing page {page_count}...")
                
                items = await page.query_selector_all(self.config.selectors['item_links'])
                print(f"Found {len(items)} items on current page")
                
                # Collect all detail URLs from the current page
                detail_urls = []
                for item in items:
                    detail_url = await item.get_attribute("href")
                    if self.config.relative_links:
                        detail_url = urljoin(page.url, detail_url)
                    detail_urls.append(detail_url)

                # Process detail pages in parallel
                num_processes = max(1, multiprocessing.cpu_count() // 2)
                with multiprocessing.Pool(num_processes) as pool:
                    process_func = partial(process_detail_page, config=self.config)
                    page_results = list(tqdm(
                        pool.imap(process_func, detail_urls),
                        total=len(detail_urls),
                        desc=f"Processing page {page_count} items"
                    ))

                # Check results and update stop condition
                for result in page_results:
                    if self._should_stop_scraping(result.get("ip_number")):
                        print(f"\nFound IP number {result['ip_number']} <= S17. Stopping scrape.")
                        should_stop = True
                        break
                    results.append(result)

                # Save intermediate results
                self._save_results(results, university)

                if should_stop:
                    break

                next_button = await page.query_selector(self.config.selectors['next_button'])
                if next_button:
                    print("\nMoving to next page...")
                    await next_button.click()
                    await page.wait_for_load_state("networkidle")
                else:
                    print("\nNo more pages to process")
                    break

            await browser.close()
        
        print(f"\nScraping complete! Total items processed: {len(results)}")
        self._save_results(results, university)
        return results

def main():
    config = ScraperConfig()
    scraper = TechTransferScraper(config)
    
    start_url = "https://techfinder.stanford.edu/"
    university = "stanford"

    all_data = asyncio.run(scraper.scrape(start_url, university))
    print(json.dumps(all_data, indent=2))

if __name__ == "__main__":
    main()
