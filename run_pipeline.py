import argparse
from scraper import scrape_tech_transfer
from summarization_service import run_summarization_pipeline
from embedding_service import run_embedding_pipeline

def run_full_pipeline(max_pages=3, index_name='tech-transfer'):
    """Run the complete tech transfer pipeline: scraping → summarization → embeddings"""
    print("\n=== Starting Tech Transfer Pipeline ===\n")
    
    print("Step 1: Scraping data...")
    scrape_tech_transfer(max_pages=max_pages)
    
    print("\nStep 2: Generating summaries...")
    run_summarization_pipeline()
    
    print("\nStep 3: Creating embeddings...")
    run_embedding_pipeline(input_dir='data', index_name=index_name)
    
    print("\n=== Pipeline Complete! ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the complete tech transfer pipeline')
    parser.add_argument('--max-pages', type=int, default=3, help='Maximum number of pages to scrape')
    parser.add_argument('--index-name', default='tech-transfer', help='Name for the Pinecone index')
    args = parser.parse_args()
    
    run_full_pipeline(max_pages=args.max_pages, index_name=args.index_name) 