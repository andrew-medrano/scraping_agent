import os
import json
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
from tqdm import tqdm
from pathlib import Path

load_dotenv()

class TechTransferEmbeddings:
    def __init__(self, input_dir='data', index_name='tech-transfer'):
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
        
        for i, entry in enumerate(self.data):
            # Combine relevant fields for embedding
            text_for_embedding = f"{entry.get('ip_name', '')}. {entry.get('ip_description', '')}"
            
            # Create metadata
            metadata = {
                "title": entry.get('ip_name', ''),
                "number": entry.get('ip_number', ''),
                "description": entry.get('ip_description', ''),
                "published_date": entry.get('published_date', ''),
                "patents": entry.get('patents', ''),
                "page_url": entry.get('page_url', '')
            }
            
            self.formatted_data.append({
                "id": f"tech_{i}",
                "text": text_for_embedding,
                "metadata": metadata
            })
        
        print(f"Prepared {len(self.formatted_data)} entries for embedding")

    def generate_embeddings(self):
        """Generate and upload embeddings to Pinecone"""
        print("Generating embeddings...")
        batch_size = 20
        
        for i in tqdm(range(0, len(self.formatted_data), batch_size), desc="Processing batches"):
            batch = self.formatted_data[i:i + batch_size]
            
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
            
            # Upload to Pinecone
            index = self.pc.Index(self.index_name)
            index.upsert(vectors=vectors, namespace="tech_transfer")
            
        print("Embedding generation and upload complete")

def run_embedding_pipeline(input_dir='data', index_name='tech-transfer'):
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
    parser.add_argument('--input-dir', default='data', help='Directory containing JSON files to process')
    parser.add_argument('--index-name', default='tech-transfer', help='Name of the Pinecone index to use')
    args = parser.parse_args()
    
    run_embedding_pipeline(input_dir=args.input_dir, index_name=args.index_name)