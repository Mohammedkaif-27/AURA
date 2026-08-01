import os
import sys

# Ensure backend module can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.rag import rebuild_collection, initialize_rag_system

print("Initializing RAG system (connecting to HF API and Chroma Cloud)...")
initialize_rag_system()

print("Triggering deep rebuild (this will download all PDFs and run OCR)...")
success = rebuild_collection()

if success:
    print("\n✅ Rebuild complete!")
else:
    print("\n❌ Rebuild failed. Check the logs above.")
