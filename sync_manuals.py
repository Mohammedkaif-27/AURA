
import os
import sys
import logging
from dotenv import load_dotenv

# Ensure we can import from backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend import supabase_client
from backend.main import _infer_doc_type

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def sync_storage_to_db():
    load_dotenv()
    
    # 1. Get all files from the 'manuals' bucket
    # We will check both the root and the 'manuals' subfolder since some files are in the subfolder.
    root_files = supabase_client.get_storage_file_list('manuals', '') or []
    subfolder_files = supabase_client.get_storage_file_list('manuals', 'manuals') or []
    
    all_files = []
    
    for f in root_files:
        if f.get('name') != 'manuals' and f.get('id'):
            all_files.append({'filename': f['name'], 'path': f['name']})
            
    for f in subfolder_files:
        if f.get('name') and f.get('id'):
            all_files.append({'filename': f['name'], 'path': f"manuals/{f['name']}"})
            
    if not all_files:
        logging.info("No files found in Supabase Storage bucket 'manuals'.")
        return

    # 2. Get existing entries in knowledge_base table to avoid duplicates
    existing_entries = supabase_client.get_knowledge_entries() or []
    existing_paths = {e.get('bucket_path') for e in existing_entries}
    
    added_count = 0
    for file_info in all_files:
        bucket_path = file_info['path']
        filename = file_info['filename']
        
        if bucket_path in existing_paths:
            logging.info(f"Skipping {filename}, already in knowledge_base.")
            continue
            
        doc_type = _infer_doc_type(filename)
        
        # Insert into knowledge_base table
        entry = {
            "file_name": filename,
            "bucket_path": bucket_path,
            "document_type": doc_type,
            "status": "ready", # Setting to ready, but 0 chunks, so it might need re-indexing
            "chunks_count": 0
        }
        
        res = supabase_client.insert_knowledge_entry(entry)
        if res:
            logging.info(f"Added {filename} to knowledge_base table.")
            added_count += 1
        else:
            logging.error(f"Failed to add {filename}")
            
    logging.info(f"Sync complete. Added {added_count} new entries to knowledge_base.")
    logging.info("Please restart your AURA backend. The startup process should now download and index these files.")

if __name__ == "__main__":
    sync_storage_to_db()
