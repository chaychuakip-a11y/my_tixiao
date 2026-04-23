"""
ASR Pipeline Executor

This script serves as the central orchestrator for the ASR (Automatic Speech Recognition) 
resource building and evaluation pipeline. It automates three main phases:
- Phase 1: Resource Build & G2P (OOV extraction, phoneme prediction, lexicon merging, and WFST packaging).
- Phase 2: Incremental Testset Generation (Semantic hash-based delta tracking, TTS synthesis).
- Phase 3: Baseline Evaluation (Performance testing of built models).

Key features:
- Zero-config path deduction: Automatically locates project roots and models.
- Concurrency: Parallel processing of tasks and files using ProcessPool and ThreadPool.
- Global Lock: Synchronized G2P execution to prevent engine resource contention.
"""

import argparse
import configparser
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import random
import re
import pandas as pd
import yaml

# =============================================================================
# Utility Functions
# =============================================================================

def get_file_md5_suffix(file_path: str, suffix_len: int = 4) -> str:
    """
    Calculates the MD5 hash of a file and returns the last N characters.
    Used for generating unique, traceable filenames for model binaries.
    """
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        # Read in 4MB chunks for efficiency with large binary files
        for chunk in iter(lambda: f.read(4096 * 1024), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()[-suffix_len:]


def load_language_map(file_path: str) -> dict:
    """
    Loads a key-value language mapping (e.g., "26: En") from a text file.
    Used to resolve numeric language IDs to their string abbreviations.
    """
    if not os.path.exists(file_path):
        print(f"[error] language map file not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    lang_map = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or ':' not in line:
                continue
            k, v = line.split(':', 1)
            lang_map[k.strip()] = v.strip().lower()
    return lang_map


def run_subprocess(cmd: List[str], cwd: str, log_file: str, env: Optional[Dict[str, str]] = None, verbose: bool = False) -> bool:
    """
    Standardized wrapper for executing shell commands and binary tools.
    - Redirects stdout/stderr to a dedicated log file.
    - verbose=True: also streams each output line to terminal in real-time.
    - Injects optional environment variables (e.g., LD_LIBRARY_PATH).
    """
    # If log_file points to a directory (nested dir issue), append a default filename
    if os.path.isdir(log_file):
        log_file = os.path.join(log_file, "pipeline.log")

    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] CMD: {' '.join(cmd)}\n")
            f.flush()
            if verbose:
                process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, env=env)
                for line in process.stdout:
                    text = line.decode('utf-8', errors='replace')
                    f.write(text)
                    f.flush()
                    print(f"  {text}", end='')
                process.wait()
            else:
                process = subprocess.Popen(cmd, cwd=cwd, stdout=f,
                                           stderr=subprocess.STDOUT, env=env)
                process.wait()
            return process.returncode == 0
    except Exception as e:
        fallback_log = log_file + ".err" if not os.path.isdir(log_file) else os.path.join(log_file, "error.log")
        with open(fallback_log, 'a') as f:
            f.write(f"\n[fatal error] {str(e)}\n")
        return False


def run_tts_with_progress(cmd: List[str], cwd: str, log_file: str) -> bool:
    """
    Runs make_test_set.py and renders a tqdm progress bar by parsing
    [PROGRESS] done/total markers emitted to its stdout.
    Other output lines are written to log_file only.
    """
    from tqdm import tqdm

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_file, 'a', encoding='utf-8') as f_log:
            process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
            pbar = None
            for raw in process.stdout:
                text = raw.decode('utf-8', errors='replace')
                m = re.match(r'\[PROGRESS\]\s*(\d+)/(\d+)', text.strip())
                if m:
                    done, total = int(m.group(1)), int(m.group(2))
                    if pbar is None:
                        pbar = tqdm(total=total, desc="  TTS", unit="sent",
                                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
                    pbar.n = done
                    pbar.refresh()
                else:
                    f_log.write(text)
                    f_log.flush()
            process.wait()
            if pbar is not None:
                pbar.close()
        return process.returncode == 0
    except Exception as e:
        with open(log_file, 'a') as f:
            f.write(f"\n[fatal error] {str(e)}\n")
        return False


def resolve_and_bind_paths(global_cfg: dict, base_path: str) -> dict:
    """
    Implements 'Zero-Config' logic by deducing paths based on script location.
    
    Logic:
    1. Base Project Dir: Assumed to be the parent of the 'pipeline/' directory.
    2. Output Dir: Defaults to 'output/' inside project root.
    3. G2P Root: Defaults to 'g2p/' inside project root.
    4. Tools: Defaults to 'pipeline/tools/'.
    """
    py_exec = global_cfg.get('python_exec')
    if not py_exec:
        global_cfg['python_exec'] = sys.executable
    elif not os.path.isabs(py_exec):
        global_cfg['python_exec'] = os.path.abspath(os.path.join(base_path, py_exec))

    # [Smart Default] asrmlg_exp_dir -> parent of pipeline/
    if 'asrmlg_exp_dir' not in global_cfg:
        global_cfg['asrmlg_exp_dir'] = os.path.abspath(os.path.join(base_path, '..'))
    elif not os.path.isabs(global_cfg['asrmlg_exp_dir']):
        global_cfg['asrmlg_exp_dir'] = os.path.abspath(os.path.join(base_path, global_cfg['asrmlg_exp_dir']))

    # [Smart Default] output_dir -> asrmlg_exp_dir/output
    if 'output_dir' not in global_cfg:
        global_cfg['output_dir'] = os.path.join(global_cfg['asrmlg_exp_dir'], 'output')
    elif not os.path.isabs(global_cfg['output_dir']):
        global_cfg['output_dir'] = os.path.abspath(os.path.join(global_cfg['asrmlg_exp_dir'], global_cfg['output_dir']))

    # [Smart Default] log_dir -> output_dir/logs
    if 'log_dir' not in global_cfg:
        global_cfg['log_dir'] = os.path.join(global_cfg['output_dir'], 'logs')
    elif not os.path.isabs(global_cfg['log_dir']):
        global_cfg['log_dir'] = os.path.abspath(os.path.join(base_path, global_cfg['log_dir']))

    # [Smart Default] tools_dir -> pipeline/tools
    if 'tools_dir' not in global_cfg:
        global_cfg['tools_dir'] = os.path.join(base_path, 'tools')

    # [Smart Default] g2p_root_dir -> pipeline/g2p
    if 'g2p_root_dir' not in global_cfg:
        global_cfg['g2p_root_dir'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'g2p')

    # [Smart Default] resource mapping for different is_yun modes
    if 'res_dir_map' not in global_cfg:
        global_cfg['res_dir_map'] = {'0': 'ubctc_duan', '1': 'rnnt_ctc_duan', '2': 'rnnt_ed_duan', '3': 'yun'}
    if 'lang_abbr_map' not in global_cfg:
        global_cfg['lang_abbr_map'] = {'26': 'En', '5': 'En', '69160': 'Ja', '69500': 'Ko', '69400': 'Th'}
    if 'res_dir_name' not in global_cfg:
        global_cfg['res_dir_name'] = 'res'
    if 'scheme_map' not in global_cfg:
        global_cfg['scheme_map'] = {'0': 'ubctc', '1': 'rnntCTC', '2': 'rnnt_ed', '3': 'yun'}

    # [Smart Default] script names relative to base_path or project root
    defaults = {
        'train_script': 'corpus_process_package.py',
        'merge_dict_script': os.path.join(base_path, 'tools/merge_dict.py'),
        'eval_script': 'evaluate.py'
    }
    for key, default_val in defaults.items():
        if key not in global_cfg:
            global_cfg[key] = default_val

    # Ensure all local paths are absolute and bound correctly
    local_keys = [
        'g2p_root_dir', 'tools_dir', 'merge_dict_script',
        'adapter_script', 'test_script', 'eval_script', 'train_script',
        'g2p_replacement_list'
    ]
    for key in local_keys:
        val = global_cfg.get(key)
        if val and not os.path.isabs(val):
            if key in ['tools_dir', 'merge_dict_script', 'g2p_root_dir', 'g2p_replacement_list']:
                global_cfg[key] = os.path.abspath(os.path.join(base_path, val))
            else:
                global_cfg[key] = os.path.abspath(os.path.join(global_cfg['asrmlg_exp_dir'], val))

    return global_cfg


# =============================================================================
# Delta Tracker Logic
# =============================================================================

class DeltaTracker:
    """
    Incremental processing engine that tracks changes in Excel corpus files.
    Calculates a 'semantic hash' (content-based) to decide if a file needs reprocessing.
    """

    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        self.history = self._load_manifest()

    def _load_manifest(self) -> dict:
        """Loads the JSON manifest containing file hashes from previous runs."""
        if os.path.isdir(self.manifest_path):
            print(f"[warning] manifest path is a directory, ignoring: {self.manifest_path}")
            return {}
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    @staticmethod
    def get_semantic_hash(file_path: str) -> str:
        """
        Calculates a semantic hash by extracting text content from specific Excel sheets.
        This ignores metadata changes (like last saved time) and focuses only on actual corpus data.
        """
        try:
            import pandas as pd
            import hashlib
            
            xl = pd.ExcelFile(file_path)
            content_list = []
            has_special_sheet = False

            # Specific sheets for ASR: 'sent', 'shuofa', or columns starting with '<'
            for sheet in xl.sheet_names:
                sheet_lower = sheet.lower()
                
                if 'sent' in sheet_lower or 'shuofa' in sheet_lower:
                    has_special_sheet = True
                    df = pd.read_excel(xl, sheet_name=sheet, header=None)
                    vals = df.values.flatten()
                    content_list.extend([
                        str(x).strip() for x in vals
                        if pd.notna(x) and str(x).strip()
                    ])
                    
                elif '<>' in sheet:
                    has_special_sheet = True
                    df = pd.read_excel(xl, sheet_name=sheet)
                    for col in df.columns:
                        col_name = str(col).strip()
                        if col_name.startswith('<') and col_name.endswith('>'):
                            vals = df[col].dropna().astype(str).str.strip().tolist()
                            content_list.extend([col_name] + vals)

            # Fallback to first sheet if no special patterns found
            if not has_special_sheet:
                df = pd.read_excel(xl, sheet_name=0)
                if 'text' in df.columns:
                    vals = df['text'].dropna().astype(str).str.strip().tolist()
                    content_list.extend(vals)
                else:
                    vals = df.values.flatten()
                    content_list.extend([str(x).strip() for x in vals if pd.notna(x) and str(x).strip()])

            if not content_list:
                raise ValueError("no valid text content found.")

            content_str = "|".join(content_list)
            return hashlib.md5(content_str.encode('utf-8')).hexdigest()

        except Exception:
            # Fallback to binary hash if Excel parsing fails
            import hashlib
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()

    def save(self):
        """Persists current build state to the manifest file."""
        if os.path.isdir(self.manifest_path):
            print(f"[warning] cannot save manifest, path is a directory: {self.manifest_path}")
            return
        Path(self.manifest_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4, ensure_ascii=False)
            
    def update_history(self, key: str, new_hash: str):
        """Updates the internal hash dictionary. key is basename of file or directory."""
        self.history[key] = {
            "hash": new_hash,
            "processed_time": datetime.now().strftime("%Y%m%d_%H%M%S")
        }


# =============================================================================
# Phase 1: Resource Build & G2P
# =============================================================================

def generate_context_for_hebrew_oov(oov_file_path: str, corpus_dir: str, g2p_input_txt: str, target_encoding: str, target_newline: str):
    """
    Specialized G2P preparation for Hebrew.
    Hebrew G2P is context-sensitive; this function finds or generates context sentences 
    for OOV words by scanning existing Excel corpus.
    """
    with open(oov_file_path, 'r', encoding='utf-8') as f:
        oov_list = [line.strip() for line in f if line.strip()]

    if not oov_list:
        return

    sent_list = []
    shuofa_list = []
    slot_dict = {}

    # Read and parse all Excel files in the corpus directory
    if os.path.exists(corpus_dir):
        for file in os.listdir(corpus_dir):
            if not file.endswith('.xlsx') or file.startswith('~'):
                continue
            try:
                xl = pd.ExcelFile(os.path.join(corpus_dir, file))
                has_special = False
                for sheet in xl.sheet_names:
                    sheet_lower = sheet.lower()
                    if 'sent' in sheet_lower:
                        has_special = True
                        df = pd.read_excel(xl, sheet_name=sheet, header=None)
                        sent_list.extend([str(x).strip() for x in df.values.flatten() if pd.notna(x)])
                    elif 'shuofa' in sheet_lower:
                        has_special = True
                        df = pd.read_excel(xl, sheet_name=sheet, header=None)
                        shuofa_list.extend([str(x).strip() for x in df.values.flatten() if pd.notna(x)])
                    elif '<>' in sheet:
                        has_special = True
                        df = pd.read_excel(xl, sheet_name=sheet)
                        for col in df.columns:
                            col_name = str(col).strip()
                            if col_name.startswith('<') and col_name.endswith('>'):
                                if col_name not in slot_dict:
                                    slot_dict[col_name] = []
                                slot_dict[col_name].extend(df[col].dropna().astype(str).str.strip().tolist())
                if not has_special:
                    df = pd.read_excel(xl, sheet_name=0)
                    if 'text' in df.columns:
                        sent_list.extend(df['text'].dropna().astype(str).str.strip().tolist())
                    else:
                        sent_list.extend(df.iloc[:, 0].dropna().astype(str).str.strip().tolist())
            except Exception:
                continue

    output_lines = []
    for oov in oov_list:
        matched = False
        
        # Priority 1: Direct match in standard sentences
        for sent in sent_list:
            if oov in sent:
                output_lines.append(sent)
                matched = True
                break
        if matched: continue

        # Priority 2: Slot-based synthesis (map OOV to a template)
        for slot_name, slot_values in slot_dict.items():
            if oov in slot_values:
                valid_shuofas = [s for s in shuofa_list if slot_name in s]
                if valid_shuofas:
                    chosen_shuofa = random.choice(valid_shuofas)
                    context_sent = chosen_shuofa.replace(slot_name, oov)
                    # Fill other slots with random valid values to make a complete sentence
                    for other_slot, other_values in slot_dict.items():
                        if other_slot != slot_name and other_slot in context_sent and other_values:
                            context_sent = context_sent.replace(other_slot, random.choice(other_values))
                    context_sent = re.sub(r'<[^>]+>', '', context_sent)
                    output_lines.append(context_sent)
                    matched = True
                    break
        
        # Fallback: Just the word itself
        if not matched:
            output_lines.append(oov)

    with open(g2p_input_txt, 'w', encoding=target_encoding, newline=target_newline) as f_out:
        for line in output_lines:
            f_out.write(f"{line}{target_newline}")


def build_base_command(task: dict, python_exec: str, train_script: str, asrmlg_exp_dir: str) -> List[str]:
    """
    Dynamically constructs the CLI command for the underlying ASR-MLG core scripts.
    Handles parameter prefixing (- vs --) and path normalization.
    """
    base_cmd = [
        python_exec if train_script.endswith('.py') else "bash",
        train_script
    ]

    # Parameters that use a single dash (legacy format)
    single_dash_whitelist = {'l', 'G', 'cp', 'np'}
    
    # Internal keys used by the pipeline but NOT passed to the core scripts
    internal_keys = {
        'enable_g2p', 'enable_merge_dict', 'enable_testset', 'enable_eval',
        'input_wav', 'output', 'only_corpus_process', 'enable_whisper_package', 'whisper_config',
        'language'  # pipeline metadata, not passed to corpus_process_package
    }

    # Keys that represent paths needing absolute resolution
    path_keys = {
        'excel_corpus_path', 'norm_excel_corpus_path',
        'norm_train_data_slot', 'norm_train_data_shuofa', 'np',
        'train_data_slot', 'train_data_shuofa', 'cp',
        'word_syms', 'phone_syms', 'triphone_syms', 'dict',
        'hmm_list', 'hmm_list_blank', 'mapping'
    }

    for key, val in task.items():
        if key in internal_keys or val is None:
            continue
            
        if key in single_dash_whitelist:
            prefix = f"-{key}"
        else:
            prefix = f"--{key}" if len(key) > 1 else f"-{key}"

        if isinstance(val, bool):
            if val:
                base_cmd.append(prefix)
            continue

        if key in path_keys and isinstance(val, str) and not os.path.isabs(val):
            val = os.path.join(asrmlg_exp_dir, val)

        base_cmd.extend([prefix, str(val)])

    return base_cmd


def step1_extract_oov(base_cmd: List[str], task_out_path: str, msg: str,
                      asrmlg_exp_dir: str, log_file: str) -> bool:
    """
    Step 1: Runs the corpus process in OOV extraction mode.
    Does not build the model; only identifies words missing from the current dictionary.
    """
    task_out_path_temp = task_out_path + "_temp"
    cmd = base_cmd + ["--only_corpus_process", "--output", task_out_path_temp]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] STARTING: phase1_step1 (extract oov) for {msg}")
    return run_subprocess(cmd, asrmlg_exp_dir, log_file)


def step2_g2p_predict(task: dict, global_cfg: dict, msg: str, task_out_path: str, log_file: str) -> bool:
    """
    Step 2: Predicts phonemes for OOV words.
    Uses fcntl locking to ensure that multiple parallel tasks don't overwrite the G2P engine files.
    """
    lang_abbr_map = global_cfg.get('lang_abbr_map', {})
    task_out_path_temp = task_out_path + "_temp"
    oov_file_path = Path(task_out_path_temp) / "custom_corpus_process" / "dict_dir" / "aaa_oov_base_dict"

    # Skip if no OOVs were found in Step 1
    if not oov_file_path.exists() or oov_file_path.stat().st_size == 0:
        return True

    lang_id = str(task.get('l', ''))
    lang_abbr = lang_abbr_map.get(lang_id) or str(task.get('language', msg))
    g2p_lang_dir = Path(global_cfg.get('g2p_root_dir', '')) / str(lang_abbr) / "g2p_models"

    if not g2p_lang_dir.is_dir():
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[warning] g2p directory not found: {g2p_lang_dir}. skipping.\n")
        return True

    # cloud_g2p_langs 语种 + is_yun==3 → run_cloud.sh + cloud 文件名，其他走 run.sh
    cloud_langs = global_cfg.get('cloud_g2p_langs', [])
    is_whisper = str(task.get('is_yun', '')) == '3'
    is_cloud_lang = lang_abbr in cloud_langs or lang_id in cloud_langs
    use_cloud = is_cloud_lang and is_whisper

    g2p_input_txt = g2p_lang_dir / ("input_cloud.txt" if use_cloud else "input.txt")
    g2p_output_dict_shared = g2p_lang_dir / ("output_cloud.dict" if use_cloud else "output.dict")
    private_output_dict = Path(task_out_path_temp) / f"g2p_output_{msg}.dict"

    # Handle encoding (UTF-16 support for specific legacy engines)
    target_encoding = 'utf-8'
    target_newline = '\n'
    if g2p_input_txt.exists():
        with open(g2p_input_txt, 'rb') as f_probe:
            raw_bytes = f_probe.read(2)
            if raw_bytes in (b'\xff\xfe', b'\xfe\xff'):
                target_encoding = 'utf-16'
                target_newline = '\r\n'

    print(f"[{datetime.now().strftime('%H:%M:%S')}] WAITING LOCK: phase1_step2 for {msg}")
    lock_file_path = g2p_lang_dir / ".g2p_engine_exec.lock"

    try:
        with open(lock_file_path, 'w') as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ACQUIRED LOCK: executing g2p for {msg}")

                # Hebrew context synthesis or standard word listing
                is_hebrew = lang_abbr and lang_abbr.lower() in ['he', 'heb', 'hebrew']
                if is_hebrew:
                    corpus_dir = os.path.join(global_cfg.get('asrmlg_exp_dir', ''), task.get('excel_corpus_path', ''))
                    generate_context_for_hebrew_oov(str(oov_file_path), corpus_dir, str(g2p_input_txt), target_encoding, target_newline)
                else:
                    with open(oov_file_path, 'r', encoding='utf-8', errors='ignore') as f_in:
                        lines = f_in.readlines()
                    with open(g2p_input_txt, 'w', encoding=target_encoding, newline=target_newline) as f_out:
                        for line in lines:
                            word = line.strip()
                            f_out.write(f"{word}{target_newline}")

                g2p_script = "run_cloud.sh" if use_cloud else "run.sh"
                success = run_subprocess(["bash", g2p_script], str(g2p_lang_dir), log_file)

                if success and g2p_output_dict_shared.exists():
                    shutil.copy2(g2p_output_dict_shared, private_output_dict)
                else:
                    return False
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] RELEASED LOCK: g2p finished for {msg}")
                
    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as f_log:
            f_log.write(f"[error] locked g2p execution failed: {str(e)}\n")
        return False

    return True


def step3_merge_dict(task: dict, global_cfg: dict, msg: str, log_file: str) -> bool:
    """
    Step 3: Merges G2P-predicted phonemes into the primary dictionary (Lexicon).
    Uses 'lexicon_vcs.py' for version control of the dictionary files.
    """
    res_dir_map = global_cfg.get('res_dir_map', {})
    lang_abbr_map = global_cfg.get('lang_abbr_map', {})
    merge_script = global_cfg.get('merge_dict_script')
    res_base_dir = os.path.join(global_cfg.get('asrmlg_exp_dir'), global_cfg.get('res_dir_name', 'res'))

    if not (merge_script and os.path.exists(merge_script) and res_base_dir):
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[warning] merge dependencies missing. skipping merge.\n")
        return True

    print(f"[{datetime.now().strftime('%H:%M:%S')}] STARTING: phase1_step3 (merge oov dict) for {msg}")

    python_exec = global_cfg.get('python_exec', 'python')
    vcs_script_path = os.path.join(global_cfg.get('tools_dir', './'), 'lexicon_vcs.py')

    lang_id = str(task.get('l', 0))
    lang_abbr = lang_abbr_map.get(lang_id)
    is_yun_val = str(task.get('is_yun', '0'))
    res_dir_name = res_dir_map.get(is_yun_val, "unknown")
    lang_map = global_cfg.get('parsed_language_map', {})
    lang_name = lang_map.get(lang_id, "")

    # Path to the primary lexicon that needs updating
    target_res_dir = os.path.join(res_base_dir, f"{lang_name}_res", res_dir_name)
    target_dict_path = os.path.join(target_res_dir, "new_dict")

    # Locate phoneme validation file
    phone_syms_path = os.path.join(target_res_dir, "phones.syms")
    if not os.path.exists(phone_syms_path):
        fallback_path = os.path.join(target_res_dir, "phones.list.noblank")
        if os.path.exists(fallback_path):
            phone_syms_path = fallback_path

    # Bug-2 Fix: Use private_output_dict (from step2) if available, fallback to shared G2P output
    # Reconstruct the task_out_path_temp from the same logic as run_phase1_pipeline
    base_out_dir = global_cfg.get('output_dir')
    scheme_map = global_cfg.get('scheme_map', {})
    model_type = scheme_map.get(is_yun_val, 'unknown')
    target_dir = os.path.join(base_out_dir, lang_name, msg, f"{model_type}_{datetime.now().strftime('%Y%m%d')}")
    task_out_path_temp = target_dir + "_temp"
    private_output_dict = os.path.join(task_out_path_temp, f"g2p_output_{msg}.dict")

    # Use private copy from step2 if it exists, otherwise fallback to shared G2P output
    g2p_output_dict = private_output_dict if os.path.exists(private_output_dict) else \
                      os.path.join(global_cfg.get('g2p_root_dir', ''), lang_abbr, "g2p_models", "output.dict")

    if not os.path.exists(g2p_output_dict):
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[warning] g2p output dict not found: {g2p_output_dict}. skipping merge.\n")
        return False

    # Snapshot before merge
    if os.path.exists(vcs_script_path):
        run_subprocess([python_exec, vcs_script_path, "-i", target_dict_path, "pre_merge"],
                       global_cfg.get('asrmlg_exp_dir'), log_file)

    # Perform physical merge
    merge_cmd = [
        python_exec, merge_script,
        "-i", g2p_output_dict,
        "-o", target_dict_path,
        "-p", phone_syms_path
    ]
    if task.get('predict_phone_for_new'):
        merge_cmd.append("--predict_phone_for_new")

    merge_success = run_subprocess(merge_cmd, global_cfg.get('asrmlg_exp_dir'), log_file)

    # Commit merge results with metadata
    if merge_success and os.path.exists(vcs_script_path):
        run_subprocess([
            python_exec, vcs_script_path,
            "-i", target_dict_path,
            "post_merge",
            "-m", task.get('msg', ''),
            "-l", lang_id,
            "--max_versions", str(global_cfg.get('max_versions', 10))
        ], global_cfg.get('asrmlg_exp_dir'), log_file)

    # Bug-3 Fix: Return actual merge_success instead of always returning True
    return merge_success

def step4_full_build(base_cmd: List[str], task_out_path: str, msg: str,
                     patch_type: str, asrmlg_exp_dir: str, log_file: str) -> bool:
    """
    Step 4: Executes the full model build (WFST compilation and binary packaging).
    This combines the updated dictionary with the corpus to create the final ASR binary.
    """
    task_out_path_temp = task_out_path + "_temp"
    shutil.rmtree(task_out_path_temp, ignore_errors=True)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] STARTING: phase1_step4 (full resource build) for {msg}")

    base_cmd = base_cmd + ["--output", task_out_path]
    # Inject patch type into the message for better tracking
    try:
        idx = base_cmd.index("--msg")
        base_cmd[idx + 1] = f"{msg}_{patch_type}"
    except (ValueError, IndexError):
        base_cmd.extend(["--msg", f"{msg}_{patch_type}"])

    return run_subprocess(base_cmd, asrmlg_exp_dir, log_file)



def generate_custom_cfg(output_cfg_path: str, work_dir: str, lm_scale: str,
                         lang_full: str, lang_short: str, patch_type: str, name: str):
    """Generates wfst_serialize .cfg using absolute paths to files in work_dir."""
    cfg_content = f"""[common]
business=
lm_factor= {lm_scale}
penalty_factor= 5
lang_name= zh-cn
pack_name= car
net_type= 5
class_type= pername

[input]
wfst_net_txt={work_dir}/output.wfst.mvrd.txt
edDcitSymsFile={work_dir}/edDictPhones.syms
phoneSymsFile={work_dir}/edDictPhones.syms
wordsSymsFile={work_dir}/words.syms
word2PhoneFile={work_dir}/aaa_dict_for_use.remake

[input_option]
mappingFile=
stateSymsFile=
pinyinSymsFile=
PYDictFile=
UpCaseConvertFile=
phoneDistanceFile=

[output]
OutWfst.bin={work_dir}/output/{lang_short}_{patch_type}_whisper_44phones_patch{lm_scale}_{name}.bin
"""
    with open(output_cfg_path, 'w', encoding='utf-8') as f:
        f.write(cfg_content)
    return output_cfg_path


def step5_whisper_package(task: dict, global_cfg: dict, hybridcnn_gpatch: str, log_file: str) -> bool:
    """
    Step 5: Whisper-specific serialization.
    Generates CFG from scratch, runs wfst_serialize, then computes MD5.
    """
    if str(task.get('is_yun', '')) != '3':
        return True

    whisper_cfg = task.get('whisper_config', {})
    msg = str(task.get('msg', 'music'))
    lang_id = str(task.get('l', ''))
    lang_map = global_cfg.get('parsed_language_map', {})
    lang_name = lang_map.get(lang_id, f"lang_{lang_id}")
    timestamp = datetime.now().strftime('%Y%m%d')
    current_user = os.environ.get('USER', 'default_user')

    work_dir_name = whisper_cfg.get('work_dir', f"{lang_name}_{msg}_patch_{timestamp}")
    patch_type = whisper_cfg.get('patch_type', msg)
    patch_scale = str(whisper_cfg.get('patch_scale', '1.0'))

    asrmlg_exp_dir = global_cfg.get('asrmlg_exp_dir', '')
    res_yun_dir = os.path.join(asrmlg_exp_dir, 'res', f"{lang_name}_res", 'yun')

    # train_dict / phoneset 自动从 res/{lang}_res/yun/ 推导，可在 whisper_config 中覆盖
    train_dict    = whisper_cfg.get('train_dict')    or os.path.join(res_yun_dir, 'new_dict')
    phoneset_path = whisper_cfg.get('phoneset')      or os.path.join(res_yun_dir, 'phones.syms')
    package_ed_target = whisper_cfg.get('package_ed_target', '/dev/null')  # placeholder

    for p, label in [(train_dict, 'train_dict'), (phoneset_path, 'phoneset')]:
        if not os.path.exists(p):
            with open(log_file, 'a', encoding='utf-8') as f_log:
                f_log.write(f"[error] step5: {label} not found: {p}\n")
            return False

    base_out_dir = global_cfg.get('output_dir')
    out_yun_dir = os.path.join(base_out_dir, lang_name, 'yun', msg)  # 交付目录
    work_dir = os.path.join(out_yun_dir, work_dir_name)               # 构建工作目录

    pipeline_dir = os.path.dirname(os.path.abspath(__file__))
    pipeline_tools_dir = os.path.join(pipeline_dir, 'tools')   # run_replace_dict.sh
    whisper_bin_dir = os.path.join(pipeline_dir, 'bin')        # wfst_serialize 及其依赖库

    ts = lambda: datetime.now().strftime('%H:%M:%S')
    print(f"[{ts()}] STARTING: step5_whisper_package for {msg} ({lang_name})")
    print(f"[{ts()}]   work_dir       : {work_dir}")
    print(f"[{ts()}]   hybridcnn_patch: {hybridcnn_gpatch}")
    print(f"[{ts()}]   train_dict     : {train_dict}")
    print(f"[{ts()}]   phoneset       : {phoneset_path}")
    print(f"[{ts()}]   patch_type     : {patch_type}  scale: {patch_scale}")

    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)
    os.makedirs(os.path.join(work_dir, "output"), exist_ok=True)

    # --- Copy artifacts from hybridCNN_Gpatch ---
    print(f"[{ts()}] STEP5.1: copying artifacts from hybridcnn_gpatch ...")
    files_to_copy = [
        (os.path.join(hybridcnn_gpatch, "custom_G_pak", "G"), os.path.join(work_dir, "G")),
        (os.path.join(hybridcnn_gpatch, "custom_G_pak", "GeneratedG.DONE"), os.path.join(work_dir, "GeneratedG.DONE")),
        (os.path.join(hybridcnn_gpatch, "custom_corpus_process", "dict_dir", "aaa_dict_for_use"), os.path.join(work_dir, "aaa_dict_for_use"))
    ]
    for src, dst in files_to_copy:
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"[{ts()}]   copied: {os.path.basename(src)}")
        else:
            print(f"[{ts()}]   ERROR: source not found: {src}")
            with open(log_file, 'a', encoding='utf-8') as f_log:
                f_log.write(f"[error] step5: source file not found: {src}\n")
            return False

    # --- run_replace_dict.sh ---
    print(f"[{ts()}] STEP5.2: run_replace_dict.sh ...")
    replace_dict_cmd = ["bash", os.path.join(pipeline_tools_dir, "run_replace_dict.sh"), train_dict, work_dir]
    if not run_subprocess(replace_dict_cmd, work_dir, log_file):
        print(f"[{ts()}]   ERROR: run_replace_dict.sh failed, see {log_file}")
        return False
    print(f"[{ts()}]   done")

    # --- package_ed ---
    print(f"[{ts()}] STEP5.3: package_ed ...")
    dict_remake_path = os.path.join(work_dir, "aaa_dict_for_use.remake")
    package_ed_cmd = [os.path.join(whisper_bin_dir, "package_ed"), dict_remake_path, phoneset_path, package_ed_target, work_dir]
    if not run_subprocess(package_ed_cmd, work_dir, log_file):
        print(f"[{ts()}]   ERROR: package_ed failed, see {log_file}")
        return False
    print(f"[{ts()}]   done")

    # --- Generate CFG ---
    print(f"[{ts()}] STEP5.4: generating wfst_serialize cfg ...")
    cfg_name = "wfst_serialize_large.241227_patch.cfg"
    cfg_path = os.path.join(work_dir, cfg_name)
    generate_custom_cfg(cfg_path, work_dir, patch_scale, lang_name, lang_name, patch_type, msg)
    log_dir = os.path.dirname(log_file)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    shutil.copy2(cfg_path, os.path.join(log_dir, cfg_name))
    print(f"[{ts()}]   cfg: {cfg_path}")

    # --- wfst_serialize ---
    print(f"[{ts()}] STEP5.5: running wfst_serialize ...")
    run_env = os.environ.copy()
    run_env['LD_LIBRARY_PATH'] = f"{whisper_bin_dir}:{run_env.get('LD_LIBRARY_PATH', '')}"
    wfst_bin = os.path.join(whisper_bin_dir, "wfst_serialize")
    if not run_subprocess([wfst_bin, cfg_path], whisper_bin_dir, log_file, env=run_env):
        print(f"[{ts()}]   ERROR: wfst_serialize failed, see {log_file}")
        return False
    print(f"[{ts()}]   done")

    # --- 交付 bin ---
    print(f"[{ts()}] STEP5.6: delivering bin to {out_yun_dir} ...")
    generated_bin_dir = os.path.join(work_dir, "output")
    bins = [f for f in os.listdir(generated_bin_dir) if f.endswith(".bin")]
    if not bins:
        print(f"[{ts()}]   WARNING: no .bin found in {generated_bin_dir}")
        with open(log_file, 'a', encoding='utf-8') as f_log:
            f_log.write(f"[warning] whisper bin not found in {generated_bin_dir}\n")
    else:
        bin_source = os.path.join(generated_bin_dir, bins[0])
        import hashlib
        with open(bin_source, 'rb') as bf:
            md5_suffix = hashlib.md5(bf.read()).hexdigest()[-4:]
        final_bin_name = f"{lang_name}_{patch_type}_whisper_patch{patch_scale}_{current_user}_{timestamp}_{md5_suffix}.bin"
        final_bin_path = os.path.join(generated_bin_dir, final_bin_name)
        os.rename(bin_source, final_bin_path)
        os.makedirs(out_yun_dir, exist_ok=True)
        shutil.copy2(final_bin_path, os.path.join(out_yun_dir, final_bin_name))
        with open(log_file, 'a', encoding='utf-8') as f_log:
            f_log.write(f"[step5] bin: {final_bin_name}\n")
        print(f"[{ts()}]   bin: {final_bin_name}")

    print(f"[{ts()}] SUCCESS: step5_whisper_package done -> {out_yun_dir}")
    return True


def run_phase1_pipeline(task: dict, global_cfg: dict, asrmlg_exp_dir: str,
                        python_exec: str, train_script: str) -> bool:
    """Orchestrates Phase 1 steps as a linear state machine."""
    msg = str(task.get('msg'))
    lang_id = str(task.get('l', ''))
    base_out_dir = global_cfg.get('output_dir')
    scheme_map = global_cfg.get('scheme_map', {})
    lang_map = global_cfg.get('parsed_language_map', {})
    lang_name = lang_map.get(lang_id, f"lang_{lang_id}")
    model_type = scheme_map.get(str(task.get('is_yun', 0)), 'unknown')

    # Per-task log: logs/{lang_name}/{msg}/pak_{msg}_{model_type}_{date}.log
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(global_cfg.get('log_dir', ''), lang_name, msg, f"pak_{msg}_{model_type}_{time_str}.log")
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # 1. Extraction -> 2. G2P -> 3. Merge -> 4. Full Build -> 5. Whisper Package
    target_dir = os.path.join(base_out_dir, lang_name, msg, f"{model_type}_{datetime.now().strftime('%Y%m%d')}")

    whisper_cfg = task.get('whisper_config', {})
    hybridcnn_gpatch = whisper_cfg.get('hybridcnn_gpatch', '')

    # If hybridcnn_gpatch is set, skip step1-4 and directly run step5
    if hybridcnn_gpatch and task.get('enable_whisper_package'):
        return step5_whisper_package(task, global_cfg, hybridcnn_gpatch, log_file)

    base_cmd = build_base_command(task, python_exec, train_script, asrmlg_exp_dir)

    if not step1_extract_oov(base_cmd, target_dir, msg, asrmlg_exp_dir, log_file): return False
    if task.get('enable_g2p') and not step2_g2p_predict(task, global_cfg, msg, target_dir, log_file): return False
    if task.get('enable_merge_dict') and not step3_merge_dict(task, global_cfg, msg, log_file): return False
    if not step4_full_build(base_cmd, target_dir, msg, model_type, asrmlg_exp_dir, log_file): return False
    if task.get('enable_whisper_package'): return step5_whisper_package(task, global_cfg, target_dir, log_file)

    return True


def execute_phase1(tasks: List[dict], global_cfg: dict):
    """Entry point for Phase 1. Uses a ProcessPool for parallel builds across languages/projects."""
    print("\n=== pipeline phase 1: resource build & g2p (parallel mode) ===")
    python_exec = global_cfg.get('python_exec')
    asrmlg_exp_dir = global_cfg.get('asrmlg_exp_dir')
    train_script = os.path.join(asrmlg_exp_dir, global_cfg.get('train_script', 'corpus_process_package.py'))

    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_phase1_pipeline, t, global_cfg, asrmlg_exp_dir, python_exec, train_script): t.get('msg') for t in tasks}
        for future in as_completed(futures):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Task {futures[future]} finished.")


# =============================================================================
# Phase 2 & 3: Testset & Eval
# =============================================================================

def execute_testset_phase(tasks: List[dict], global_cfg: dict):
    """
    Orchestrates Phase 2. Parallel text extraction from Excel files, followed by
    serial TTS generation (to prevent audio interface/TTS engine conflicts).

    Flow:
    1. DeltaTracker checks semantic hash of each Excel corpus.
    2. Changed files are extracted in parallel (ThreadPool).
    3. TTS synthesis runs serially (global engine lock inside make_test_set.py).
    4. Manifest is updated per task on success.
    """
    print("\n=== pipeline phase 2: incremental testset generation ===")
    try:
        _execute_testset_phase_impl(tasks, global_cfg)
    except Exception as e:
        import traceback
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR in phase2: {e}")
        traceback.print_exc()


def _execute_testset_phase_impl(tasks: List[dict], global_cfg: dict):
    output_dir    = global_cfg.get('output_dir', '')
    log_dir       = global_cfg.get('log_dir', '')
    asrmlg_exp_dir = global_cfg.get('asrmlg_exp_dir', '')
    python_exec   = global_cfg.get('python_exec', sys.executable)
    tools_dir     = global_cfg.get('tools_dir', '')
    lang_map      = global_cfg.get('parsed_language_map', {})

    make_test_set_script = os.path.join(tools_dir, 'make_test_set.py')

    # -------------------------------------------------------------------------
    # Step 1: Determine which tasks need regeneration (hash check)
    # Each task has its own manifest: test_sets/{lang_name}_{msg}_manifest.json
    # -------------------------------------------------------------------------
    pending = []
    for task in tasks:
        if not task.get('enable_testset'):
            continue

        lang_id    = str(task.get('l', ''))
        lang_name  = lang_map.get(lang_id, f"lang_{lang_id}")
        msg        = str(task.get('msg', ''))
        excel_path = task.get('excel_corpus_path', '')

        if not excel_path:
            continue
        if not os.path.isabs(excel_path):
            excel_path = os.path.join(asrmlg_exp_dir, excel_path)
        if not os.path.exists(excel_path):
            print(f"[warning] corpus path not found: {excel_path}, skipping {msg}")
            continue

        # Per-task manifest, isolated by language and msg
        manifest_path = os.path.join(output_dir, "test_sets", f"{lang_name}_{msg}_testset_manifest.json")
        tracker = DeltaTracker(manifest_path)

        # Support both single .xlsx file and directory of .xlsx files
        # Key strategy matches pipeline_warmup.py: use filename (not path) as manifest key
        # Each xlsx file is checked and queued independently for extract -> TTS -> package
        if os.path.isdir(excel_path):
            xlsx_files = sorted([
                os.path.join(root, f)
                for root, _, files in os.walk(excel_path)
                for f in files
                if f.endswith('.xlsx') and not f.startswith('~$')
            ])
            if not xlsx_files:
                print(f"[warning] no .xlsx files found in {excel_path}, skipping {msg}")
                continue
        else:
            xlsx_files = [excel_path]

        for xf in xlsx_files:
            fname = os.path.basename(xf)
            new_hash = DeltaTracker.get_semantic_hash(xf)
            if tracker.history.get(fname, {}).get('hash') == new_hash:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] SKIP (no change): {fname}")
                continue
            pending.append((task, lang_name, msg, xf, new_hash, lang_id, tracker))

    print(f"[{datetime.now().strftime('%H:%M:%S')}] INFO: {len(pending)} task(s) pending for testset generation.")
    if not pending:
        print("[INFO] All testsets up-to-date, nothing to do.")
        return

    # -------------------------------------------------------------------------
    # Step 2: Parallel text extraction from Excel
    # -------------------------------------------------------------------------
    sys.path.insert(0, tools_dir)
    from excel_to_txt_sampler import CorpusAdapter

    def extract_text(item):
        task, lang_name, msg, xlsx_file, new_hash, lang_id, tracker = item
        xlsx_stem = Path(xlsx_file).stem
        try:
            count = task.get('testset_count', 1000)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] EXTRACTING: {xlsx_stem} ({os.path.basename(xlsx_file)})")
            adapter = CorpusAdapter(xlsx_file, target_count=count)
            adapter.parse_excel()
            sentences = adapter.generate_testset()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] EXTRACTED:  {xlsx_stem} -> {len(sentences)} sentences")

            txt_dir = os.path.join(output_dir, "test_sets", lang_name, f"{msg}_staging")
            os.makedirs(txt_dir, exist_ok=True)
            txt_path = os.path.join(txt_dir, f"{xlsx_stem}.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                for sent in sentences:
                    f.write(sent.strip() + '\n')

            return item, txt_path, True
        except Exception as e:
            print(f"[error] text extraction failed for {xlsx_stem}: {e}")
            return item, None, False

    with ThreadPoolExecutor(max_workers=4) as pool:
        extraction_results = list(pool.map(extract_text, pending))

    # -------------------------------------------------------------------------
    # Step 3: Serial TTS synthesis (engine allows only one concurrent user)
    # -------------------------------------------------------------------------
    replacement_list = global_cfg.get('g2p_replacement_list', '')

    for item, txt_path, ok in extraction_results:
        if not ok or not txt_path:
            continue

        task, lang_name, msg, xlsx_file, new_hash, lang_id, tracker = item
        xlsx_stem    = Path(xlsx_file).stem
        task_log_dir = os.path.join(log_dir, lang_name, msg)
        out_base     = os.path.join(output_dir, "test_sets", lang_name, msg)
        time_str     = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file     = os.path.join(task_log_dir, f"testset_{xlsx_stem}_{time_str}.log")

        cmd = [
            python_exec, make_test_set_script,
            '-e', asrmlg_exp_dir,
            '-l', lang_id,
            '-i', txt_path,
            '--output', out_base,
            '--tts',
            '--log_dir', task_log_dir,
        ]
        if replacement_list and os.path.exists(replacement_list):
            cmd.extend(['--replacement_list', replacement_list])

        print(f"[{datetime.now().strftime('%H:%M:%S')}] STARTING: TTS testset for {xlsx_stem} -> {os.path.basename(txt_path)}")
        success = run_tts_with_progress(cmd, asrmlg_exp_dir, log_file)

        if success:
            tracker.update_history(os.path.basename(xlsx_file), new_hash)
            tracker.save()
            # Clean up staging txt; remove staging/ dir when all files done
            if os.path.exists(txt_path):
                os.remove(txt_path)
            staging_dir = os.path.dirname(txt_path)
            if os.path.isdir(staging_dir) and not os.listdir(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] DONE: testset for {xlsx_stem}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] FAILED: TTS for {xlsx_stem}, see {log_file}")

def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="ASR Pipeline Executor")
    parser.add_argument('-g', '--global_config', required=False, help='Path to global_config.yaml (default: config/global_config.yaml)')
    parser.add_argument('-j', '--job', required=False, default=None, help='Path to job.yaml (default: config/job.yaml)')
    args = parser.parse_args()

    base_path = os.path.dirname(os.path.abspath(__file__))

    # Auto-detect job.yaml in pipeline/config/ if -j not specified
    job_path = args.job
    if not job_path:
        default_job = os.path.join(base_path, 'config', 'job.yaml')
        if os.path.exists(default_job):
            job_path = default_job
            print(f"[INFO] job config  : {job_path} (auto-detected)")
        else:
            print("[error] -j <job.yaml> is required or place job.yaml in pipeline/config/")
            sys.exit(1)

    # Auto-detect global_config.yaml in pipeline/config/ if -g not specified
    cfg_path = args.global_config
    if not cfg_path:
        default_cfg = os.path.join(base_path, 'config', 'global_config.yaml')
        if os.path.exists(default_cfg):
            cfg_path = default_cfg
            print(f"[INFO] global_config: {cfg_path} (auto-detected)")

    # Load configurations or use empty defaults for zero-config
    global_cfg = yaml.safe_load(open(cfg_path)) if cfg_path and os.path.exists(cfg_path) else {}
    job_cfg = yaml.safe_load(open(job_path))

    # Apply smart path resolution
    global_cfg = resolve_and_bind_paths(global_cfg, base_path)
    tasks = job_cfg.get('tasks', [])

    # Load language name mappings (e.g. 26 -> En)
    lang_map_path = global_cfg.get('language_map_name', 'language_map')
    global_cfg['parsed_language_map'] = load_language_map(os.path.join(global_cfg.get('asrmlg_exp_dir', ''), lang_map_path))

    # Execute Phase 1 and Phase 2 concurrently
    with ThreadPoolExecutor(max_workers=2) as macro_executor:
        future_p1 = macro_executor.submit(execute_phase1, tasks, global_cfg)
        future_p2 = macro_executor.submit(execute_testset_phase, tasks, global_cfg)
        future_p1.result(); future_p2.result()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] PIPELINE COMPLETED.")

if __name__ == "__main__":
    main()
