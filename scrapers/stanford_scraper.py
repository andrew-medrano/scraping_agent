import os
import json
import asyncio
import requests
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import urljoin
from tqdm import tqdm

from playwright.async_api import async_playwright, Page, Browser
from openai import OpenAI

# Configuration
@dataclass
class ScraperConfig:
    relative_links: bool = True # FILL THIS OUT: True if the links are relative, False if they are absolute
    jina_api_url: str = 'https://r.jina.ai/'
    jina_api_key: str = os.getenv('JINA_API_KEY')
    deepseek_api_key: str = os.getenv('DEEPSEEK_API_KEY')
    deepseek_base_url: str = os.getenv('DEEPSEEK_BASE_URL')
    selectors = {
        'item_links': ".view__item .teaser__title > a",      # FILL THIS OUT: This is the selector for the items on the page
        'next_button': ".pager__item--next > .pager__link"   # FILL THIS OUT: This is the selector for the next button on the page
    }
    jina_remove_selectors = '.node__sidebar, #similar-technologies, #footer, .su-masthead, .su-global-footer' # FILL THIS OUT: This is the selector for the elements to remove from the page

class ContentExtractor:
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.client = OpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url
        )

    async def get_markdown_content(self, url: str) -> str:
        """Converts webpage content to markdown using Jina API."""
        url = f"{self.config.jina_api_url}{url}"
        headers = {
            'Authorization': f'Bearer {self.config.jina_api_key}',
            'X-Remove-Selector': self.config.jina_remove_selectors,
            'X-Return-Format': 'markdown'
        }
        response = requests.get(url, headers=headers)
        return response.text

    async def extract_info(self, markdown_content: str) -> Dict[str, str]:
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

class TechTransferScraper:
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.extractor = ContentExtractor(config)

    def _should_stop_scraping(self, ip_number: str) -> bool:  # FILL THIS OUT: This is the function that checks if we should stop scraping based on the IP number
        """Check if we should stop scraping based on IP number."""
        if not ip_number or not ip_number.startswith('S'):
            return False
        try:
            # Extract the number after 'S'
            num = int(ip_number[1:])
            return num <= 17
        except ValueError:
            return False

    async def _process_detail_page(self, browser: Browser, detail_url: str) -> Dict[str, Optional[str]]:
        """Process a single detail page and extract its information."""
        detail_page = await browser.new_page()
        await detail_page.goto(detail_url)
        
        markdown_content = await self.extractor.get_markdown_content(detail_url)
        extracted_data = await self.extractor.extract_info(markdown_content)
        extracted_data["page_url"] = detail_url
        
        await detail_page.close()
        return extracted_data

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
                
                for item in tqdm(items, desc=f"Page {page_count} items"):
                    if should_stop:
                        break
                        
                    detail_url = await item.get_attribute("href")
                    if self.config.relative_links:
                        detail_url = urljoin(page.url, detail_url)
                    print(f"\nProcessing item: {detail_url}")

                    extracted_data = await self._process_detail_page(browser, detail_url)
                    
                    # Check if we should stop based on IP number
                    if self._should_stop_scraping(extracted_data.get("ip_number")):
                        print(f"\nFound IP number {extracted_data['ip_number']} <= S17. Stopping scrape.")
                        should_stop = True
                        break
                        
                    results.append(extracted_data)
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