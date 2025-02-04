import os
import json

def clean_null_values(directory_path):
    """
    Recursively finds all JSON files in the given directory and replaces 'null' values with empty strings.
    
    Args:
        directory_path (str): Path to directory containing JSON files to clean
    """
    # Walk through directory
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                
                # Read JSON file
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Helper function to recursively replace nulls
                def replace_nulls(obj):
                    if isinstance(obj, dict):
                        return {k: replace_nulls(v) if v is not None else "" for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [replace_nulls(item) if item is not None else "" for item in obj]
                    return obj if obj is not None else ""
                
                # Clean the data
                cleaned_data = replace_nulls(data)
                
                # Write back to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    # Example usage
    clean_null_values("data/summarized")
