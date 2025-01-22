# Tech Transfer Pipeline

A complete pipeline for scraping, summarizing, and embedding technology transfer listings from Carnegie Mellon University's Flintbox platform.

## Overview

This pipeline consists of three main components:
1. **Scraper**: Extracts technology listings from CMU's Flintbox
2. **Summarizer**: Generates AI summaries and teasers for each technology
3. **Embedder**: Creates vector embeddings for semantic search

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

3. Create a `.env` file with your API keys:
```env
AGENTQL_API_KEY=your_agentql_key
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_BASE_URL=your_deepseek_url
PINECONE_API_KEY=your_pinecone_key
```

## Running the Pipeline

You can run each component separately:

1. **Scraper**:
```bash
python cmu_scraper.py
```
- Scrapes technology listings
- Saves to `data/tech_transfer_results.json`

1. **Summarizer**:
```bash
python summarization_service.py
```
- Generates summaries and teasers
- Saves to `data/tech_transfer_results_summarized.json`

1. **Embedder**:
```bash
python embedding_service.py --input-dir data --index-name tech-transfer
```
- Creates vector embeddings
- Uploads to Pinecone database

## Data Pipeline

See `data_format.md` for detailed information about:
- Data structure at each stage
- Field descriptions
- Example JSON formats
- Vector database schema

## Directory Structure

```
.
├── data/                      # Data directory
│   ├── .gitkeep
│   ├── raw/
│   │   ├── cmu_raw.json
│   │   └── mit_raw.json
│   ├── summarized/
│   │   ├── cmu_summarized.json
│   │   └── mit_summarized.json
├── scrapers/
│   ├── cmu_scraper.py
│   └── mit_scraper.py
├── summarization_service.py   # AI summarization service
├── embedding_service.py       # Vector embedding service
├── data_format.md            # Data format documentation
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Error Handling

- Failed scrapes create screenshots (`error_screenshot_X.png`)
- Progress is saved after each entry
- Each service can be rerun independently
- Pipeline maintains state between steps

## Customization

### Scraper
- Modify `RESULT_PAGE_QUERY` in `scraper.py` to extract different fields
- Adjust page wait times for slower connections
- Change headless mode for debugging

### Summarizer
- Update prompt templates in `summarization_service.py`
- Modify summary structure
- Adjust token limits

### Embedder
- Change embedding model
- Modify metadata fields
- Adjust batch sizes

## Troubleshooting

1. **Scraper Issues**
   - Check screenshots in error_screenshot_*.png
   - Verify AgentQL API key
   - Ensure stable internet connection

2. **Summarizer Issues**
   - Verify DeepSeek API key and base URL
   - Check input JSON format
   - Monitor token usage

3. **Embedder Issues**
   - Verify Pinecone API key
   - Check index dimensions
   - Monitor batch processing

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - See LICENSE file for details
