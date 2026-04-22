#!/bin/bash
# make_testset.sh
#
# 从 Excel 直接合成 ASR 测试集：采样 → TTS → ZIP 打包
#
# 支持多种 xlsx 输入方式：
#   单个文件:   ./make_testset.sh corpus/en_nav.xlsx
#   多个文件:   ./make_testset.sh a.xlsx b.xlsx c.xlsx
#   通配符:     ./make_testset.sh corpus/en/*.xlsx
#   整个目录:   ./make_testset.sh corpus/en/
#   混合:       ./make_testset.sh corpus/en/ extra/special.xlsx

set -euo pipefail

# =============================================================================
# ★ 用户配置区 ★
# =============================================================================

# ASR 引擎目录（含 corpus_process.py 和 python_lib/）
# 留空则自动推导为 pipeline/ 的上级目录（即 asr_mlg/）
ENGINE_DIR=""

# 语种索引（见 corpus_process.py 的 num2LagDict，如 0=英语 1=日语）
LANGUAGE=0

# 输出目录（测试集 ZIP 存放位置）
# 留空则从 config/global_config.yaml 的 output_dir 下的 test_sets/manual/ 自动推导
OUTPUT_DIR=""

# 每个 xlsx 采样句数
COUNT=1000

# 发音替换列表（留空则不使用）
REPLACEMENT_LIST=""

# 日志目录（留空则默认写到 OUTPUT_DIR/logs/）
LOG_DIR=""

# Python 解释器（留空则自动从 config/global_config.yaml 读取，fallback python3）
PYTHON=""

# =============================================================================
# 以下无需修改
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$SCRIPT_DIR/tools"
SAMPLER="$TOOLS_DIR/excel_to_txt_sampler.py"
MAKE_TESTSET="$TOOLS_DIR/make_test_set.py"
DEFAULT_CFG="$SCRIPT_DIR/config/global_config.yaml"

# Python 解释器：优先从 global_config.yaml 读取 python_exec，fallback python3
if [[ -z "$PYTHON" ]]; then
    if [[ -f "$DEFAULT_CFG" ]]; then
        PYTHON=$(python3 -c "
import yaml, sys
cfg = yaml.safe_load(open('$DEFAULT_CFG', encoding='utf-8')) or {}
print(cfg.get('python_exec', '') or '')
" 2>/dev/null)
    fi
    PYTHON="${PYTHON:-python3}"
fi

# 引擎目录自动推导：pipeline/ 的上级目录（即 asr_mlg/）
if [[ -z "$ENGINE_DIR" ]]; then
    ENGINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    echo "[INFO] engine_dir 自动推导: $ENGINE_DIR"
fi

# 输出目录：留空则从 global_config.yaml 读取
if [[ -z "$OUTPUT_DIR" ]]; then
    if [[ -f "$DEFAULT_CFG" ]]; then
        OUTPUT_DIR=$($PYTHON - <<PYEOF
import yaml, os
cfg = yaml.safe_load(open("$DEFAULT_CFG", encoding='utf-8')) or {}
asrmlg_exp_dir = cfg.get('asrmlg_exp_dir') or os.path.abspath(os.path.join("$SCRIPT_DIR", '..'))
raw = cfg.get('output_dir') or os.path.join(asrmlg_exp_dir, 'output')
base = raw if os.path.isabs(raw) else os.path.join(asrmlg_exp_dir, raw)
print(os.path.join(base, 'test_sets', 'manual'))
PYEOF
)
        echo "[INFO] output_dir 从配置推导: $OUTPUT_DIR"
    else
        OUTPUT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/output/test_sets/manual"
        echo "[INFO] output_dir 默认推导: $OUTPUT_DIR"
    fi
fi

# 默认日志目录
LOG_DIR="${LOG_DIR:-$OUTPUT_DIR/logs}"

# ---------------------------------------------------------------------------
# 收集 xlsx 文件
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
    echo "用法: $0 <file.xlsx|dir|glob> ..."
    echo ""
    echo "示例:"
    echo "  $0 corpus/en_nav.xlsx"
    echo "  $0 a.xlsx b.xlsx c.xlsx"
    echo "  $0 corpus/en/*.xlsx"
    echo "  $0 corpus/en/"
    exit 1
fi

declare -a XLSX_FILES=()

for ARG in "$@"; do
    if [[ -d "$ARG" ]]; then
        while IFS= read -r -d '' f; do
            XLSX_FILES+=("$f")
        done < <(find "$ARG" -name "*.xlsx" ! -name "~\$*" -print0 | sort -z)
    elif [[ -f "$ARG" && "$ARG" == *.xlsx ]]; then
        XLSX_FILES+=("$ARG")
    else
        echo "[warn] 跳过无效路径: $ARG"
    fi
done

if [[ ${#XLSX_FILES[@]} -eq 0 ]]; then
    echo "[error] 未找到任何 xlsx 文件"
    exit 1
fi

# ---------------------------------------------------------------------------
# 打印配置
# ---------------------------------------------------------------------------
echo ""
echo "=== make_testset: ${#XLSX_FILES[@]} 个文件 ==="
echo "  engine_dir : $ENGINE_DIR"
echo "  language   : $LANGUAGE"
echo "  output_dir : $OUTPUT_DIR"
echo "  count      : $COUNT"
[[ -n "$REPLACEMENT_LIST" ]] && echo "  replacement: $REPLACEMENT_LIST"
echo "  log_dir    : $LOG_DIR"

# ---------------------------------------------------------------------------
# staging 临时目录
# ---------------------------------------------------------------------------
STAGING_DIR="$OUTPUT_DIR/_staging"
mkdir -p "$STAGING_DIR"

SUCCESS=0
FAIL=0

# ---------------------------------------------------------------------------
# 逐个处理
# ---------------------------------------------------------------------------
for XLSX in "${XLSX_FILES[@]}"; do
    STEM="$(basename "${XLSX%.xlsx}")"
    TXT_PATH="$STAGING_DIR/${STEM}.txt"

    echo ""
    echo "[$(date '+%H:%M:%S')] 处理: $STEM"
    echo "  来源: $XLSX"

    # Step 1: 采样提取文本
    if ! $PYTHON "$SAMPLER" -i "$XLSX" -o "$TXT_PATH" -n "$COUNT"; then
        echo "  [error] 提取失败，跳过"
        FAIL=$((FAIL + 1))
        continue
    fi
    echo "  提取: $(wc -l < "$TXT_PATH") 句"

    # Step 2: TTS 合成 + 打包
    TTS_CMD=(
        $PYTHON "$MAKE_TESTSET"
        -e "$ENGINE_DIR"
        -l "$LANGUAGE"
        -i "$TXT_PATH"
        --output "$OUTPUT_DIR"
        --tts
        --log_dir "$LOG_DIR"
    )
    [[ -n "$REPLACEMENT_LIST" && -f "$REPLACEMENT_LIST" ]] && \
        TTS_CMD+=(--replacement_list "$REPLACEMENT_LIST")

    if "${TTS_CMD[@]}"; then
        rm -f "$TXT_PATH"
        SUCCESS=$((SUCCESS + 1))
        echo "  [done] $STEM"
    else
        FAIL=$((FAIL + 1))
        echo "  [failed] $STEM，临时文件保留: $TXT_PATH"
    fi
done

# 清理空 staging 目录
[[ -d "$STAGING_DIR" && -z "$(ls -A "$STAGING_DIR")" ]] && rmdir "$STAGING_DIR"

echo ""
echo "=== 完成：成功 ${SUCCESS}，失败 ${FAIL} / 共 ${#XLSX_FILES[@]} 个 ==="
[[ $FAIL -gt 0 ]] && exit 1 || exit 0
