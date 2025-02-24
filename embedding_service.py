import os
import json
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
from tqdm import tqdm
from pathlib import Path

load_dotenv()

class TechTransferEmbeddings:
    def __init__(self, input_dir='data/summarized', index_name='tech-transfer-01222024'):
        self.input_dir = input_dir
        self.pc = None
        self.index_name = index_name
        self.data = []
        
    def setup(self):
        """Initialize Pinecone client"""
        print("Setting up Pinecone client...")
        PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        
        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        print("Pinecone client setup complete.")

    def create_index(self):
        """Create Pinecone index if it doesn't exist"""
        print(f"Setting up index '{self.index_name}'...")
        try:
            self.pc.create_index(
                name=self.index_name,
                dimension=1024,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            print("Index created successfully.")
        except Exception as e:
            print(f"Index already exists or error occurred: {e}")

    def load_data(self):
        """Load all JSON files from input directory"""
        print(f"Loading data from {self.input_dir}...")
        input_path = Path(self.input_dir)
        
        if not input_path.exists():
            raise ValueError(f"Input directory {self.input_dir} does not exist")
            
        json_files = list(input_path.glob("*.json"))
        if not json_files:
            raise ValueError(f"No JSON files found in {self.input_dir}")
            
        for json_file in json_files:
            print(f"Loading {json_file.name}...")
            with open(json_file, 'r') as f:
                file_data = json.load(f)
                if isinstance(file_data, list):
                    self.data.extend(file_data)
                else:
                    self.data.append(file_data)
                    
        print(f"Loaded {len(self.data)} total technology entries from {len(json_files)} files")

    def prepare_texts(self):
        """Prepare texts for embedding"""
        print("Preparing texts for embedding...")
        self.formatted_data = []
        
        # Add debug logging
        used_ids = set()
        
        for i, entry in enumerate(self.data):
            # Generate ID
            entry_id = f"{entry.get('university', '').lower().replace(' ', '-')}_{entry.get('ip_number', '').lower().replace(' ', '-')}"
            
            # Debug: Check for ID collisions
            if entry_id in used_ids:
                print(f"WARNING: Duplicate ID found: {entry_id}")
            used_ids.add(entry_id)
            
            # Rest of the preparation code...
            text_for_embedding = f"{entry.get('ip_name', '')}. {entry.get('ip_description', '')} {entry.get('llm_summary', '')}"
            
            # Create metadata with null value handling
            metadata = {
                "university": entry.get('university', ''),
                "title": entry.get('ip_name', ''),
                "number": entry.get('ip_number', ''),
                "description": entry.get('ip_description', ''),
                "llm_teaser": entry.get('llm_teaser', ''),
                "llm_summary": entry.get('llm_summary', ''),
                "published_date": entry.get('published_date', ''),
                "patents": entry.get('patents', []),
                "page_url": entry.get('page_url', '')
            }
            
            cleaned_metadata = {k: [] if v is None and isinstance(v, (list, tuple)) else "" if v is None else v 
                              for k, v in metadata.items()}
            
            self.formatted_data.append({
                "id": entry_id,
                "text": text_for_embedding,
                "metadata": cleaned_metadata
            })
            
        print(f"Prepared {len(self.formatted_data)} entries for embedding")
        print(f"Number of unique IDs: {len(used_ids)}")

    def generate_embeddings(self):
        """Generate and upload embeddings to Pinecone"""
        print("Generating embeddings...")
        batch_size = 20
        
        # Debug: Track processed entries
        processed_count = 0
        
        for i in tqdm(range(0, len(self.formatted_data), batch_size), desc="Processing batches"):
            batch = self.formatted_data[i:i + batch_size]
            
            # Debug: Print batch info
            print(f"\nProcessing batch {i//batch_size + 1}")
            print(f"Batch size: {len(batch)}")
            print(f"First ID in batch: {batch[0]['id']}")
            print(f"Last ID in batch: {batch[-1]['id']}")
            
            # Generate embeddings for batch
            batch_embeddings = self.pc.inference.embed(
                model='multilingual-e5-large',
                inputs=[d['text'] for d in batch],
                parameters={"input_type": "passage", "truncate": "END"}
            )
            
            # Prepare vectors for upload
            vectors = []
            for d, e in zip(batch, batch_embeddings):
                vectors.append({
                    "id": d['id'],
                    "values": e['values'],
                    "metadata": d['metadata']
                })
            
            # Debug: Print vector info
            print(f"Number of vectors to upload: {len(vectors)}")
            
            # Upload to Pinecone
            index = self.pc.Index(self.index_name)
            index.upsert(vectors=vectors, namespace="tech_transfer")
            
            processed_count += len(vectors)
            print(f"Total processed entries: {processed_count}")
            
        print(f"Final processed count: {processed_count}")
        print("Embedding generation and upload complete")

def run_embedding_pipeline(input_dir='data/summarized', index_name='tech-transfer'):
    """Run the complete embedding pipeline"""
    embedder = TechTransferEmbeddings(input_dir=input_dir, index_name=index_name)
    
    try:
        embedder.setup()
        embedder.create_index()
        embedder.load_data()
        embedder.prepare_texts()
        embedder.generate_embeddings()
        print("Embedding pipeline completed successfully!")
    except Exception as e:
        print(f"Error in embedding pipeline: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Generate embeddings for tech transfer data')
    parser.add_argument('--input-dir', default='data/summarized', help='Directory containing JSON files to process')
    parser.add_argument('--index-name', default='tech-transfer-02162025', help='Name of the Pinecone index to use')
    args = parser.parse_args()
    
    run_embedding_pipeline(input_dir=args.input_dir, index_name=args.index_name)