# Stanford Tech Transfer Scraper Guide

## Overview
The Stanford Tech Transfer scraper is a sophisticated tool designed to extract technology listings from university tech transfer websites. It uses a combination of web scraping, AI-powered content extraction, and parallel processing to efficiently gather and structure technology transfer data.

## Table of Contents
1. [How to Use](#how-to-use)
2. [Architecture Overview](#architecture-overview)
3. [Control Flow](#control-flow)
4. [Parallelism](#parallelism)
5. [Key Components](#key-components)
6. [Adapting for Other Universities](#adapting-for-other-universities)
7. [Configuration](#configuration)
8. [Error Handling](#error-handling)

## How to Use

### Prerequisites
```bash
# Required environment variables
JINA_API_KEY=your_jina_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=your_deepseek_base_url
```

### Running the Scraper
```bash
python scrapers/stanford_scraper_parallel.py
```

The scraper will:
1. Start from the Stanford Tech Transfer homepage
2. Process each listing page in sequence
3. Extract and process detail pages in parallel
4. Save results incrementally to `data/raw/stanford_raw.json`

## Architecture Overview

The scraper is built with a modular architecture consisting of three main components:

1. **ScraperConfig**: Configuration dataclass that holds all settings
2. **ContentExtractor**: Handles content extraction and AI processing
3. **TechTransferScraper**: Orchestrates the scraping process

### Data Flow
```
Web Page → Playwright → Jina API → Markdown → DeepSeek LLM → Structured JSON
```

## Control Flow

1. **Main Loop** (`scrape` method):
   - Initializes browser session
   - Navigates to start URL
   - Enters pagination loop

2. **Page Processing**:
   ```python
   while True and not should_stop:
       # 1. Get all listing URLs from current page
       # 2. Process detail pages in parallel
       # 3. Check stop conditions
       # 4. Save intermediate results
       # 5. Navigate to next page if available
   ```

3. **Stop Conditions**:
   - IP number ≤ S17
   - No more pages available
   - Error conditions

## Parallelism

The scraper implements parallelism at the detail page level:

1. **Process Pool**:
   ```python
   num_processes = max(1, multiprocessing.cpu_count() // 2)
   with multiprocessing.Pool(num_processes) as pool:
       process_func = partial(process_detail_page, config=self.config)
       page_results = list(pool.imap(process_func, detail_urls))
   ```

2. **Parallel Components**:
   - Markdown conversion (Jina API)
   - Content extraction (DeepSeek LLM)
   - Multiple detail pages processed simultaneously

3. **Benefits**:
   - Significantly faster processing
   - Efficient resource utilization
   - Automatic load balancing

4. **Implementation Details**:
   - Uses Python's multiprocessing
   - Each process handles complete detail page pipeline
   - Main process handles pagination and coordination
   - Results aggregated after parallel processing

## Key Components

### ScraperConfig
```python
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
```

### ContentExtractor
- **get_markdown_content**: Converts HTML to markdown using Jina
- **extract_info**: Processes markdown with DeepSeek LLM
- **_parse_llm_response**: Handles JSON parsing and error cases

### TechTransferScraper
- **scrape**: Main orchestration method
- **_process_detail_page**: Individual page processing
- **_save_results**: Handles incremental saving
- **_should_stop_scraping**: Controls termination conditions

## Adapting for Other Universities

To adapt the scraper for other universities:

1. **Update Selectors**:
   ```python
   selectors = {
       'item_links': "your-listing-selector",
       'next_button': "your-pagination-selector"
   }
   ```

2. **Modify Content Extraction**:
   - Update `jina_remove_selectors` for site-specific elements
   - Adjust LLM prompt if needed for different data structures

3. **Update Stop Conditions**:
   ```python
   def _should_stop_scraping(self, ip_number: str) -> bool:
       # Implement university-specific logic
       return False
   ```

4. **Handle Site-Specific Features**:
   - Different pagination mechanisms
   - Authentication if required
   - Rate limiting considerations

## Configuration

### Key Settings to Adjust

1. **URL Configuration**:
   - Base URL
   - Relative vs. absolute links
   - API endpoints

2. **Scraping Parameters**:
   - CSS selectors
   - Elements to remove
   - Stop conditions

3. **Processing Settings**:
   - Number of parallel processes
   - Batch sizes
   - Save frequency

### Example Configuration
```python
config = ScraperConfig(
    relative_links=True,
    selectors={
        'item_links': "your-selector",
        'next_button': "your-next-button"
    },
    jina_remove_selectors="your-remove-selectors"
)
```

## Error Handling

The scraper implements robust error handling:

1. **Page Level**:
   - Connection errors
   - Navigation timeouts
   - Missing elements

2. **Content Extraction**:
   - API failures
   - Parsing errors
   - Invalid responses

3. **Data Processing**:
   - JSON parsing errors
   - Missing fields
   - Invalid data types

4. **Recovery Mechanisms**:
   - Incremental saving
   - Error logging
   - Graceful degradation

### Error Recovery Example
```python
try:
    markdown_content = extractor.get_markdown_content(detail_url)
    extracted_data = extractor.extract_info(markdown_content)
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
``` 