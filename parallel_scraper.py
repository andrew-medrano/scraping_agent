import os
import asyncio
import agentql
from playwright.async_api import async_playwright
from pyairtable import Api
from dotenv import load_dotenv
import json
import logging
from typing import List, Dict

load_dotenv()
os.environ["AGENTQL_API_KEY"] = os.getenv("AGENTQL_API_KEY")

INITIAL_URL = "https://cmu.flintbox.com/technologies"
MAX_CONCURRENT_SCRAPES = 3  # Adjust based on your needs

LIST_BUTTON_QUERY = """
{
    list_button(element to turn results into list view)
}
"""

LIST_PAGE_QUERY = """
{
    ip_result(box showing title, number, and description)[]
    next_page_button(element to go to next page of results)
}
"""

RESULT_PAGE_QUERY = """
{
    ip_name(text that follows the ip number, at the top of the page)
    ip_number(number to the left of the title, at the top of the page)
    published_date
    ip_link(link to each result page)
    ip_description(details, benefits, applications, advantages, etc.)
    patents(IP numbers, at the bottom of the page)
}
"""

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def save_results(results, filename='tech_transfer_results.json'):
    """Save results to JSON file"""
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)

async def scrape_detail_page(context, url: str) -> Dict:
    """Scrape a single detail page"""
    page = await context.new_page()
    try:
        # Await the async wrapper
        wrapped_page = await agentql.wrap_async(page)
        await wrapped_page.goto(url)
        await wrapped_page.wait_for_load_state('networkidle')
        
        result = await wrapped_page.query_data(RESULT_PAGE_QUERY)
        logger.debug(f"Successfully scraped: {result.get('ip_name', 'Unknown')}")
        
        return result
    finally:
        await page.close()

async def get_all_detail_urls(page) -> List[str]:
    """Get all detail page URLs from all pages"""
    urls = []
    # Await the async wrapper
    wrapped_page = await agentql.wrap_async(page)
    
    while True:
        logger.debug("Querying for IP results on current page...")
        response = await wrapped_page.query_elements(LIST_PAGE_QUERY)
        await wrapped_page.wait_for_load_state('networkidle')
        
        # Get URLs from current page
        for result in response.ip_result:
            try:
                await result.click()
                await wrapped_page.wait_for_load_state('networkidle')
                urls.append(wrapped_page.url)
                await wrapped_page.go_back()
                await wrapped_page.wait_for_load_state('networkidle')
            except Exception as e:
                logger.error(f"Error getting URL: {str(e)}")
                continue
        
        # Check for next page
        try:
            next_button = response.next_page_button
            if not next_button:
                break
            await next_button.click()
            await wrapped_page.wait_for_load_state('networkidle')
        except Exception as e:
            logger.error(f"Error navigating to next page: {str(e)}")
            break
    
    return urls

async def main():
    results = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        
        # Get initial page and switch to list view
        page = await context.new_page()
        # Await the async wrapper
        wrapped_page = await agentql.wrap_async(page)
        
        await wrapped_page.goto(INITIAL_URL)
        await wrapped_page.wait_for_load_state('networkidle')
        
        response = await wrapped_page.query_elements(LIST_BUTTON_QUERY)
        list_button = response.list_button
        await list_button.click()
        await wrapped_page.wait_for_load_state('networkidle')
        
        # Get all detail page URLs first
        detail_urls = await get_all_detail_urls(page)
        await page.close()
        
        logger.info(f"Found {len(detail_urls)} pages to scrape")
        
        # Create semaphore to limit concurrent scrapes
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)
        
        async def scrape_with_semaphore(url):
            async with semaphore:
                return await scrape_detail_page(context, url)
        
        # Scrape all pages in parallel
        tasks = [scrape_with_semaphore(url) for url in detail_urls]
        scraped_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and add successful results
        for result in scraped_results:
            if isinstance(result, Exception):
                logger.error(f"Error during scraping: {str(result)}")
            else:
                results.append(result)
                await save_results(results)
        
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())