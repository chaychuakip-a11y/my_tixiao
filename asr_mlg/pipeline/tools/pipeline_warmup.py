"""
Pipeline Warm-up Tool

This script initializes or updates the per-task manifest JSON used by the incremental pipeline.
By calculating the semantic hash of all existing Excel corpus files, it allows the
pipeline to:
1. Fast-Forward: Recognize that existing files haven't changed and skip reprocessing.
2. Synchronize: Align the build history of a new deployment with pre-existing data.
3. Audit: Track which files were used for a specific project build.

Usage (single task):
    python pipeline_warmup.py -c <corpus_dir> -m <manifest.json> --msg <task_name>

Usage (all tasks from job.yaml):
    python pipeline_warmup.py -j <job.yaml> [-g <global_config.yaml>] [--dry-run]
"""

import os
import sys
import json
import hashlib
import argparse
from datetime import datetime
from pathlib import Path
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
        import pandas as pd

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

        content_str = "|".join(content_list)
        return hashlib.md5(content_str.encode('utf-8')).hexdigest()

    except Exception:
        print(f"[Warning] Parsing failed for {os.path.basename(file_path)}. Using binary hash.")
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()


def warmup_manifest(corpus_dir: str, manifest_path: str, msg: str, dry_run: bool = False):
    """
    Scans a corpus directory and populates the manifest JSON with semantic hashes.
    Manifest key = filename only (matches pipeline_executor.py DeltaTracker strategy).
    """
    processed_state: Dict[str, dict] = {}

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                processed_state = json.load(f)
        except Exception:
            print(f"[Warning] Could not load manifest at {manifest_path}.")

    print(f"  corpus  : {corpus_dir}")
    print(f"  manifest: {manifest_path}")

    if not os.path.exists(corpus_dir):
        print(f"  [WARN] corpus path not found, skipping.")
        return

    count = 0
    skip_count = 0

    for root, _, files in os.walk(corpus_dir):
        for file in sorted(files):
            if not file.endswith(".xlsx") or file.startswith("~$"):
                continue
            file_path = os.path.join(root, file)
            content_hash = get_semantic_hash(file_path)
            file_key = file

            if file_key in processed_state and processed_state[file_key].get("hash") == content_hash:
                skip_count += 1
                continue

            if dry_run:
                print(f"  [dry-run] would index: {file}")
            else:
                processed_state[file_key] = {
                    "hash": content_hash,
                    "file_path": os.path.abspath(file_path),
                    "task_msg": msg,
                    "processed_time": "WARMUP_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                }
            count += 1

    if not dry_run and count > 0:
        os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(processed_state, f, indent=4, ensure_ascii=False)

    print(f"  result  : indexed={count}, skipped={skip_count}")


def load_language_map(lang_map_path: str) -> dict:
    lang_map = {}
    if os.path.exists(lang_map_path):
        with open(lang_map_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    k, v = line.split(':', 1)
                    lang_map[k.strip()] = v.strip().lower()
    return lang_map


def run_from_job(job_path: str, cfg_path: str, dry_run: bool = False):
    """
    Iterates all tasks in job.yaml that have enable_testset: true and warms up
    their per-task manifest ({lang_name}_{msg}_testset_manifest.json).
    Path resolution mirrors pipeline_executor.py:resolve_and_bind_paths.
    """
    import yaml

    job = yaml.safe_load(open(job_path, encoding='utf-8'))

    # Default config search: pipeline/config/global_config.yaml (relative to this script)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not cfg_path:
        default_cfg = os.path.join(script_dir, '..', 'config', 'global_config.yaml')
        if os.path.exists(default_cfg):
            cfg_path = os.path.abspath(default_cfg)
            print(f"[INFO] global_config     : {cfg_path} (auto-detected)")
        else:
            print(f"[INFO] global_config     : not found, using defaults")

    cfg = yaml.safe_load(open(cfg_path, encoding='utf-8')) if cfg_path and os.path.exists(cfg_path) else {}

    # Derive asrmlg_exp_dir from script location (pipeline/tools/ -> up 2 levels -> asr_mlg/)
    # This mirrors pipeline_executor.py which uses its own __file__ as the anchor,
    # NOT the job.yaml location which can be anywhere.
    asrmlg_exp_dir = cfg.get('asrmlg_exp_dir') or os.path.abspath(os.path.join(script_dir, '..', '..'))
    if not os.path.isabs(asrmlg_exp_dir):
        asrmlg_exp_dir = os.path.abspath(asrmlg_exp_dir)

    raw_output_dir = cfg.get('output_dir') or os.path.join(asrmlg_exp_dir, 'output')
    output_dir     = raw_output_dir if os.path.isabs(raw_output_dir) else os.path.join(asrmlg_exp_dir, raw_output_dir)

    print(f"[INFO] asrmlg_exp_dir : {asrmlg_exp_dir}")
    print(f"[INFO] output_dir     : {output_dir}")

    lang_map_name = cfg.get('language_map_name', 'language_map')
    lang_map = load_language_map(os.path.join(asrmlg_exp_dir, lang_map_name))

    tasks = [t for t in job.get('tasks', []) if t.get('enable_testset')]
    if not tasks:
        print("[INFO] No tasks with 'enable_testset: true' found.")
        return

    print(f"\n=== pipeline warmup: {len(tasks)} task(s) ===\n")

    for task in tasks:
        msg        = str(task.get('msg', '')).strip()
        lang_id    = str(task.get('l', '')).strip()
        excel_path = str(task.get('excel_corpus_path', '')).strip()

        if not msg or not excel_path:
            continue
        if not os.path.isabs(excel_path):
            excel_path = os.path.join(asrmlg_exp_dir, excel_path)

        lang_name = lang_map.get(lang_id)
        if not lang_name:
            print(f"[WARN] lang_id '{lang_id}' not found in language_map, skipping task '{msg}'. "
                  f"Check the 'l' field in job.yaml and the language_map file.")
            continue
        manifest_path = os.path.join(output_dir, 'test_sets', f"{lang_name}_{msg}_testset_manifest.json")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] task: {msg}")
        warmup_manifest(excel_path, manifest_path, msg, dry_run=dry_run)
        print()

    print("=== warmup complete ===")


def main():
    parser = argparse.ArgumentParser(description="Warm-up script for incremental ASR testset builds.")

    # Mode 1: job-level (reads job.yaml + global_config.yaml)
    parser.add_argument("-j", "--job",           default=None, help="Path to job.yaml (iterates all enable_testset tasks)")
    parser.add_argument("-g", "--global_config", default=None, help="Path to global_config.yaml (optional)")

    # Mode 2: single-task (original interface)
    parser.add_argument("-c", "--corpus_dir",    default=None, help="Directory containing Excel corpus")
    parser.add_argument("-m", "--manifest_path", default=None, help="Output manifest.json path")
    parser.add_argument("--msg",                 default=None, help="Task name")

    parser.add_argument("--dry-run", action="store_true", help="Print what would be processed without writing")

    args = parser.parse_args()

    if args.job:
        run_from_job(args.job, args.global_config or "", dry_run=args.dry_run)
    elif args.corpus_dir and args.manifest_path and args.msg:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] task: {args.msg}")
        warmup_manifest(args.corpus_dir, args.manifest_path, args.msg, dry_run=args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
