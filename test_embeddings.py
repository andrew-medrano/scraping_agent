import os
import asyncio
from pinecone import Pinecone
from dotenv import load_dotenv

# Set this before importing any HuggingFace libraries
os.environ["TOKENIZERS_PARALLELISM"] = "false"

class SemanticSearch:
    def __init__(self, index_name='tech-transfer-01222024', top_k=20):
        # Load environment variables
        load_dotenv()
        self.pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
        self.index = self.pc.Index(index_name)
        self.top_k = top_k

    async def search(self, query, filter_dict=None):
        # Generate embedding using same model and parameters as embedding service
        embedding = self.pc.inference.embed(
            model="multilingual-e5-large",
            inputs=[query],
            parameters={"input_type": "query"}
        )

        # Query the index
        results = self.index.query(
            namespace="tech_transfer",
            vector=embedding[0].values,
            top_k=self.top_k,
            include_values=False,
            include_metadata=True,
            filter=filter_dict
        )

        return results['matches']

    def search_sync(self, query, filter_dict=None):
        """Synchronous wrapper for the async search method"""
        return asyncio.run(self.search(query, filter_dict=filter_dict))

    def get_by_id(self, id):
        """Fetch a specific document by its ID"""
        try:
            response = self.index.fetch(ids=[id], namespace="tech_transfer")
            if not response or not response.get('vectors'):
                return None
            return {
                'id': id,
                'metadata': response['vectors'][id].metadata,
                'score': 1.0
            }
        except Exception as e:
            print(f"Error fetching document: {e}")
            return None

if __name__ == "__main__":
    ss = SemanticSearch()
    while True:
        query = input("\nEnter search query (or 'q' to quit): ")
        if query.lower() == 'q':
            break
            
        results = ss.search_sync(query)
        if not results:
            print("No results found.")
            continue
            
        print(f"\nFound {len(results)} results:")
        for result in results:
            print(f"\nTitle: {result['metadata']['title']}")
            print(f"Score: {result['score']:.3f}")
            print(f"University: {result['metadata']['university']}")
            print(f"Description: {result['metadata']['description']}")
            print(f"Patents: {result['metadata']['patents']}")
            print(f"LLM Summary: {result['metadata']['llm_summary']}")
            print(f"LLM Teaser: {result['metadata']['llm_teaser']}")
