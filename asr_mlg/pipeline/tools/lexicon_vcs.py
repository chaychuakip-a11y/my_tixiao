"""
Lexicon Version Control System (VCS)

This tool provides basic versioning and rollback capabilities for ASR dictionary files (lexicons).
Since lexicons are frequently modified during G2P merging, this script ensures:
1. Safety: Automatic snapshots are taken before every merge.
2. Traceability: Every modification is logged with task ID, language ID, and diff statistics.
3. Disk Efficiency: Automatically prunes old backups to maintain a fixed historical depth.
4. Resilience: Quick rollback to a specific MD5 hash if a merge causes regressions.
"""

import os
import sys
import shutil
import hashlib
import argparse
import glob
from datetime import datetime
from typing import Set

class LexiconVCS:
    """
    Core VCS manager for a specific dictionary file.
    Operates in a hidden '.history' folder relative to the target file.
    """
    def __init__(self, dict_path: str, max_versions: int = 10):
        self.dict_path = os.path.abspath(dict_path)
        self.work_dir = os.path.dirname(self.dict_path)
        self.dict_name = os.path.basename(self.dict_path)
        self.history_dir = os.path.join(self.work_dir, ".history")
        self.log_file = os.path.join(self.history_dir, "history.log")
        self.max_versions = max_versions
        
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)

    def _get_md5(self, file_path: str) -> str:
        """Calculates a short 7-character MD5 hash for identification."""
        if not os.path.exists(file_path):
            return "0000000"
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()[:7]

    def _get_latest_backup(self) -> str:
        """Retrieves the path of the most recently created backup file."""
        pattern = os.path.join(self.history_dir, f"{self.dict_name}.v*.bak")
        backups = sorted(glob.glob(pattern))
        return backups[-1] if backups else ""

    def _load_vocab(self, file_path: str) -> Set[str]:
        """Loads the first column (words) of the dictionary into a set for fast comparison."""
        vocab = set()
        if not os.path.exists(file_path):
            return vocab
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if parts:
                    vocab.add(parts[0])
        return vocab

    def pre_merge(self) -> bool:
        """
        Creates a timestamped snapshot of the dictionary. 
        Must be called BEFORE any merge operation.
        """
        # Initialize an empty file if the dictionary doesn't exist yet
        if not os.path.exists(self.dict_path):
            open(self.dict_path, 'w', encoding='utf-8').close()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_hash = self._get_md5(self.dict_path)
        backup_name = f"{self.dict_name}.v{timestamp}.{file_hash}.bak"
        backup_path = os.path.join(self.history_dir, backup_name)

        shutil.copy2(self.dict_path, backup_path)
        print(f"Pre-merge snapshot created: {backup_path}")
        return True

    def post_merge(self, task_msg: str, lang_id: str) -> bool:
        """
        Analyzes the result of a merge, logs statistics, and prunes old versions.
        Must be called AFTER a successful merge operation.
        """
        latest_bak = self._get_latest_backup()
        if not latest_bak:
            print("Error: No pre-merge backup found to compare against.", file=sys.stderr)
            return False

        # Calculate exact differences (new words added)
        old_vocab = self._load_vocab(latest_bak)
        new_vocab = self._load_vocab(self.dict_path)
        
        added_words = new_vocab - old_vocab
        added_count = len(added_words)
        total_count = len(new_vocab)
        
        new_hash = self._get_md5(self.dict_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Log entry for the task history
        log_entry = (
            f"[{timestamp}] TASK: {task_msg} | LANG: {lang_id} | "
            f"HASH: {new_hash} | TOTAL_WORDS: {total_count} | "
            f"ADDED_WORDS: {added_count}\n"
        )
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
            
        print(f"Post-merge log updated. Added {added_count} words.")
        
        # Prune old versions to save disk space
        self._prune()
        return True

    def _prune(self):
        """Maintains the history depth by deleting the oldest backups and log lines."""
        pattern = os.path.join(self.history_dir, f"{self.dict_name}.v*.bak")
        backups = sorted(glob.glob(pattern))
        
        if len(backups) <= self.max_versions:
            return
            
        # Delete files
        backups_to_delete = backups[:-self.max_versions]
        for bak in backups_to_delete:
            os.remove(bak)
            
        # Truncate log file to prevent it from growing indefinitely
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            lines_to_keep = self.max_versions * 2 
            if len(lines) > lines_to_keep:
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-lines_to_keep:])
                    
        print(f"Pruned {len(backups_to_delete)} old snapshots. Kept latest {self.max_versions}.")

    def log(self):
        """CLI: Displays the recent modification history."""
        if not os.path.exists(self.log_file):
            print("No version history found.")
            return

        print(f"\n=== Version History for {self.dict_name} ===")
        with open(self.log_file, "r", encoding="utf-8") as f:
            print(f.read().strip())
        print("=========================================\n")

    def rollback(self, target_hash: str) -> bool:
        """
        CLI: Restores the dictionary to a specific version identified by its MD5 hash.
        A safety snapshot is taken of the current (broken) state before overriding.
        """
        pattern = os.path.join(self.history_dir, f"{self.dict_name}.v*.{target_hash}.bak")
        matches = glob.glob(pattern)

        if not matches:
            print(f"Error: No snapshot found matching hash '{target_hash}'", file=sys.stderr)
            return False

        if len(matches) > 1:
            print(f"Error: Multiple snapshots found for hash '{target_hash}'. Collision detected.", file=sys.stderr)
            return False

        backup_path = matches[0]
        
        # Save current state as a 'Rollback Safety' point
        self.pre_merge()

        shutil.copy2(backup_path, self.dict_path)
        print(f"VCS Rollback successful. Restored to hash: {target_hash}")
        
        # Record the rollback event
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] ROLLBACK | Restored to Hash: {target_hash}\n")
            
        return True

def main():
    parser = argparse.ArgumentParser(description="Lexicon Version Control System CLI")
    parser.add_argument("-i", "--input", type=str, required=True, help="Absolute path to the dictionary file")
    parser.add_argument("action", choices=["pre_merge", "post_merge", "rollback", "log"], help="Lifecycle or intervention action")
    parser.add_argument("-m", "--msg", type=str, default="UnknownTask", help="Task message identifier")
    parser.add_argument("-l", "--lang", type=str, default="0", help="Language ID")
    parser.add_argument("-t", "--target_hash", type=str, help="Target MD5 hash to restore (for rollback)")
    parser.add_argument("--max_versions", type=int, default=10, help="Max history versions to retain")

    args = parser.parse_args()
    vcs = LexiconVCS(args.input, args.max_versions)

    if args.action == "pre_merge":
        vcs.pre_merge()
    elif args.action == "post_merge":
        vcs.post_merge(args.msg, args.lang)
    elif args.action == "log":
        vcs.log()
    elif args.action == "rollback":
        if not args.target_hash:
            print("Error: --target_hash (-t) is required for rollback.", file=sys.stderr)
            sys.exit(1)
        vcs.rollback(args.target_hash)

if __name__ == "__main__":
    main()
