# -*- coding:utf-8 -*-
"""
Make Test Set Pipeline

This script automates the creation of ASR test sets, including:
1. Text Normalization: Leveraging the main engine's corpus processing logic.
2. TTS Generation: Automated audio synthesis using the XTTS engine.
3. Concurrency Protection: Global file locking to prevent multiple processes from crashing the TTS engine.
4. Packaging: Creating standardized ZIP archives containing audio and MLF (Master Label File).
"""

import sys
import os
import re
import shutil
import argparse
import subprocess
import zipfile
import uuid
import fcntl
import getpass
from datetime import datetime
from pathlib import Path

# =============================================================================
# Dynamic Environment Injection
# =============================================================================
# We must parse the engine directory early to inject its libraries into sys.path
# before attempting to import internal modules like 'corpus_process'.
_init_parser = argparse.ArgumentParser(add_help=False)
_init_parser.add_argument('-e', '--engine_dir', type=str, required=True, help="Path to main ASR engine directory")
_init_args, _ = _init_parser.parse_known_args()

ENGINE_DIR = Path(_init_args.engine_dir).resolve()
PYTHON_LIB_PATH = ENGINE_DIR / "python_lib"

if not PYTHON_LIB_PATH.exists():
    print(f"[FATAL ERROR] python_lib not found in {ENGINE_DIR}.")
    sys.exit(1)

# Push the engine's library paths to the front of the environment
sys.path.insert(0, str(ENGINE_DIR))
if PYTHON_LIB_PATH.exists():
    sys.path.insert(0, str(PYTHON_LIB_PATH))

# corpus_process.py opens "language_map" with a relative path → must run from ENGINE_DIR
os.chdir(str(ENGINE_DIR))

# Import main project dependencies
from corpus_process import *

def generate_mlf(input_txt_path: str, output_mlf_path: str):
    """
    Converts a tab-separated text file (wave_name \t transcript) into HTK MLF format.
    Required for standard ASR evaluation tools.
    """
    with open(input_txt_path, 'r', encoding='utf-8') as src_file, \
         open(output_mlf_path, 'w', encoding='utf-8') as dst_mlf:
        
        dst_mlf.write("#!MLF!#\n")
        for line in src_file:
            line = line.strip()
            if not line: continue
            parts = line.split("\t")
            wave_name_full = parts[0]
            lab_line = parts[-1].strip()
            wave_name = Path(wave_name_full).stem
            
            dst_mlf.write(f'"*/{wave_name}.lab"\n')
            dst_mlf.write("<s>\n")
            for word in lab_line.split(' '):
                if word.strip():
                    dst_mlf.write(f"{word}\n")
            dst_mlf.write("</s>\n.\n")

def process_text_corpus(input_txt: str, language: int, ispost: bool, corpus_proc_inst) -> str:
    """
    Normalizes test transcripts (splitting and filtering) to match the model's training format.
    """
    input_path = Path(input_txt)
    output_txt = input_path
    
    # Handle language-specific subword splitting (e.g., Thai/Japanese)
    if num2LagDict[language] in need_split:
        before_split = input_path.with_name(f"{input_path.name}_before_split")
        shutil.move(input_path, before_split)
        split_function = corpus_proc_inst.get_split_function()
        
        with open(before_split, 'r', encoding='utf-8') as infile, \
             open(output_txt, 'w', encoding='utf-8') as outfile, \
             open(input_path.with_name(f"{input_path.name}_split_oov"), 'w', encoding='utf-8') as oov_file:
            for line in infile:
                line = line.strip()
                if not line: continue
                parts = line.split("\t")
                wave_name = parts[0]
                lab_line = parts[-1].strip()
                outfile.write(f"{wave_name}\t")
                split_function.split(lab_line, outfile, oov_file)

    # Character filtering and OOV tracking
    before_filter = input_path.with_name(f"{input_path.name}_before_filter")
    shutil.move(output_txt, before_filter)
    
    with open(before_filter, 'r', encoding='utf-8') as infile, \
         open(output_txt, 'w', encoding='utf-8') as outfile, \
         open(input_path.with_name(f"{input_path.name}_filter_oov"), 'w', encoding='utf-8') as oov_file:
        for line in infile:
            line = line.strip()
            if not line: continue
            parts = line.split("\t")
            wave_name = parts[0]
            lab_line = parts[-1].strip()
            outfile.write(f"{wave_name}\t")
            corpus_proc_inst.filter_corpus_by_char(lab_line, outfile, oov_file, ispost)
            
    return str(output_txt)

def run_tts_generation(input_txt: str, language: int, output_dir: str, label_txt: str = None, log_dir: str = None):
    """
    Core synthesis logic.
    Uses 'fcntl' locking to ensure that only ONE process uses the legacy TTS engine at a time.
    """
    tts_base_dir = ENGINE_DIR / "xtts20_for_asr" / "bin_tts"
    wav_outdir = tts_base_dir / "wav_outdir"
    frontinfo = tts_base_dir / "frontinfo.txt"
    
    # Generate unique ID to isolate this task's audio output
    task_uuid = uuid.uuid4().hex[:6]
    private_wav_dir = Path(output_dir) / f"wavs_{task_uuid}"
    log_base = Path(log_dir) if log_dir else Path(output_dir)
    log_base.mkdir(parents=True, exist_ok=True)
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_base / f"tts{time_str}.log"
    
    env = os.environ.copy()
    env['TTSKNL_DOMAIN'] = str(tts_base_dir)
    original_ld = env.get('LD_LIBRARY_PATH', '')
    env['LD_LIBRARY_PATH'] = f"{tts_base_dir}:{original_ld}" if original_ld else str(tts_base_dir)
    env['OMP_NUM_THREADS'] = '1'
    
    input_abs_path = Path(input_txt).resolve()
    lang_param = ttsdict[num2LagDict[language]]
    
    cmd = [
        "./ttsSample", "-l", "libttsknl.so", "-v", str(lang_param), 
        "-x", "1", "-i", str(input_abs_path), "-o", "wav_outdir/", 
        "-m", "1", "-f", "1", "-g", "1"
    ]
    
    # Global Exclusive Lock for the TTS Engine
    lock_file = tts_base_dir / ".tts_global_engine.lock"
    print(f"[INFO] Task {task_uuid} waiting for TTS Engine Lock...")

    with open(lock_file, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX) # Block here until engine is free
        try:
            print(f"[INFO] Running TTS for Task {task_uuid}...")
            
            # Clean shared state files from previous runs
            if frontinfo.exists(): frontinfo.unlink()
            if wav_outdir.exists(): shutil.rmtree(wav_outdir)
            wav_outdir.mkdir(parents=True, exist_ok=True)
            
            # Count total sentences for progress display
            with open(input_abs_path, 'r', encoding='utf-8') as _f:
                total_lines = sum(1 for l in _f if l.strip())

            # Run the legacy binary, emit [PROGRESS] markers for the caller to render
            with open(log_file, 'w', encoding='utf-8') as f_log:
                process = subprocess.Popen(cmd, cwd=tts_base_dir, env=env,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                for raw in process.stdout:
                    text = raw.decode('utf-8', errors='replace')
                    f_log.write(text)
                    f_log.flush()
                    if re.match(r'\s*No\.(\d+)\s*:', text):
                        m = re.match(r'\s*No\.(\d+)\s*:', text)
                        print(f"[PROGRESS] {m.group(1)}/{total_lines}", flush=True)
                process.wait()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)
            
            # Secure the audio files before releasing the lock!
            if private_wav_dir.exists(): shutil.rmtree(private_wav_dir)
            shutil.copytree(wav_outdir, private_wav_dir)
            
        except subprocess.CalledProcessError as e:
            print(f"[FATAL] XTTS Engine failed. Check {log_file}"); sys.exit(1)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
            print(f"[INFO] Lock Released by Task {task_uuid}")

    # Map the generated audio files back to the requested labels
    final_output_txt = Path(output_dir) / f"{Path(output_dir).name}.txt"
    wav_files = sorted([f.name for f in private_wav_dir.iterdir() if f.is_file()])
    
    label_source = Path(label_txt).resolve() if label_txt else input_abs_path
    with open(label_source, 'r', encoding='utf-8') as f_in, \
         open(final_output_txt, 'w', encoding='utf-8') as f_out:
        lines = f_in.readlines()
        for wav_name, line in zip(wav_files, lines):
            f_out.write(f"{wav_name}\t{line.strip()}\n")
    
    return str(final_output_txt), str(private_wav_dir)

def build_testset_package(input_txt: str, language: int, input_wav_dir: str, output_dir: str, ispost: bool, corpus_proc_inst, archive_name: str = None):
    """
    Gathers normalization results and audio, then packages them into a HTK-compatible ZIP.
    ZIP contains a subfolder with the same name, containing the MLF and audio files.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    target_txt = out_path / f"{out_path.name}.txt"
    target_mlf = out_path / f"{out_path.name}.mlf"
    
    if Path(input_txt).resolve() != target_txt.resolve():
        shutil.copy2(input_txt, target_txt)
    
    processed_txt = process_text_corpus(str(target_txt), language, ispost, corpus_proc_inst)
    generate_mlf(processed_txt, str(target_mlf))
    
    if input_wav_dir and Path(input_wav_dir).exists():
        zip_stem = archive_name if archive_name else out_path.name
        archive_path = out_path.parent / f"{zip_stem}.zip"
        zip_root_name = zip_stem
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add MLF to the zip subfolder
            if target_mlf.exists():
                zipf.write(target_mlf, arcname=f"{zip_root_name}/{target_mlf.name}")
            
            # Add audio files to the zip subfolder
            for file_path in Path(input_wav_dir).iterdir():
                if file_path.is_file():
                    zipf.write(file_path, arcname=f"{zip_root_name}/{file_path.name}")
                    
        print(f"[INFO] Testset packaged: {archive_path}")

def main():
    parser = argparse.ArgumentParser(description="Create ASR testsets from text.")
    parser.add_argument('-e', '--engine_dir', type=str, required=True)
    parser.add_argument('-l', '--language', type=int, required=True)
    parser.add_argument('-i', '--txt_path', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('-iw', '--input_wav', type=str, default=None)
    parser.add_argument('--tts', action='store_true')
    parser.add_argument('--post', action='store_true')
    parser.add_argument('--replacement_list', type=str, default=None)
    parser.add_argument('--log_dir', type=str, default=None, help="Directory for log files (default: working dir)")
    args = parser.parse_args()

    # Dynamic naming: Language_FileName_User_YYYYMMDD_HHMMSS
    lang_str = num2LagDict.get(args.language, "Unknown")
    base_file_name = Path(args.txt_path).stem
    user_name = getpass.getuser()
    now = datetime.now()
    date_str = now.strftime("%Y%m%d_%H%M%S")
    archive_date_str = now.strftime("%Y%m%d")

    # Working directory uses full timestamp to avoid same-day collisions
    final_name = f"{lang_str}_{base_file_name}_{user_name}_{date_str}"
    # ZIP archive uses date-only name per naming convention
    archive_name = f"{lang_str}_{base_file_name}_{user_name}_{archive_date_str}"
    out_dir = Path(args.output) / final_name
    
    # We only create the directory; we don't rmtree the parent unless specifically needed
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Update args.output for subsequent functions
    args.output = str(out_dir)

    corpus_proc_inst = get_corpus_process(args.language, None, None, None, None, None, None, None, None, None, None, None)

    if args.tts:
        # Pre-process text for TTS (includes phonetic replacements and normalization)
        synthesize_txt = out_dir / "synthesize.txt"
        filter_txt = out_dir / "filter.txt"
        
        # [Logic] Load replacement list for phonetic hacking (e.g., 'A' -> 'Eh')
        replacements = {}
        if args.replacement_list and os.path.exists(args.replacement_list):
            for rep_line in open(args.replacement_list, 'r', encoding='utf-8'):
                parts = rep_line.strip().split(':', 1)
                if len(parts) == 2: replacements[parts[0].strip().upper()] = parts[1].strip()

        # Generate synced label and synthesis text
        with open(args.txt_path, 'r', encoding='utf-8') as infile, \
             open(filter_txt, 'w', encoding='utf-8') as f_filter, \
             open(synthesize_txt, 'w', encoding='utf-8') as f_synth, \
             open(out_dir / "oov_pre_filter.txt", 'w', encoding='utf-8') as f_oov:
            for line in infile:
                line = line.strip()
                if not line: continue
                replaced_line = " ".join([replacements.get(w.upper(), w) for w in line.split()])
                corpus_proc_inst.filter_corpus_by_char(line, f_filter, f_oov, args.post)
                corpus_proc_inst.filter_corpus_by_char(replaced_line, f_synth, f_oov, args.post)

        tts_log_dir = str(Path(args.log_dir) / lang_str / base_file_name) if args.log_dir else None
        output_path, gen_wav_dir = run_tts_generation(str(synthesize_txt), args.language, args.output, label_txt=str(filter_txt), log_dir=tts_log_dir)
        build_testset_package(output_path, args.language, gen_wav_dir, args.output, args.post, corpus_proc_inst, archive_name=archive_name)
    else:
        build_testset_package(args.txt_path, args.language, args.input_wav, args.output, args.post, corpus_proc_inst, archive_name=archive_name)

if __name__ == "__main__":
    main()
