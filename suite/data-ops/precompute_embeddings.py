import json
import os
import sys

# Try to import sentence_transformers
try:
    from sentence_transformers import SentenceTransformer
    import torch
except ImportError:
    print("Error: sentence-transformers not found.")
    print("Please install it using: pip install sentence-transformers torch")
    sys.exit(1)

def precompute_embeddings():
    model_name = 'all-MiniLM-L6-v2'
    print(f"Loading model {model_name}...")
    
    # Force CPU for stability in script context if no GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(model_name, device=device)

    # Paths relative to project root
    files_to_process = [
        {
            "path": "apps/chat-app/public/assets/golden_dataset.json",
            "text_gen": lambda item: item["question"]
        },
        {
            "path": "apps/chat-app/public/assets/league_lore.json",
            "text_gen": lambda item: f"{item['topic']}: {item['context']}"
        }
    ]

    for file_info in files_to_process:
        file_path = file_info["path"]
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}")
            continue

        print(f"Processing {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        texts = [file_info["text_gen"](item) for item in data]

        print(f"Generating embeddings for {len(texts)} items...")
        embeddings = model.encode(texts, show_progress_bar=True)

        for i, item in enumerate(data):
            # Convert to list of floats for JSON serialization
            item["embedding"] = [float(val) for val in embeddings[i]]

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        print(f"Successfully updated {file_path}")

if __name__ == "__main__":
    precompute_embeddings()
