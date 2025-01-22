import os
import agentql
from playwright.sync_api import sync_playwright
from pyairtable import Api
from dotenv import load_dotenv
import json
import logging
import argparse

# Load environment variables
load_dotenv()
os.environ["AGENTQL_API_KEY"] = os.getenv("AGENTQL_API_KEY")

# Constants
INITIAL_URL = "https://ucla.technologypublisher.com/"
UNIVERSITY_SHORT_NAME = "ucla"
MAX_PAGES = 70
# Add timeout constants
NAVIGATION_TIMEOUT = 10000  # 10 seconds
WAIT_TIMEOUT = 200  # 200ms between actions

# AgentQL Queries
LIST_PAGE_QUERY = """
{
    ip_result(select the <a> elements containing technology titles that link to detail pages, it is not the algolia search)[]
    next_page_button(element to go to next page of results)
}
"""

RESULT_PAGE_QUERY = """
{
    ip_name(text that precedes the ip number, at the top of the page)
    ip_number(number to the right of the title, at the top of the page)
    published_date(first part of ip number, at top of page, only has year)
    ip_description(background, details, benefits, applications, advantages, etc.)
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

def load_results(filename=f'{UNIVERSITY_SHORT_NAME}_raw.json'):
    """Load existing results from JSON file in the data directory"""
    filepath = os.path.join('data/raw', filename)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse existing results file {filepath}")
                return []
    return []

def save_results(results, filename=f'{UNIVERSITY_SHORT_NAME}_raw.json'):
    """Save results to JSON file in the data directory"""
    # Ensure data directory exists
    os.makedirs('data/raw', exist_ok=True)
    
    # Save to data directory
    filepath = os.path.join('data/raw', filename)
    # Create file if it doesn't exist
    with open(filepath, 'w+') as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {filepath}")

def initialize_page(browser):
    """Initialize and return a wrapped browser page"""
    page = agentql.wrap(browser.new_page())
    # Set shorter timeouts for the page
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
    page.set_default_timeout(NAVIGATION_TIMEOUT)
    page.goto(INITIAL_URL)
    page.wait_for_load_state('networkidle', timeout=NAVIGATION_TIMEOUT)
    return page


def process_single_result(page, current_result, index, total_results):
    """Process a single IP result and return the data"""
    try:
        # First try to get href directly
        link = current_result.get_attribute('href')
        if not link:
            # If that fails, try to find the anchor tag within the element
            anchor = current_result.locator('a').first
            link = anchor.get_attribute('href')
            
        if not link:
            print(f"Warning: Could not find link for result {index + 1}")
            return None
            
        if not link.startswith('http'):
            link = INITIAL_URL.rstrip('/') + '/' + link.lstrip('/')
            
        print(f"Processing link: {link}")
        page.wait_for_timeout(WAIT_TIMEOUT)  # Reduced from 500ms to 200ms
        page.goto(link)
        page.wait_for_load_state('networkidle', timeout=NAVIGATION_TIMEOUT)
        
        # First check the published date
        result_data = page.query_data(RESULT_PAGE_QUERY)
        try:
            published_year = int(result_data.get('published_date', '0'))
            if published_year < 2018:
                print(f"Skipping result {index + 1}/{total_results}: Published in {published_year} (before 2018)")
                page.go_back()
                page.wait_for_load_state('networkidle', timeout=NAVIGATION_TIMEOUT)
                return None
        except (ValueError, TypeError):
            print(f"Warning: Could not parse published year for result {index + 1}")
        
        result_data['page_url'] = page.url
        print(f"Processed result {index + 1}/{total_results}: {result_data.get('ip_name', 'Unknown Title')}")
        
        page.go_back()
        page.wait_for_load_state('networkidle', timeout=NAVIGATION_TIMEOUT)
        
        return result_data
    except Exception as e:
        print(f"Error processing result {index + 1}: {str(e)}")
        # Make sure we return to the list page even if there's an error
        try:
            page.go_back()
            page.wait_for_load_state('networkidle', timeout=NAVIGATION_TIMEOUT)
        except Exception as nav_error:
            print(f"Error returning to list page: {str(nav_error)}")
        return None

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

    index = 0
    while index < total_results:
        try:
            # Re-query the elements to get fresh reference
            response = page.query_elements(LIST_PAGE_QUERY)
            current_results = response.ip_result
            
            # Check if the refreshed list still has enough elements
            if index >= len(current_results):
                print(f"Warning: Results list changed size during processing, stopping at index {index}")
                break
                
            current_result = current_results[index]
            result_data = process_single_result(page, current_result, index, total_results)
            
            if result_data:  # Only append if we got valid data
                results.append(result_data)
            
            index += 1
            
        except Exception as e:
            print(f"Error processing result {index + 1}: {str(e)}")
            page.screenshot(path=f"error_screenshot_{index}.png")
            # Still increment index to move to next result even if this one failed
            index += 1
            continue
    
    return results, get_next_page_button(page)

def scrape_tech_transfer(max_pages=MAX_PAGES, start_page=1):
    """Main function to scrape the tech transfer website
    
    Args:
        max_pages (int): Maximum number of pages to scrape
        start_page (int): Page number to start scraping from
    """
    print(f"Starting scraping from page {start_page} (max {max_pages} pages)...")
    
    # Load existing results if any
    all_results = load_results()
    print(f"Loaded {len(all_results)} existing results")
    
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)  # Changed to headless for speed
        page = initialize_page(browser)
        
        # Navigate to start_page if needed
        current_page = 1
        while current_page < start_page:
            next_button = get_next_page_button(page)
            if not next_button:
                print(f"Could not reach start page {start_page}, stopping at page {current_page}")
                browser.close()
                return all_results
            next_button.click()
            page.wait_for_load_state('networkidle', timeout=NAVIGATION_TIMEOUT)
            current_page += 1
        
        # Process all pages
        pages_scraped = 0
        while True:
            try:
                pages_scraped += 1
                print(f"\n=== Processing Page {current_page}/{max_pages} ===")
                
                page_results, next_button = process_page_results(page)
                all_results.extend(page_results)
                save_results(all_results)
                print(f"Saved {len(all_results)} total results so far")
                
                next_button = get_next_page_button(page)
                if not next_button or pages_scraped >= max_pages:
                    break
                    
                next_button.click()
                page.wait_for_load_state('networkidle', timeout=NAVIGATION_TIMEOUT)
                current_page += 1
                
            except Exception as e:
                print(f"Error navigating to next page: {str(e)}")
                break
        
        browser.close()
    
    print(f"\nScraping completed. Total results: {len(all_results)}")
    return all_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape UCLA tech transfer listings')
    parser.add_argument('--max-pages', type=int, default=MAX_PAGES,
                      help='Maximum number of pages to scrape')
    parser.add_argument('--start-page', type=int, default=10,
                      help='Page number to start scraping from')
    
    args = parser.parse_args()
    scrape_tech_transfer(max_pages=args.max_pages, start_page=args.start_page)