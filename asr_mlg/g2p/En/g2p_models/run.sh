#!/usr/bin/env python3
"""
G2P (Grapheme-to-Phoneme) script for English using CMU Dictionary.
Reads words from input.txt and outputs pronunciations to output.dict.
"""

import sys
import os

# Add project root to path for cmudict
sys.path.insert(0, '/home/lty/my_tixiao')

import cmudict

def eng_g2p(word):
    """Convert English word to phonemes using CMUdict."""
    word_lower = word.strip().lower()

    # Check in cmudict
    if word_lower in cmudict.dict():
        phones_list = cmudict.dict()[word_lower]
        if phones_list:
            # Return first pronunciation, join phones with spaces
            phones = ' '.join(phones_list[0])
            return phones

    # If not found, try without stress markers
    for entry, pronunciations in cmudict.entries():
        if entry.lower() == word_lower:
            phones = ' '.join(pronunciations[0])
            # Remove stress numbers (0, 1, 2)
            phones_clean = ''.join([c for c in phones if not c.isdigit()])
            return phones_clean

    return None

def main():
    input_file = 'input.txt'
    output_file = 'output.dict'

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found", file=sys.stderr)
        sys.exit(1)

    output_lines = []
    skipped = []

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            word = line.strip()
            if not word:
                continue

            phones = eng_g2p(word)
            if phones:
                output_lines.append(f"{word}\t{phones}")
            else:
                skipped.append(word)

    with open(output_file, 'w', encoding='utf-8') as f:
        for line in output_lines:
            f.write(line + '\n')

    print(f"G2P completed: {len(output_lines)} success, {len(skipped)} skipped")
    if skipped:
        print(f"Skipped words: {skipped[:10]}...")

if __name__ == '__main__':
    main()
