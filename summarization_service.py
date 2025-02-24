import json
import os
from dotenv import load_dotenv
from tqdm import tqdm
from openai import OpenAI
from pathlib import Path
import multiprocessing
from functools import partial

load_dotenv()

UNIVERSITY_NAMES = {
    'cmu': 'Carnegie Mellon University',
    'duke': 'Duke University',
    'harvard': 'Harvard University',
    'johnsHopkins': 'Johns Hopkins University',
    'mit': 'Massachusetts Institute of Technology',
    'ohioState': 'Ohio State University',
    'princeton': 'Princeton University',
    'rutgers': 'Rutgers University',
    'stanford': 'Stanford University',
    'uArizona': 'University of Arizona',
    'ucDavis': 'University of California, Davis',
    'uChicago': 'University of Chicago',
    'ucla': 'University of California, Los Angeles',
    'ucSanDiego': 'University of California, San Diego',
    'umich': 'University of Michigan',
    'uMinnesota': 'University of Minnesota',
    'uWashington': 'University of Washington'
}

class TechTransferSummarizer:
    def __init__(self, input_dir='data/raw', output_dir='data/summarized'):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
    def clean_null_values(self, data):
        """
        Replace null values with empty strings in the data structure.
        
        Args:
            data: Data structure (dict or list) to clean
        Returns:
            Cleaned data structure with null values replaced by empty strings
        """
        def replace_nulls(obj):
            if isinstance(obj, dict):
                return {k: replace_nulls(v) if v is not None else "" for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_nulls(item) if item is not None else "" for item in obj]
            return obj if obj is not None else ""
        
        return replace_nulls(data)

    def filter_empty_descriptions(self, data):
        """
        Remove entries that don't have a description or have empty descriptions.
        
        Args:
            data: List of technology entries
        Returns:
            Filtered list with only entries containing descriptions
        """
        original_count = len(data)
        filtered_data = [
            entry for entry in data 
            if entry.get('ip_description') and len(entry['ip_description'].strip()) > 0
        ]
        removed_count = original_count - len(filtered_data)
        print(f"Removed {removed_count} entries without descriptions")
        return filtered_data

    def load_data(self, input_file):
        """Load data from JSON file, clean null values, and filter empty descriptions"""
        print(f"Loading data from {input_file}...")
        with open(input_file, 'r') as f:
            self.data = json.load(f)
        # Clean null values after loading
        self.data = self.clean_null_values(self.data)
        # Filter out entries without descriptions
        self.data = self.filter_empty_descriptions(self.data)
        print(f"Loaded, cleaned, and filtered to {len(self.data)} technology entries")
    
    def save_data(self, output_file):
        """Save processed data to JSON file"""
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Saving results to {output_file}...")
        with open(output_file, 'w') as f:
            json.dump(self.data, f, indent=2)
        print("Save complete!")

    def generate_summary(self, title, description):
        """Generate a structured summary using DeepSeek API"""
        if not description or len(description.strip()) < 30:
            prompt = f"""Given only the technology title '{title}', provide a conservative estimate of what this technology might do.
            Format the response with these exact headers:
            **Summary:** (2-3 sentences about likely purpose)
            **Applications:** (1-2 potential use cases)
            **Problem Solved:** (1 sentence about the likely problem addressed)
            Be very clear that this is based only on the title."""
        else:
            prompt = f"""Summarize this technology transfer listing:
            Title: {title}
            Description: {description}
            
            Format the response with these exact headers:
            **Summary:** (2-3 sentences about key features and capabilities)
            **Applications:** (2-3 main use cases or industries)
            **Problem Solved:** (1-2 sentences about the problem this technology addresses)
            
            Focus only on factual information from the text. Be concise and specific."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800
        )
        return response.choices[0].message.content.strip()

    def generate_teaser(self, title, description):
        """Generate a short teaser using DeepSeek API"""
        if not description or len(description.strip()) < 30:
            prompt = f"Create a one-sentence teaser for a technology titled '{title}'. Be conservative and only state what can be reasonably inferred from the title."
        else:
            prompt = f"""Create a compelling one-sentence teaser for this technology:
            Title: {title}
            Description: {description}
            
            Focus on the key benefit or innovation. Be specific but concise."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()

    def process_single_entry(self, entry, university_name):
        """Process a single entry with summary and teaser"""
        title = entry.get('ip_name', '')
        description = entry.get('ip_description', '')
        
        try:
            # Generate summary and teaser
            entry['llm_summary'] = self.generate_summary(title, description)
            entry['llm_teaser'] = self.generate_teaser(title, description)
            # Add university name
            entry['university'] = university_name
            return entry
        except Exception as e:
            print(f"\nError processing entry '{title}': {str(e)}")
            return entry

    def process_entries(self, university_code):
        """Process all entries with summaries and teasers in parallel"""
        print("Processing entries...")
        university_name = UNIVERSITY_NAMES.get(university_code, university_code.upper())
        
        # Use half of available CPU cores for API calls
        num_processes = max(1, multiprocessing.cpu_count() // 2)
        
        with multiprocessing.Pool(num_processes) as pool:
            # Create partial function with fixed university_name
            process_func = partial(self.process_single_entry, university_name=university_name)
            
            # Process entries in parallel
            self.data = list(tqdm(
                pool.imap(process_func, self.data),
                total=len(self.data)
            ))
            
        # Save results
        output_file = self.output_dir / f"{university_code}_summarized.json"
        self.save_data(output_file)

def process_single_entry(entry, university_code):
    """Process a single entry with summary and teaser - standalone function for multiprocessing"""
    summarizer = TechTransferSummarizer()  # Create new instance for each process
    university_name = UNIVERSITY_NAMES.get(university_code, university_code.upper())
    
    return summarizer.process_single_entry(entry, university_name)

def run_summarization_pipeline():
    """Run the complete summarization pipeline with parallel API calls"""
    try:
        # Get list of files to process
        input_files = list(Path('data/raw').glob('*.json'))
        summarizer = TechTransferSummarizer()
        
        for input_file in input_files:
            university_code = input_file.stem.split('_')[0] # cmu_raw.json -> cmu
            
            # Check if summarized file already exists
            summarized_file = Path('data/summarized') / f"{university_code}_summarized.json"
            if summarized_file.exists():
                print(f"\nSkipping {university_code} - summarized file already exists")
                continue
                
            print(f"\nProcessing {university_code} data...")
            summarizer.load_data(input_file)
            
            # Use half of available CPU cores for API calls
            num_processes = max(1, multiprocessing.cpu_count() // 2)
            
            # Process entries in parallel
            with multiprocessing.Pool(num_processes) as pool:
                process_func = partial(process_single_entry, university_code=university_code)
                summarizer.data = list(tqdm(
                    pool.imap(process_func, summarizer.data),
                    total=len(summarizer.data)
                ))
            
            # Save results
            output_file = summarizer.output_dir / f"{university_code}_summarized.json"
            summarizer.save_data(output_file)
            
        print("Summarization pipeline completed successfully!")
    except Exception as e:
        print(f"Error in summarization pipeline: {e}")

if __name__ == "__main__":
    run_summarization_pipeline()