"""
Lexicon Merge Tool

This script merges newly predicted phonemes (typically from G2P) into an existing base dictionary.
It enforces strict validation to ensure the integrity of the ASR system:
1. Deduplication: Prevents adding identical word-pronunciation pairs.
2. Format Enforcement: Validates the 'word\tphone1 phone2' structure.
3. Phoneme Validation: Compares every predicted phoneme against the project's official 'phones.syms'.
   Any word containing an 'illegal' phoneme is rejected to prevent model crashes during training.
"""

import argparse
import sys
import os

def load_valid_phones(syms_path: str) -> set:
    """
    Loads the set of allowed phonemes for the current language.
    Used to catch G2P hallucination or model-incompatible symbols.
    """
    valid_phones = set()
    if not os.path.exists(syms_path):
        print(f"Warning: phones.syms not found at {syms_path}. Validation skipped.", file=sys.stderr)
        return valid_phones
    
    with open(syms_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()
            if parts:
                valid_phones.add(parts[0])
    return valid_phones

def merge_dictionaries(base_dict_path: str, new_dict_path: str, syms_path: str):
    """
    Appends valid entries from new_dict to base_dict.
    Preserves existing entries and order.
    """
    valid_phones = load_valid_phones(syms_path)
    existing_entries = set() # Stores "word\tphones" for O(1) deduplication
    base_lines = []
    
    # 1. Load the existing base dictionary into memory
    if os.path.exists(base_dict_path):
        with open(base_dict_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\r\n')
                if not line: continue
                parts = line.split('\t')
                if len(parts) == 2:
                    # Record the exact pronunciation entry
                    existing_entries.add(f"{parts[0]}\t{parts[1].strip()}")
                base_lines.append(line)
                
    # 2. Process and validate the new entries
    added_count = 0
    skip_duplicate = 0
    skip_format = 0
    skip_abnormal_phone = 0
    
    with open(new_dict_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if not line: continue
                
            # Basic structural check
            parts = line.split('\t')
            if len(parts) != 2:
                skip_format += 1
                continue
                
            word, phones_str = parts[0], parts[1].strip()
            entry_key = f"{word}\t{phones_str}"
            
            # Skip if this exact word-pronunciation pair already exists
            if entry_key in existing_entries:
                skip_duplicate += 1
                continue
                
            # Verify every phoneme against the project phoneset
            phones = phones_str.split(' ')
            if valid_phones:
                invalid_phones = [p for p in phones if p not in valid_phones]
                if invalid_phones:
                    print(f"[REJECTED] Abnormal Phone(s) {invalid_phones} in '{word}'.", file=sys.stderr)
                    skip_abnormal_phone += 1
                    continue
            
            # Entry passed all checks; add to the list
            base_lines.append(entry_key)
            existing_entries.add(entry_key)
            added_count += 1
            
    # 3. Commit changes back to disk with Linux-style newlines
    with open(base_dict_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(base_lines) + '\n')
        
    print(f"Merge Results: Added={added_count}, Dups={skip_duplicate}, FormatErr={skip_format}, IllegalPhone={skip_abnormal_phone}")
    
    
def main():
    parser = argparse.ArgumentParser(description="Merges G2P results into the primary ASR lexicon.")
    parser.add_argument("-i", "--input_new", required=True, help="New dictionary file (G2P output)")
    parser.add_argument("-o", "--output_base", required=True, help="Target base dictionary file")
    parser.add_argument("-p", "--phone_syms", required=True, help="Project phoneset symbols file")
    args = parser.parse_args()
    
    merge_dictionaries(args.output_base, args.input_new, args.phone_syms)

if __name__ == "__main__":
    main()
