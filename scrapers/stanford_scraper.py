import os
import json
import asyncio
import aiohttp
import requests
from pathlib import Path
from urllib.parse import urljoin
from tqdm import tqdm
from openai import AsyncOpenAI

from playwright.async_api import async_playwright


# Optionally, set your OpenAI API key in an environment variable before running:
RELATIVE_LINKS = True
MAX_CONCURRENT_REQUESTS = 5  # Limit concurrent API calls

# Add Jina API configuration
JINA_API_URL = 'https://r.jina.ai/'
JINA_API_KEY = os.getenv('JINA_API_KEY')

# Create semaphores for API rate limiting
jina_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Create async OpenAI client
async_client = AsyncOpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url=os.getenv('DEEPSEEK_BASE_URL'))

async def get_markdown_content(session: aiohttp.ClientSession, url: str) -> str:
    """
    Uses Jina API to convert webpage content to markdown.
    """
    async with jina_semaphore:
        jina_url = f"{JINA_API_URL}{url}"
        headers = {
            'Authorization': f'Bearer {JINA_API_KEY}',
            'X-Remove-Selector': '.node__sidebar, #similar-technologies, #footer, .su-masthead, .su-global-footer',
            'X-Return-Format': 'markdown'
        }

        async with session.get(jina_url, headers=headers) as response:
            return await response.text()

async def extract_info_with_llm(markdown_content: str) -> dict:
    """
    Sends markdown content to LLM for extraction.
    """
    async with llm_semaphore:
        system_prompt = f"""
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
          {{
            "ip_name": "...",
            "ip_number": "...",
            "published_date": "...",
            "ip_description": "...",
            "patents": "..."
          }}
        """

        user_prompt = f"""
        Markdown content:
        {markdown_content}
        """

        response = await async_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0
        )
        message_content = response.choices[0].message.content.strip()
        
        try:
            # Strip markdown code block if present
            if message_content.startswith("```"):
                # Remove first line (```json) and last line (```)
                message_content = "\n".join(message_content.split("\n")[1:-1])
            
            data = json.loads(message_content)
        except json.JSONDecodeError as e:
            print(f"\nERROR: Failed to parse LLM response as JSON: {str(e)}")
            # In case of LLM not returning valid JSON, fallback
            data = {
                "ip_name": "",
                "ip_number": "",
                "published_date": "",
                "ip_description": "",
                "patents": ""
            }
        return data

def save_results(results: list, university: str) -> None:
    """
    Saves the scraped results to a JSON file in the data/raw directory.
    Creates the directory if it doesn't exist.
    """
    # Create data/raw directory if it doesn't exist
    save_dir = Path('data/raw')
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Create the file path
    file_path = save_dir / f'{university}_raw.json'
    
    # Save the results
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

async def process_item(session: aiohttp.ClientSession, detail_url: str) -> dict:
    """Process a single item with markdown conversion and LLM extraction"""
    try:
        # Get markdown content
        print(f"Getting markdown content from {detail_url}")
        markdown_content = await get_markdown_content(session, detail_url)

        # Extract data with LLM
        print("Extracting data with LLM")
        extracted_data = await extract_info_with_llm(markdown_content)
        
        # Add the page_url to the record
        extracted_data["page_url"] = detail_url
        
        return extracted_data
    except Exception as e:
        print(f"Error processing {detail_url}: {e}")
        return None

async def process_batch(session: aiohttp.ClientSession, items: list, page_url: str) -> list:
    """Process a batch of items concurrently"""
    tasks = []
    for item in items:
        detail_url = await item.get_attribute("href")
        if RELATIVE_LINKS:
            detail_url = urljoin(page_url, detail_url)
        tasks.append(process_item(session, detail_url))
    
    return await asyncio.gather(*tasks)

async def scrape_tech_transfer_site(start_url: str, university: str) -> list:
    """
    Scrapes a tech transfer site starting at `start_url`.
    
    Args:
        start_url: URL to start scraping from
        university: Name of the university for saving results
    """
    results = []
    page_count = 0

    print(f"\nStarting scrape of {university} tech transfer site: {start_url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Create aiohttp session for concurrent requests
        async with aiohttp.ClientSession() as session:
            print("Navigating to start URL...")
            await page.goto(start_url)

            while True:
                page_count += 1
                print(f"\nProcessing page {page_count}...")
                
                # 1. Select all "items" on the page
                items = await page.query_selector_all(".view__item .teaser__title > a")
                print(f"Found {len(items)} items on current page")
                
                # Process items in batches
                BATCH_SIZE = 5
                for i in range(0, len(items), BATCH_SIZE):
                    batch = items[i:i + BATCH_SIZE]
                    print(f"\nProcessing batch {i//BATCH_SIZE + 1} of {len(items)//BATCH_SIZE + 1}")
                    
                    batch_results = await process_batch(session, batch, page.url)
                    # Filter out None results from failed processing
                    valid_results = [r for r in batch_results if r is not None]
                    results.extend(valid_results)
                    
                    # Save results after every batch
                    save_results(results, university)

                # Check for next page
                next_button = await page.query_selector(".pager__item--next > .pager__link")
                if next_button:
                    print("\nMoving to next page...")
                    await next_button.click()
                    await page.wait_for_load_state("networkidle")
                else:
                    print("\nNo more pages to process")
                    break

            await browser.close()
    
    print(f"\nScraping complete! Total items processed: {len(results)}")
    # Final save of results
    save_results(results, university)
    return results


def main():
    start_url = "https://techfinder.stanford.edu/"
    university = "stanford"

    # Run the scrape
    all_data = asyncio.run(scrape_tech_transfer_site(start_url, university))

    # Here we have a list of dictionaries that look like:
    # {
    #   "ip_name": "...",
    #   "ip_number": "...",
    #   "published_date": "...",
    #   "ip_description": "...",
    #   "patents": "...",
    #   "page_url": "...",
    # }
    # Print as JSON
    print(json.dumps(all_data, indent=2))


if __name__ == "__main__":
    main()