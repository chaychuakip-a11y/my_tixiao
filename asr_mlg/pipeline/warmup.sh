#!/bin/bash
# warmup.sh
#
# Pre-computes semantic hashes for all Excel corpus files listed in job.yaml.
# Run this before the first pipeline execution (or after importing a new corpus)
# so the incremental tracker treats existing files as "already processed",
# preventing unnecessary TTS re-synthesis.
#
# Usage:
#   ./warmup.sh -j ../../job.yaml
#   ./warmup.sh -j ../../job.yaml -g ../../global_config.yaml
#   ./warmup.sh -j ../../job.yaml --dry-run
#
# Note: if -g is omitted, auto-detects config/global_config.yaml under pipeline/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WARMUP_SCRIPT="$SCRIPT_DIR/tools/pipeline_warmup.py"
PYTHON="${PYTHON:-python3}"

if [[ ! -f "$WARMUP_SCRIPT" ]]; then
    echo "[error] pipeline_warmup.py not found at: $WARMUP_SCRIPT"
    exit 1
fi

exec $PYTHON "$WARMUP_SCRIPT" "$@"
