# Tech Transfer Web Scraper: Detailed Explanation

This document provides a explanation of how the scraping script works. You will learn:

1. The **structure** of the code and each function’s responsibilities.
2. How to **configure** the scraper to work on a specific website.
3. How to **find the required CSS selectors** (with the help of the Rayrun or other browser dev tools).
4. How to **run the script** and **debug** any issues.
5. A recommended **workflow** for adapting the scraper to new university tech transfer sites.

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. Configuration and `ScraperConfig`](#2-configuration-and-scraperconfig)
  - [2.1. Config Fields in Detail](#21-config-fields-in-detail)
  - [2.2. How to fill out the `selectors`](#22-how-to-fill-out-the-selectors)
  - [2.3. Workflow for filling in config values](#23-workflow-for-filling-in-config-values)
- [3. The `ContentExtractor` Class](#3-the-contentextractor-class)
  - [3.1. `get_markdown_content` Method](#31-get_markdown_content-method)
  - [3.2. `extract_info` Method](#32-extract_info-method)
  - [3.3. `_parse_llm_response` Method](#33-_parse_llm_response-method)
- [4. The `process_detail_page` Function](#4-the-process_detail_page-function)
- [5. The `TechTransferScraper` Class](#5-the-techtransferscraper-class)
  - [5.1. The `scrape` Method (Async)](#51-the-scrape-method-async)
  - [5.2. `_should_stop_scraping` and `_save_results`](#52-_should_stop_scraping-and-_save_results)
- [6. The `main` Function](#6-the-main-function)
- [7. Running the Script](#7-running-the-script)
- [8. Adapting this Scraper to New Websites](#8-adapting-this-scraper-to-new-websites)
  - [8.1. Step-by-Step Workflow](#81-step-by-step-workflow)
- [9. Troubleshooting and Debugging](#9-troubleshooting-and-debugging)

---

## 1. Overview

The provided script automates the process of:

1. **Visiting a start page** (e.g., a university’s tech transfer website listing).
2. **Paginating** through multiple result pages, if available.
3. **Extracting links** to detail pages (each page representing a single technology).
4. **Requesting** the page’s content in **Markdown** format (using a Jina API).
5. **Using an LLM** (Deepseek) to **extract structured fields** from the Markdown.
6. **Collecting** and **saving** the results in a JSON file for easy analysis.

---

## 2. Configuration and `ScraperConfig`

### Location in Code
```python
@dataclass
class ScraperConfig:
    start_url: str = "https://tlo.mit.edu/industry-entrepreneurs/available-technologies"
    university: str = "mit"
    relative_links: bool = True
    max_pages: int = 20
    max_results: int = 0
    debug: bool = False
    parallel: bool = True
    jina_api_url: str = 'https://r.jina.ai/'
    jina_api_key: str = os.getenv('JINA_API_KEY')
    deepseek_api_key: str = os.getenv('DEEPSEEK_API_KEY')
    deepseek_base_url: str = os.getenv('DEEPSEEK_BASE_URL')
    selectors = {
        'item_links': ".views-row .arrow-text",
        'next_button': ".pager__item--next"
    }
    jina_remove_selectors = '.cta-section, .tech-brief-more, #footer, .header__navbar-inner, .header__navbar-bottom, .open'
    jina_target_selectors = '.tech-brief-header, .tech-brief-details'

This is the configuration object that centralizes all the user-defined settings for the scraper. It leverages Python’s @dataclass for neat organization.

2.1. Config Fields in Detail
	•	start_url
		- The main entry point for the scraper.
		- For MIT, it’s set to "https://tlo.mit.edu/industry-entrepreneurs/available-technologies".
		- You must update it if you’re scraping a different site.
	•	university
		- A string identifier (e.g., "mit", "stanford"), used to label saved data.
		- This is also used in the output file name (e.g., data/raw/stanford_raw.json).
	•	relative_links
		- A boolean. If True, the scraper will convert any relative URL to an absolute URL using the base of the current page.
		- If set to False, detail links are assumed to be absolute already.
	•	max_pages
		- A positive integer specifying the maximum number of pages to process.
		- 0 means unlimited pages.
	•	max_results
		- A positive integer specifying the maximum number of detail pages (technologies) to process in total.
		- 0 means unlimited results.
	•	debug
		- A boolean that, if True, makes the script print verbose debug information (such as requested URLs, headers, extracted content, etc.).
		- This is extremely useful for troubleshooting.
	•	parallel
		- If set to True, the script uses Python multiprocessing to process detail pages in parallel, speeding up the scrape.
		- If False, detail pages are processed sequentially, which may be easier to debug or if concurrency causes issues.
	•	jina_api_url
		- The base URL for the Jina service that converts HTML to Markdown.
		- Typically https://r.jina.ai/.
	•	jina_api_key
		- The API key for Jina, taken from an environment variable JINA_API_KEY.
		- If the environment variable is not set, it’s None.
	•	deepseek_api_key & deepseek_base_url
		- Similar to jina_api_key, used to authenticate with the Deepseek LLM service.
		- Grabbed from environment variables (DEEPSEEK_API_KEY and DEEPSEEK_BASE_URL).
	•	selectors
		- A dictionary with two main keys:
			- item_links: CSS selector for links to detail pages.
			- next_button: CSS selector for the pagination button (or link) to go to the next page.
		- Important: These are updated for each site.
	•	jina_remove_selectors
		- A CSS string specifying which elements to remove from the Jina-generated Markdown (e.g., footers, sidebars).
		- Adjust to your needs if you find irrelevant text cluttering your extracted data.
	•	jina_target_selectors
		- A CSS string specifying which parts of the page to focus on for the Jina-generated Markdown.
		- Helps to ensure only relevant text is extracted.

2.2. How to fill out the selectors
	1.	item_links (e.g., ".views-row .arrow-text")
		- This selector must match every link on the page that points to a single technology detail.
		- If you’re on a different site, locate the HTML element in the listing that links to the detail page.
		- For instance, it might be an <a> tag with a specific class name.
	2.	next_button (e.g., ".pager__item--next")
		- This selector must match the pagination link or button that navigates to the next set of results.
		- If there is no Next button but a more elaborate pagination system, you’ll have to adapt accordingly (or manually detect if you can’t find a standard Next button).
		- If you find that the site does not use a clickable next link but uses infinite scroll or a different mechanism, the script’s approach may need to be modified.

2.3. Workflow for filling in config values
	1.	Find the start URL
		- Go to the main listing page (e.g., https://example.com/tech-transfer/listing).
		- Copy and paste that into start_url.
	2.	Identify the university or site name
		- Provide a short string for university (e.g., "mit", "stanford", "nyu").
	3.	Use Rayrun (or your browser DevTools) to find the CSS selectors
		- Open the listing page in your browser.
		- Right-click on a link to a technology detail page.
		- Inspect the element or use the Rayrun extension to copy the CSS selector.
		- Paste it into selectors['item_links'].
	4.	Find the next_button selector
		- Same approach as above, but this time for the “Next Page” button or link.
		- If the site uses a link with the class .next-link, your selector might be ".next-link".
	5.	Set relative_links to True or False
		- If the links you see in the href attribute are like /detail/1234, that’s relative (so relative_links = True).
		- If the links are full URLs (e.g., https://example.com/tech/detail/1234), you can set relative_links = False.
	6.	Decide on max_pages and max_results
		- If you want to limit the scraper to the first 2 pages for testing, set max_pages=2.
		- If you want 50 items in total (even if that means 2 or 3 pages), set max_results=50.
	7.	Decide on debug
		- If you want to see logs, set debug=True.
		- Otherwise, keep it False for a cleaner output.
	8.	Decide on parallel
		- If the site is large and you want faster scraping, keep parallel=True.
		- If you want to debug step-by-step, set parallel=False.

3. The ContentExtractor Class

Location in code:

class ContentExtractor:
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.client = OpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url
        )
    ...

This class encapsulates the logic for:
	1.	Requesting page content from the Jina API (to get Markdown).
	2.	Extracting structured data from that Markdown using a Large Language Model (Deepseek).

3.1. get_markdown_content Method

def get_markdown_content(self, url: str) -> str:
    """Converts webpage content to markdown using Jina API."""
    ...

	•	What it does:
		- It sends a GET request to the Jina API (defined in config.jina_api_url).
		- It includes custom headers to:
			- Authorize with the Jina API key (if provided).
			- Remove certain selectors (X-Remove-Selector) from the HTML before conversion.
			- Target certain selectors (X-Target-Selector) for improved extraction of relevant text.
		- Return the response in markdown format.
	•	Debugging:
		- If debug=True, the function prints out:
			- The exact URL being fetched.
			- The headers used.
			- The raw Markdown returned by Jina.

3.2. extract_info Method

def extract_info(self, markdown_content: str) -> Dict[str, str]:
    """Extracts structured information from markdown content using LLM."""
    ...

	•	What it does:
		- It uses the Deepseek LLM to parse the Markdown content and extract specific fields:
			- ip_name
			- ip_number
			- published_date
			- ip_description
			- patents
		- It sends a chat request to the LLM with a system prompt instructing the LLM to parse out these fields and return them in JSON format.
		- Debugging:
			- If debug=True, the method prints the response from the LLM.

3.3. _parse_llm_response Method

def _parse_llm_response(self, content: str) -> Dict[str, str]:
    """Parses LLM response and handles potential JSON errors."""
    ...

	•	What it does:
		- Takes the LLM’s response (which should be JSON or fenced code blocks containing JSON) and safely loads it into a Python dictionary.
		- If there’s a JSON parse error, it logs an error and returns a dictionary with empty strings for each field.

4. The process_detail_page Function

Location in code:

def process_detail_page(detail_url: str, config: ScraperConfig) -> Dict[str, Optional[str]]:
    ...

	•	This is a standalone function (not in a class) used by the multiprocessing pool to:
	1.	Create a new ContentExtractor.
	2.	Fetch the Markdown content via Jina.
	3.	Ask the LLM to parse it.
	4.	Return the resulting dictionary with an additional key: "page_url".
		- If any exception occurs, it logs an error and returns empty strings for all fields but includes the "page_url" for debugging.

5. The TechTransferScraper Class

Location in code:

class TechTransferScraper:
    def __init__(self, config: ScraperConfig):
        ...
    ...

5.1. The scrape Method (Async)

async def scrape(self, start_url: str, university: str) -> List[Dict[str, str]]:
    ...

This is the core method that:
	1.	Launches a Playwright browser session (Chromium in headless mode).
	2.	Navigates to the start_url.
	3.	Enters a loop where:
		- It finds all items (using the CSS selector selectors['item_links']).
		- Extracts their detail URLs.
		- If relative_links=True, it calls urljoin to construct the absolute URL.
		- It processes these detail URLs (either in parallel or sequentially) via process_detail_page.
		- It checks each result to see if the max_pages or max_results threshold has been reached, and stops if necessary.
		- It saves the partial results to JSON.
		- It attempts to click the next_button to go to the next page (if found).
		- If no next_button is found, or a stop condition is reached, it breaks the loop.

Finally, the method closes the browser and returns the collected results.

5.2. _should_stop_scraping and _save_results
	•	_should_stop_scraping

def _should_stop_scraping(self, ip_number: str) -> bool:
    ...

Checks if we have hit max_results or max_pages. Returns True if scraping should stop.

	•	_save_results

def _save_results(self, results: List[Dict[str, str]], university: str) -> None:
    ...

	•	Writes the results list to data/raw/{university}_raw.json as formatted JSON. It’s called after each page’s results and at the very end of scraping.

6. The main Function

At the bottom of the file:

def main():
    config = ScraperConfig()
    scraper = TechTransferScraper(config)
    all_data = asyncio.run(scraper.scrape(config.start_url, config.university))
    print(f"Scraped {len(all_data)} items from {config.university} tech transfer site")

	1.	Creates an instance of ScraperConfig (this will read from environment variables if set).
	2.	Creates an instance of TechTransferScraper, passing the config.
	3.	Uses asyncio.run(...) to execute the async scrape method.
	4.	Prints the total items processed.

When running the script (python your_script.py), main() is called if __name__ == "__main__".

7. Running the Script
	1.	Install dependencies (Playwright, requests, openai, etc.).
	2.	Set environment variables (if needed) for JINA_API_KEY, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL.
	3.	Update the ScraperConfig with your target website’s details (selectors, start_url, etc.).
	4.	Run:

python scraper.py

(assuming the script is named scraper.py).

	5.	Watch the console output. If you set debug=True, you’ll see more verbose logs.

8. Adapting this Scraper to New Websites

The script is fairly generic. As long as:
	1.	The site uses a listing page with link elements to detail pages.
	2.	There is a “next page” button (or something equivalent).

Then you can fill out the config and run it.

8.1. Step-by-Step Workflow
	1.	Identify your target university/site.
	2.	Find the “Available Technologies” or “Tech Listings” page. Copy that URL into start_url.
	3.	Set the university field to a short name for that site.
	4.	Open the site in Chrome/Edge/Firefox (or your favorite browser) and:
		1.	Right-click on a link to an individual technology detail page.
		2.	Inspect (or use Rayrun).
	5.	Copy a unique CSS selector for that link (this is your selectors['item_links']).
	6.	Inspect the “Next” button for pagination.
	7.	Copy a CSS selector for it (this is your selectors['next_button']).
	8.	If the site does not have a next button but has a numeric pagination or infinite scrolling, you may have to modify the code logic or adapt the CSS selector for each page link.
	6.	Decide if the site’s detail page links are relative (like /details/tech123) or absolute (like https://.../details/tech123).
	•	Set relative_links=True or False accordingly.
	7.	Modify jina_remove_selectors or jina_target_selectors if necessary to remove or focus on specific parts of the page’s HTML.
	8.	(Optionally) set max_pages or max_results if you only want a subset of data for testing.
	9.	Run the script and observe the logs.
	•	If something goes wrong, enable debug=True and re-run to see more detailed output.

9. Troubleshooting and Debugging
	1.	No items found:
		- Make sure the CSS selector in selectors['item_links'] is correct.
		- Try toggling relative_links if the links do not open properly.
	2.	Next button not clicking or no next page is found:
		- Check the selectors['next_button'].
		- Inspect the HTML for the “next” link or button.
	3.	Some sites do not have a straightforward “Next” button.
	4.	Too many results or script not stopping:
		- Check your max_pages or max_results. If both are 0, the script will run until no next page is found or until it hits an error.
	5.	LLM extraction issues:
		- Look at the debug logs to see the raw Markdown.
		- If the LLM is not extracting the data properly, you may need to refine the system prompt or tweak the jina_target_selectors.
	6.	Parallel processing problems:
		- If you suspect concurrency issues, set parallel=False in your config to process detail pages sequentially.

Conclusion

By following the detailed explanation above, you should be able to:
	1.	Understand how the scraper is structured.
	2.	Confidently modify the configuration to target new websites.
	3.	Use debugging tools and logs to pinpoint and resolve issues.
	4.	Scrape your chosen tech transfer listings reliably, extracting the content into structured JSON format for further analysis.

Happy scraping!