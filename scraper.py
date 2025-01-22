import os
import agentql
from playwright.sync_api import sync_playwright
from pyairtable import Api
from dotenv import load_dotenv
import json
import logging

# Load environment variables
load_dotenv()
os.environ["AGENTQL_API_KEY"] = os.getenv("AGENTQL_API_KEY")

# Constants
INITIAL_URL = "https://cmu.flintbox.com/technologies"

# AgentQL Queries
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
    ip_description(details, benefits, applications, advantages, etc.)
    patents(IP numbers, at the bottom of the page)
}
"""

# Setup logging - suppress most logs
logging.basicConfig(level=logging.ERROR)
# Suppress specific loggers
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('agentql').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

def save_results(results, filename='tech_transfer_results.json'):
    """Save results to JSON file"""
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)

def initialize_page(browser):
    """Initialize and return a wrapped browser page"""
    page = agentql.wrap(browser.new_page())
    page.goto(INITIAL_URL)
    page.wait_for_load_state('networkidle')
    return page

def switch_to_list_view(page):
    """Switch the page view to list format"""
    response = page.query_elements(LIST_BUTTON_QUERY)
    list_button = response.list_button
    list_button.click()
    page.wait_for_load_state('networkidle')

def process_single_result(page, current_result, index, total_results):
    """Process a single IP result and return the data"""
    current_result.click()
    page.wait_for_load_state('networkidle')
    
    result_data = page.query_data(RESULT_PAGE_QUERY)
    result_data['page_url'] = page.url
    
    print(f"Processed result {index + 1}/{total_results}: {result_data.get('ip_name', 'Unknown Title')}")
    
    page.go_back()
    page.wait_for_load_state('networkidle')
    
    return result_data

def get_next_page_button(page):
    """Get the next page button"""
    response = page.query_elements(LIST_PAGE_QUERY)
    return response.next_page_button

def process_page_results(page):
    """Process all results on the current page"""
    results = []
    response = page.query_elements(LIST_PAGE_QUERY)
    page.wait_for_load_state('networkidle')
    
    ip_results = response.ip_result
    total_results = len(ip_results)
    print(f"\nProcessing page with {total_results} results...")

    for index in range(total_results):
        try:
            # Re-query the elements to get fresh reference
            response = page.query_elements(LIST_PAGE_QUERY)
            current_result = response.ip_result[index]
            
            result_data = process_single_result(page, current_result, index, total_results)
            results.append(result_data)
            
        except Exception as e:
            print(f"Error processing result {index + 1}: {str(e)}")
            page.screenshot(path=f"error_screenshot_{index}.png")
            continue
    
    return results, response.next_page_button

def scrape_tech_transfer(max_pages=3):
    """Main function to scrape the tech transfer website"""
    print(f"Starting scraping (max {max_pages} pages)...")
    
    with sync_playwright() as playwright, playwright.chromium.launch(headless=False) as browser:
        page = initialize_page(browser)
        all_results = []
        
        # Switch to list view
        switch_to_list_view(page)
        
        # Process all pages
        pages_scraped = 0
        while True:
            try:
                pages_scraped += 1
                print(f"\n=== Processing Page {pages_scraped}/{max_pages} ===")
                
                page_results, next_button = process_page_results(page)
                all_results.extend(page_results)
                save_results(all_results)
                print(f"Saved {len(all_results)} total results so far")
                
                next_button = get_next_page_button(page)
                if not next_button or pages_scraped >= max_pages:
                    break
                    
                next_button.click()
                page.wait_for_load_state('networkidle')
                
            except Exception as e:
                print(f"Error navigating to next page: {str(e)}")
                break
    
    print(f"\nScraping completed. Total results: {len(all_results)}")
    return all_results

if __name__ == "__main__":
    scrape_tech_transfer()