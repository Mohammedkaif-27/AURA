import os
import sys

# Ensure backend module can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.supabase_client import _get_client, get_knowledge_entries, get_storage_file_list

def cleanup_orphaned_knowledge_entries():
    client = _get_client()
    if not client:
        print("Could not connect to Supabase.")
        return

    print("Fetching entries from knowledge_base table...")
    entries = get_knowledge_entries()
    
    if not entries:
        print("No entries found in knowledge_base table.")
        return
        
    print(f"Found {len(entries)} entries in the database.")
    
    print("Fetching files from 'manuals' storage bucket...")
    files = get_storage_file_list("manuals", "manuals")
    
    actual_filenames = set()
    for f in files:
        name = f.get("name")
        if name and name != ".emptyFolderPlaceholder":
            actual_filenames.add(name)
            
    print(f"Found {len(actual_filenames)} actual files in storage.")
    
    deleted_count = 0
    for entry in entries:
        db_filename = entry.get("file_name")
        if db_filename not in actual_filenames:
            print(f"Orphaned record found: '{db_filename}'. Deleting from database...")
            
            try:
                result = client.table("knowledge_base").delete().eq("id", entry["id"]).execute()
                print(f"   Deleted record ID {entry['id']}")
                deleted_count += 1
            except Exception as e:
                print(f"   Failed to delete record ID {entry['id']}: {e}")
                
    if deleted_count > 0:
        print(f"\nCleanup complete! Removed {deleted_count} orphaned records.")
    else:
        print("\nDatabase is perfectly in sync with Storage. No orphans found.")

if __name__ == "__main__":
    cleanup_orphaned_knowledge_entries()
