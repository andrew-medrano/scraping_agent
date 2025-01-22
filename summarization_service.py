import json
import os
from dotenv import load_dotenv
from tqdm import tqdm
from openai import OpenAI

load_dotenv()

class TechTransferSummarizer:
    def __init__(self, input_file='data/tech_transfer_results.json', output_file=None):
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_summarized.json')
        self.client = OpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url=os.getenv('DEEPSEEK_BASE_URL'))
        
    def load_data(self):
        """Load data from JSON file"""
        print(f"Loading data from {self.input_file}...")
        with open(self.input_file, 'r') as f:
            self.data = json.load(f)
        print(f"Loaded {len(self.data)} technology entries")
    
    def save_data(self):
        """Save processed data to JSON file"""
        print(f"Saving results to {self.output_file}...")
        with open(self.output_file, 'w') as f:
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
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
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
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()

    def process_entries(self):
        """Process all entries with summaries and teasers"""
        print("Processing entries...")
        for entry in tqdm(self.data):
            title = entry.get('ip_name', '')
            description = entry.get('ip_description', '')
            
            try:
                # Generate summary and teaser
                entry['llm_summary'] = self.generate_summary(title, description)
                entry['llm_teaser'] = self.generate_teaser(title, description)
                
                # Save after each entry to maintain progress
                self.save_data()
                
            except Exception as e:
                print(f"\nError processing entry '{title}': {str(e)}")
                continue

def run_summarization_pipeline():
    """Run the complete summarization pipeline"""
    summarizer = TechTransferSummarizer()
    
    try:
        summarizer.load_data()
        summarizer.process_entries()
        print("Summarization pipeline completed successfully!")
    except Exception as e:
        print(f"Error in summarization pipeline: {e}")

if __name__ == "__main__":
    run_summarization_pipeline()