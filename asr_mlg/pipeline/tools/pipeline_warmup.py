"""
Pipeline Warm-up Tool

This script initializes or updates the 'manifest.json' used by the incremental pipeline.
By calculating the semantic hash of all existing Excel corpus files, it allows the 
pipeline to:
1. Fast-Forward: Recognize that existing files haven't changed and skip reprocessing.
2. Synchronize: Align the build history of a new deployment with pre-existing data.
3. Audit: Track which files were used for a specific project build.
"""

import os
import json
import pandas as pd
import hashlib
import argparse
from datetime import datetime
from typing import Dict

def get_semantic_hash(file_path: str) -> str:
    """
    Calculates a hash based on actual text content rather than file metadata.
    This ensures that simply 'saving' an Excel file without changes won't trigger a rebuild.
    
    Priority Logic:
    1. ASR Templates: Sheets 'sent', 'shuofa', or '<>' (slot) columns.
    2. Standard Format: Sheet 0, column named 'text' or index 0.
    """
    try:
        xl = pd.ExcelFile(file_path)
        content_list = []
        has_special_sheet = False
        
        for sheet in xl.sheet_names:
            sheet_lower = sheet.lower()
            if 'sent' in sheet_lower or 'shuofa' in sheet_lower:
                has_special_sheet = True
                df = pd.read_excel(xl, sheet_name=sheet, header=None)
                vals = df.values.flatten()
                content_list.extend([str(x).strip() for x in vals if pd.notna(x) and str(x).strip()])
                
            elif '<>' in sheet:
                has_special_sheet = True
                df = pd.read_excel(xl, sheet_name=sheet)
                for col in df.columns:
                    col_name = str(col).strip()
                    if col_name.startswith('<') and col_name.endswith('>'):
                        vals = df[col].dropna().astype(str).str.strip().tolist()
                        content_list.extend([col_name] + vals)
                        
        # Fallback for standard non-templated Excel files
        if not has_special_sheet:
            df = pd.read_excel(xl, sheet_name=0)
            if 'text' in df.columns:
                vals = df['text'].dropna().astype(str).str.strip().tolist()
                content_list.extend(vals)
            else:
                vals = df.values.flatten()
                content_list.extend([str(x).strip() for x in vals if pd.notna(x) and str(x).strip()])
                
        if not content_list:
            raise ValueError("No text found.")
            
        # Combine all text and hash it
        content_str = "|".join(content_list)
        return hashlib.md5(content_str.encode('utf-8')).hexdigest()
        
    except Exception as e:
        # Fallback to binary MD5 if parsing fails
        print(f"[Warning] Parsing failed for {os.path.basename(file_path)}. Using binary hash.")
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

def warmup_manifest(corpus_dir: str, manifest_path: str, msg: str):
    """
    Scans a directory and populates the manifest JSON with hashes.
    """
    processed_state: Dict[str, dict] = {}
    
    # Load existing state to avoid re-hashing everything if called multiple times
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                processed_state = json.load(f)
        except Exception:
            print(f"[Warning] Could not load manifest at {manifest_path}.")

    print(f"Indexing corpus for project [{msg}] at: {corpus_dir}")
    count = 0
    skip_count = 0
    
    for root, _, files in os.walk(corpus_dir):
        for file in files:
            # Only track Excel files, skip temporary office lock files (~$)
            if file.endswith(".xlsx") and not file.startswith("~$"):
                file_path = os.path.join(root, file)
                content_hash = get_semantic_hash(file_path)
                file_key = file 
                
                # Check if file is already tracked with the same hash
                if file_key not in processed_state or processed_state[file_key].get("hash") != content_hash:
                    processed_state[file_key] = {
                        "hash": content_hash,
                        "file_path": os.path.abspath(file_path),
                        "task_msg": msg,
                        "processed_time": "WARMUP_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                    }
                    count += 1
                else:
                    skip_count += 1

    # Save the updated manifest
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(processed_state, f, indent=4, ensure_ascii=False)
    
    print(f"\nWarm-up Result: Indexed={count}, Skipped={skip_count}")
    print(f"Manifest saved to: {manifest_path}")

def main():
    parser = argparse.ArgumentParser(description="Warm-up script for incremental ASR builds.")
    parser.add_argument("-c", "--corpus_dir", required=True, help="Directory containing Excel corpus")
    parser.add_argument("-m", "--manifest_path", required=True, help="Output manifest.json path")
    parser.add_argument("--msg", required=True, help="Task name")
    
    args = parser.parse_args()
    if not os.path.exists(args.corpus_dir):
        sys.exit(1)
        
    warmup_manifest(args.corpus_dir, args.manifest_path, args.msg)

if __name__ == "__main__":
    main()
