# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Pipeline

**Full pipeline (Phase 1 resource build):**
```bash
# From asr_mlg/pipeline/
python pipeline_executor.py -j ../../job.yaml -g ../../global_config.yaml
```

**Generate a single test set (TTS mode):**
```bash
python asr_mlg/pipeline/tools/make_test_set.py \
  -e /path/to/engine_dir \
  -l 69260 \
  -i input.txt \
  --output /path/to/output \
  --tts \
  --replacement_list replacements.txt
```

**Rollback a dictionary after a bad merge:**
```bash
python asr_mlg/pipeline/tools/lexicon_vcs.py -i res/En_res/ubctc_duan/new_dict log
python asr_mlg/pipeline/tools/lexicon_vcs.py -i res/En_res/ubctc_duan/new_dict rollback -t <hash7>
```

**Run unit tests:**
```bash
# From project root (paths hardcoded to /home/lty/my_tixiao, update before running)
python test_pipeline.py
```

**Environment requirement:** All scripts use `import fcntl` and must run on Linux/WSL. The TTS engine requires `LD_LIBRARY_PATH` to include `xtts20_for_asr/bin_tts`. Japanese requires `pip install sudachipy sudachidict_core`.

## Architecture

The project builds ASR (Automatic Speech Recognition) language model binaries from Excel corpora. There are two entry points:

### `asr_mlg/pipeline/pipeline_executor.py` — Full Pipeline Orchestrator

Runs two phases in parallel (ThreadPoolExecutor):

- **Phase 1 (parallel, ProcessPool max 4):** For each task in `job.yaml`, runs a 5-step linear chain:
  1. `step1_extract_oov` — runs `corpus_process_package.py --only_corpus_process` to extract OOV words
  2. `step2_g2p_predict` — predicts phonemes via `g2p/{Lang}/g2p_models/run.sh` (uses `fcntl` exclusive lock per language to prevent engine contention)
  3. `step3_merge_dict` — merges G2P output into `res/{lang}_res/{arch}/new_dict` via `merge_dict.py`; uses `lexicon_vcs.py` to snapshot before/after
  4. `step4_full_build` — runs `corpus_process_package.py` (full build) to produce `.bin` artifacts
  5. `step5_whisper_package` — Whisper serialization (only when `is_yun=3`); bin named `{lang}_{patch_type}_whisper_patch{scale}_{md5[-4:]}.bin`; output to `output/{lang}/yun/{msg}/`
- **Phase 2 (`enable_testset: true`):** `_execute_testset_phase_impl` — per-xlsx incremental testset generation:
  1. `DeltaTracker` checks semantic hash per xlsx against `output/test_sets/{lang_name}_{msg}_testset_manifest.json`
  2. Changed files extracted in parallel → TTS synthesis (serial, fcntl lock) → ZIP
  3. Staging tmp files in `output/test_sets/{lang}/{msg}_staging/`, cleaned on success
  4. Per-xlsx logs: `logs/{lang}/{msg}/testset_{xlsx_stem}_{datetime}.log`

Per-task Phase 1 log: `logs/{lang}/{msg}/pak_{msg}_{model_type}_{datetime}.log` (each task writes its own file, no interleaving)

Output directory pattern: `output/{lang_name}/{msg}/{model_type}_{YYYYMMDD}/`

### `asr_mlg/pipeline/tools/make_test_set.py` — Test Set Generator (standalone)

Requires `-e engine_dir` at startup; performs early `sys.path` injection to import `corpus_process` from the engine. Flow:

1. Load replacement list (phonetic hacks, e.g. `A : Eh`, case-insensitive)
2. Write `synthesize.txt` (TTS input, with replacements) and `filter.txt` (MLF labels, original)
3. `run_tts_generation` — acquires a global `fcntl.LOCK_EX` on `.tts_global_engine.lock`, runs `./ttsSample`, copies WAVs to a private `wavs_{uuid6}/` dir before releasing lock
4. `build_testset_package` → `process_text_corpus` (subword split for Thai/Japanese, then char filter) → `generate_mlf` → ZIP with structure `{name}/{name}.mlf + *.wav`

**Output naming:** `{Language}_{FileName}_{user}_{YYYYMMDD_HHMMSS}/`

### `asr_mlg/corpus_process.py` — Core Language Engine

Imported at runtime by `make_test_set.py`. Provides:
- `num2LagDict`: numeric language ID → name (e.g. `69260 → "english"`)
- `ttsdict`: language name → TTS language param (uses *old* names: `"italy"`, `"portugal"` — mismatches `language_map` which uses `"italian"`, `"portuguese"`)
- `need_split = {'japan', 'thai'}`: languages requiring subword tokenization
- `get_corpus_process(language_id, ...)`: factory for language-specific processing instance
- Loads `spacy` (`ja_core_news_lg`) and `pythainlp` at module level — slow import

### Configuration

**`job.yaml`** (required): list of tasks, each specifying `msg`, `l` (language ID), `is_yun` (arch: 0=CTC, 1=RNNT+CTC, 2=RNNT_ED, 3=Whisper), corpus/resource paths (relative to `asrmlg_exp_dir`), and feature flags (`enable_g2p`, `enable_merge_dict`, etc.).

**`global_config.yaml`** (optional): path overrides and mappings. All paths auto-deduced from `pipeline/`'s parent if not set. Critical: `scheme_map` has **no default** — omitting it causes `model_type='unknown'` in output directory names. `python_exec` sets the interpreter used by shell scripts (`warmup.sh`, `make_testset.sh`); defaults to `python3` if unset. `whisper_bin_dir` defaults to `pipeline/bin/`.

**`asr_mlg/language_map`**: numeric ID → lowercase language name (e.g. `69260:english`). Used to build resource paths like `res/english_res/ubctc_duan/`. The `lang_abbr_map` in config uses uppercase abbreviations (e.g. `En`, `Ja`) for G2P directory lookup — these are separate from `language_map`.

### Supporting Tools

- **`merge_dict.py`**: merges G2P-predicted phonemes into the base dict; validates every phoneme against `phones.syms`; rejects invalid entries with `[REJECTED]` to stderr; writes with forced Linux line endings (`\n`).
- **`lexicon_vcs.py`**: snapshots dict to `.history/` before each merge; hash = first 7 chars of MD5; supports `log` and `rollback -t <hash>` CLI commands.
- **`excel_to_txt_sampler.py`**: expands Excel corpora (sheets: `sent`=static sentences, `shuofa`=templates, `<>`=slot sheet) into test sentences; recursively fills `<slot>` placeholders up to depth 20.
- **`pipeline_warmup.py`**: pre-computes semantic hashes for Excel files. **Critical:** its `get_semantic_hash` logic is a verbatim copy of `DeltaTracker.get_semantic_hash` in `pipeline_executor.py` — both must be updated together if sheet-matching logic changes.

## Known Issues

| Issue | Location | Status |
|-------|----------|--------|
| `ttsdict` uses old language names (`italy`, `portugal`) vs `language_map` (`italian`, `portuguese`) | `corpus_process.py` | Won't fix (by request) |
| `corpus_process.py` opens `language_map` with a bare relative path — CWD must be `ENGINE_DIR` at import time | `corpus_process.py:84` / `make_test_set.py` | Fixed: `os.chdir(ENGINE_DIR)` before import |
| `pipeline_warmup.py` uses filename (not path) as manifest key — same-named xlsx in different dirs collide | `pipeline_warmup.py` | Known |
| `multiprocessing.Pool` + Spacy can cause `ForkProcess` errors on Linux | `corpus_process.py` | Reduce pool size if frequent |

## Resource Layout

```
asr_mlg/
├── corpus_process.py          # Core language engine (imported by make_test_set.py)
├── language_map               # numeric_id:lang_name (no extension)
├── corpus/                    # Excel corpora (*.xlsx)
├── g2p/{Lang}/g2p_models/     # G2P per language: input.txt, output.dict, run.sh
├── res/{lang}_res/{arch}/     # Model resources: new_dict, phones.syms, hmm_list, etc.
├── xtts20_for_asr/bin_tts/    # TTS engine binaries (proprietary, Linux only)
└── pipeline/
    ├── pipeline_executor.py   # Main orchestrator
    ├── warmup.sh              # Thin wrapper over pipeline_warmup.py
    ├── make_testset.sh        # xlsx → TTS testset synthesis (standalone)
    ├── bin/                   # wfst_serialize binary + .so dependencies (copy real files here)
    ├── config/
    │   ├── global_config.yaml
    │   └── job.yaml
    └── tools/
        ├── make_test_set.py         # Standalone test set generator
        ├── merge_dict.py            # Lexicon merge + phoneme validation
        ├── lexicon_vcs.py           # Dict versioning/rollback
        ├── excel_to_txt_sampler.py  # Corpus expansion
        ├── pipeline_warmup.py       # Hash pre-computation
        ├── run_replace_dict.sh      # Placeholder (replace with real tool)
        └── package_ed               # Placeholder (replace with real binary)
```
