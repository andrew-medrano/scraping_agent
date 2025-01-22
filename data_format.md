# Tech Transfer Data Pipeline Format

This document outlines the data structure at each stage of the tech transfer pipeline.

## 1. After Scraping (`data/tech_transfer_results.json`)

Raw data from the website, stored as a JSON array of objects:

```json
[
  {
    "ip_name": "Novel Method for Quantum Computing",
    "ip_number": "REF-2024-001",
    "published_date": "2024-01-15",
    "ip_description": "A groundbreaking approach to quantum computing...",
    "patents": "US12345678, EP87654321",
    "page_url": "https://cmu.flintbox.com/technologies/sample-1"
  },
  // ... more entries
]
```

## 2. After Summarization (`data/tech_transfer_results_summarized.json`)

Enhanced data with AI-generated summaries and teasers:

```json
[
  {
    // Original scraped fields
    "ip_name": "Novel Method for Quantum Computing",
    "ip_number": "REF-2024-001",
    "published_date": "2024-01-15",
    "ip_description": "A groundbreaking approach to quantum computing...",
    "patents": "US12345678, EP87654321",
    "page_url": "https://cmu.flintbox.com/technologies/sample-1",
    
    // Added by summarization service
    "llm_summary": "**Summary:** This technology introduces a novel approach to quantum computing using topological qubits.\n\n**Applications:** Cryptography, drug discovery, and financial modeling.\n\n**Problem Solved:** Addresses the stability issues in current quantum computing systems.",
    "llm_teaser": "Revolutionary quantum computing method that increases qubit stability by 100x while reducing error rates."
  },
  // ... more entries
]
```

## 3. Vector Database Format (Pinecone)

The data is split into two components when stored in Pinecone:

### 3.1 Text for Embedding
Combined text that gets converted into a vector embedding:
```text
{ip_name}. {ip_description}
```

### 3.2 Metadata
Stored alongside the vector for filtering and retrieval:
```json
{
  "id": "tech_0",
  "values": [0.123, -0.456, ...],  // 1024-dimensional vector
  "metadata": {
    "title": "Novel Method for Quantum Computing",
    "number": "REF-2024-001",
    "description": "A groundbreaking approach to quantum computing...",
    "published_date": "2024-01-15",
    "patents": "US12345678, EP87654321",
    "page_url": "https://cmu.flintbox.com/technologies/sample-1"
  }
}
```

## Data Flow Summary

1. **Scraper** → Raw data (basic fields)
2. **Summarizer** → Enhanced data (adds AI-generated content)
3. **Embedder** → Vector database
   - Converts text to embeddings
   - Stores metadata for retrieval

## Field Descriptions

### Scraped Fields
- `ip_name`: Technology title
- `ip_number`: Reference/ID number
- `published_date`: Publication date
- `ip_description`: Full technology description
- `patents`: Related patent numbers
- `page_url`: Source URL

### Generated Fields
- `llm_summary`: Structured summary with sections
  - Summary section: Key features
  - Applications section: Use cases
  - Problem Solved section: Issues addressed
- `llm_teaser`: One-sentence highlight

### Vector Database Fields
- `id`: Unique identifier (university_ipnumber, e.g. "cmu_REF-2024-001")
- `values`: Vector embedding (1024 dimensions)
- `metadata`: Original fields for filtering/display
- `namespace`: "tech_transfer" (organizes entries)