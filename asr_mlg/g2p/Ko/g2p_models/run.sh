#!/usr/bin/env python3
"""
G2P (Grapheme-to-Phoneme) script for Korean using epitran.
Reads words from input.txt and outputs pronunciations to output.dict.
"""

import sys
import os

def main():
    input_file = 'input.txt'
    output_file = 'output.dict'

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found", file=sys.stderr)
        sys.exit(1)

    try:
        import epitran
        epi = epitran.Epitran('kor-Hang')
    except Exception as e:
        print(f"Error loading Korean G2P: {e}", file=sys.stderr)
        sys.exit(1)

    output_lines = []
    skipped = []

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            word = line.strip()
            if not word:
                continue

            try:
                phones = epi.transliterate(word)
                if phones:
                    phones_clean = phones.replace(' ', '')
                    output_lines.append(f"{word}\t{phones_clean}")
                else:
                    skipped.append(word)
            except Exception as e:
                skipped.append(word)

    with open(output_file, 'w', encoding='utf-8') as f:
        for line in output_lines:
            f.write(line + '\n')

    print(f"G2P completed: {len(output_lines)} success, {len(skipped)} skipped")
    if skipped:
        print(f"Skipped words: {skipped[:10]}...")

if __name__ == '__main__':
    main()
