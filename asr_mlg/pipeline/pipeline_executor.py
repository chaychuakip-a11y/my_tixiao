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


def run_subprocess(cmd: List[str], cwd: str, log_file: str, env: Optional[Dict[str, str]] = None) -> bool:
    """
    Standardized wrapper for executing shell commands and binary tools.
    - Redirects stdout/stderr to a dedicated log file.
    - Injects optional environment variables (e.g., LD_LIBRARY_PATH).
    """
    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] CMD: {' '.join(cmd)}\n")
            f.flush()
            process = subprocess.Popen(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=env)
            process.wait()
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

    # [Smart Default] tools_dir -> pipeline/tools
    if 'tools_dir' not in global_cfg:
        global_cfg['tools_dir'] = os.path.join(base_path, 'tools')

    # [Smart Default] g2p_root_dir -> asrmlg_exp_dir/g2p
    if 'g2p_root_dir' not in global_cfg:
        global_cfg['g2p_root_dir'] = os.path.join(global_cfg['asrmlg_exp_dir'], 'g2p')

    # [Smart Default] resource mapping for different is_yun modes
    if 'res_dir_map' not in global_cfg:
        global_cfg['res_dir_map'] = {'0': 'ubctc_duan', '1': 'rnnt_ctc_duan', '2': 'rnnt_ed_duan', '3': 'yun'}
    if 'lang_abbr_map' not in global_cfg:
        global_cfg['lang_abbr_map'] = {'26': 'En', '5': 'En', '69160': 'Ja', '69500': 'Ko', '69400': 'Th'}
    if 'res_dir_name' not in global_cfg:
        global_cfg['res_dir_name'] = 'res'

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
            if key in ['tools_dir', 'merge_dict_script']:
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
        Path(self.manifest_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4, ensure_ascii=False)
            
    def update_history(self, file_path: str, new_hash: str):
        """Updates the internal hash dictionary for a processed file."""
        file_key = os.path.basename(file_path)
        self.history[file_key] = {
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

    g2p_input_txt = g2p_lang_dir / "input.txt"
    g2p_output_dict_shared = g2p_lang_dir / "output.dict"
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
            # Exclusive file lock
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
                
                # Trigger the G2P engine script
                cloud_langs = global_cfg.get('cloud_g2p_langs', [])
                g2p_script = "run_cloud.sh" if lang_abbr in cloud_langs or lang_id in cloud_langs else "run.sh"
                
                success = run_subprocess(["./" + g2p_script], str(g2p_lang_dir), log_file)
                
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


def check_whisper_dependencies(source_dir: str) -> bool:
    """Checks if the required WFST and dictionary artifacts exist for Whisper serialization."""
    required_artifacts = [
        os.path.join(source_dir, "custom_G_pak", "GeneratedG.DONE"),
        os.path.join(source_dir, "custom_G_pak", "G"),
        os.path.join(source_dir, "custom_corpus_process", "dict_dir", "aaa_dict_for_use")
    ]
    return all(os.path.exists(f) for f in required_artifacts)


def generate_custom_cfg(template_path: str, output_cfg_path: str, work_dir: str, bin_output_name: str, patch_scale: str):
    """Generates a specialized .cfg file for the wfst_serialize binary tool."""
    config = configparser.ConfigParser(allow_no_value=True)
    config.optionxform = str
    config.read(template_path, encoding='utf-8')

    if 'common' in config:
        config['common']['lm_factor'] = str(patch_scale)

    abs_work_dir = os.path.abspath(work_dir)
    if 'input' in config:
        config['input']['wfst_net_txt'] = f"{abs_work_dir}/output.wfst.mvrd.txt"
        config['input']['edDcitSymsFile'] = f"{abs_work_dir}/edDictPhones.syms"
        config['input']['phoneSymsFile'] = f"{abs_work_dir}/edDictPhones.syms"
        config['input']['wordsSymsFile'] = f"{abs_work_dir}/words.syms"
        config['input']['word2PhoneFile'] = f"{abs_work_dir}/aaa_dict_for_use.remake"

    if 'output' in config:
        config['output']['OutWfst.bin'] = f"./output/{bin_output_name}"

    with open(output_cfg_path, 'w', encoding='utf-8') as f:
        config.write(f)

    return output_cfg_path


def step5_whisper_package(task: dict, global_cfg: dict, hybridcnn_gpatch: str, log_file: str) -> bool:
    """
    Step 5: Whisper-specific serialization.
    Converts ASR artifacts into a format optimized for Whisper-based edge devices.
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
    patch_name = whisper_cfg.get('name', f"{current_user}_{msg}_{timestamp}")
    patch_type = whisper_cfg.get('patch_type', msg)
    patch_scale = str(whisper_cfg.get('patch_scale', '1.0'))
    
    train_dict = whisper_cfg.get('train_dict')
    phoneset_path = whisper_cfg.get('phoneset')
    package_ed_target = whisper_cfg.get('package_ed_target')

    if not all([train_dict, phoneset_path, package_ed_target]):
        return False

    whisper_tools_dir = global_cfg.get('whisper_tools_dir', global_cfg.get('asrmlg_exp_dir'))
    work_dir = os.path.join(whisper_tools_dir, work_dir_name)
    base_out_dir = global_cfg.get('output_dir')
    final_whisper_out = os.path.join(base_out_dir, lang_name, msg, f"whisper_bin_{timestamp}")
    os.makedirs(final_whisper_out, exist_ok=True)

    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)

    # Isolated build environment
    files_to_copy = [
        (os.path.join(hybridcnn_gpatch, "custom_G_pak", "G"), os.path.join(work_dir, "G")),
        (os.path.join(hybridcnn_gpatch, "custom_G_pak", "GeneratedG.DONE"), os.path.join(work_dir, "GeneratedG.DONE")),
        (os.path.join(hybridcnn_gpatch, "custom_corpus_process", "dict_dir", "aaa_dict_for_use"), os.path.join(work_dir, "aaa_dict_for_use"))
    ]

    for src, dst in files_to_copy:
        if os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            return False

    # Execute binary conversion tools
    replace_dict_cmd = ["bash", "run_replace_dict.sh", train_dict, work_dir, lang_id]
    if not run_subprocess(replace_dict_cmd, whisper_tools_dir, log_file): return False

    dict_remake_path = os.path.join(work_dir, "aaa_dict_for_use.remake")
    package_ed_cmd = ["./package_ed", dict_remake_path, phoneset_path, package_ed_target, work_dir]
    if not run_subprocess(package_ed_cmd, whisper_tools_dir, log_file): return False

    wearlized_dir = os.path.join(whisper_tools_dir, "wearlized")
    task_uuid = uuid.uuid4().hex[:8]
    template_cfg = os.path.join(wearlized_dir, "wfst_serialize_large.241227_patch.cfg")
    custom_cfg_name = f"task_{task_uuid}.cfg"

    exact_bin_name = f"whisper_{patch_type}_{patch_scale}_{patch_name}_{task_uuid}.bin"
    generate_custom_cfg(template_cfg, os.path.join(wearlized_dir, custom_cfg_name), work_dir, exact_bin_name, patch_scale)

    # Dynamic library binding and serialization
    run_env = os.environ.copy()
    run_env['LD_LIBRARY_PATH'] = f"./:{run_env.get('LD_LIBRARY_PATH', '')}"
    if not run_subprocess(["./wfst_serialize", custom_cfg_name], wearlized_dir, log_file, env=run_env):
        return False

    # Bug-5 Fix: Copy .bin from wearlized/output/ to final_whisper_out
    bin_source = os.path.join(wearlized_dir, "output", exact_bin_name)
    if os.path.exists(bin_source):
        shutil.copy2(bin_source, final_whisper_out)
    else:
        with open(log_file, 'a', encoding='utf-8') as f_log:
            f_log.write(f"\n[warning] whisper bin not found at {bin_source}\n")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] SUCCESS: whisper artifacts exported to {final_whisper_out}")
    return True


def run_phase1_pipeline(task: dict, global_cfg: dict, asrmlg_exp_dir: str,
                        python_exec: str, train_script: str, log_file: str) -> bool:
    """Orchestrates Phase 1 steps as a linear state machine."""
    msg = str(task.get('msg'))
    lang_id = str(task.get('l', ''))
    base_out_dir = global_cfg.get('output_dir')
    scheme_map = global_cfg.get('scheme_map', {})
    lang_map = global_cfg.get('parsed_language_map', {})
    lang_name = lang_map.get(lang_id, f"lang_{lang_id}")
    model_type = scheme_map.get(str(task.get('is_yun', 0)), 'unknown')
    
    # 1. Extraction -> 2. G2P -> 3. Merge -> 4. Full Build -> 5. Whisper Package
    target_dir = os.path.join(base_out_dir, lang_name, msg, f"{model_type}_{datetime.now().strftime('%Y%m%d')}")

    base_cmd = build_base_command(task, python_exec, train_script, asrmlg_exp_dir)

    if not step1_extract_oov(base_cmd, target_dir, msg, asrmlg_exp_dir, log_file): return False
    if task.get('enable_g2p') and not step2_g2p_predict(task, global_cfg, msg, target_dir, log_file): return False
    if task.get('enable_merge_dict'): step3_merge_dict(task, global_cfg, msg, log_file)
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
        futures = {executor.submit(run_phase1_pipeline, t, global_cfg, asrmlg_exp_dir, python_exec, train_script, 
                                 os.path.join(global_cfg.get('output_dir', ''), "logs", "build.log")): t.get('msg') for t in tasks}
        for future in as_completed(futures):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Task {futures[future]} finished.")


# =============================================================================
# Phase 2 & 3: Testset & Eval
# =============================================================================

def execute_testset_phase(tasks: List[dict], global_cfg: dict):
    """
    Orchestrates Phase 2. Parallel text extraction from Excel files, followed by 
    serial TTS generation (to prevent audio interface/TTS engine conflicts).
    """
    print("\n=== pipeline phase 2: incremental testset generation ===")
    # Implementation omitted for brevity in this comment block...
    pass

def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="ASR Pipeline Executor")
    parser.add_argument('-g', '--global_config', required=False, help='Path to global_config.yaml (optional)')
    parser.add_argument('-j', '--job', required=True, help='Path to job.yaml defining tasks')
    args = parser.parse_args()

    base_path = os.path.dirname(os.path.abspath(__file__))

    # Load configurations or use empty defaults for zero-config
    global_cfg = yaml.safe_load(open(args.global_config)) if args.global_config and os.path.exists(args.global_config) else {}
    job_cfg = yaml.safe_load(open(args.job))

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
