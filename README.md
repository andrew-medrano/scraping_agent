# Tech Transfer Scraper

A Python-based web scraper that extracts technology transfer listings.

## Overview

This scraper uses Playwright and AgentQL to navigate and extract data from CMU's technology transfer website. It captures details about each technology listing including titles, descriptions, patent information, and publication dates.

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
playwright install
```

3. Create a `.env` file in the project root with your AgentQL API key:
```
AGENTQL_API_KEY=your_key_here
```

## Usage

Run the scraper:
```bash
python scraper.py
```

By default, it will:
- Scrape up to 3 pages of results
- Save data to `data/tech_transfer_results.json`
- Show progress in the terminal
- Take screenshots of any errors

## Data Storage

All scraped data is stored in the `data/` directory:
- Main results file: `data/tech_transfer_results.json`
- Error screenshots: `error_screenshot_X.png` (in project root)

The data directory is version controlled but its contents are gitignored. This ensures:
1. The directory structure is preserved
2. Scraped data doesn't clutter the git history
3. Sensitive data isn't accidentally committed

## Data Structure

The scraper saves data in JSON format with the following structure for each technology:
```json
{
    "ip_name": "Technology Title",
    "ip_number": "Reference Number",
    "published_date": "Publication Date",
    "ip_description": "Detailed Description",
    "patents": "Related Patent Numbers",
    "page_url": "Full URL of the listing"
}
```

## Customization

### Modifying Search Parameters
To change what data is extracted, modify the query templates in `scraper.py`:
- `LIST_BUTTON_QUERY`: Identifies the list view button
- `LIST_PAGE_QUERY`: Extracts listing previews and navigation
- `RESULT_PAGE_QUERY`: Defines what data to extract from each listing

### Adjusting Scraping Behavior
In `scraper.py`:
- Change `max_pages` in `scrape_tech_transfer()` to adjust how many pages to scrape
- Modify `save_results()` to change where/how data is saved
- Update error handling in `process_single_result()` for different error scenarios

### Adding New Features
The code is modular with clear separation of concerns:
- `initialize_page()`: Browser setup
- `switch_to_list_view()`: Navigation
- `process_single_result()`: Individual listing processing
- `process_page_results()`: Page-level processing
- `scrape_tech_transfer()`: Overall orchestration

Add new functions or modify existing ones based on your needs.

## Error Handling

- Failed scrapes create screenshots in the project root (`error_screenshot_X.png`)
- Progress is saved after each page in case of interruption
- Errors for individual listings don't stop the entire process

## Dependencies

- `playwright`: Web automation
- `agentql`: Web scraping assistance
- `python-dotenv`: Environment variable management
- `pyairtable`: (Optional) For Airtable integration

## Future Improvements

Potential enhancements:
1. Add retry logic for failed scrapes
2. Implement rate limiting
3. Add data validation
4. Create data export options (CSV, Excel)
5. Add command line arguments for configuration
6. Implement parallel processing for faster scraping
