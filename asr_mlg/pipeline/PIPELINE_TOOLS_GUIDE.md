# ASR Pipeline 工具：详尽使用指南

本手册详细介绍了位于 `asr_mlg/pipeline/` 目录下的自动化工具的功能、命令行参数及实际应用场景。

## 1. 核心语料场景举例：英语车载系统
为了方便理解，本指南统一使用以下英语语料进行举例：
*   **输入文件**：`en_navigation.xlsx`
*   **说法模板 (Sheet: `shuofa`)**：`Navigate to <city>` (导航到`<city>`)
*   **槽位词表 (Sheet: `<>`)**：`<city>` 包含 `London`, `New York`, `Los Angeles`。

---

## 2. 组件详细拆解

### A. 流水线总调度器 (`pipeline_executor.py`)
**功能**：整个系统的"大脑"。读取任务定义（`job.yaml`），并行执行 Phase 1（资源构建/G2P）与 Phase 2（增量测试集生成）。

*   **详细用法**：
    ```bash
    # 从 pipeline/ 目录下运行
    python pipeline_executor.py -j config/job.yaml
    python pipeline_executor.py -j config/job.yaml -g config/global_config.yaml
    ```

*   **Phase 1 流程（资源构建）**：
    1.  检测到 `en_navigation.xlsx` 中出现了新词 `London`，在 `new_dict` 中找不到。
    2.  自动提取 `London` 到 OOV 列表。
    3.  调用 G2P 模型预测发音：`l ah n d ah n`。
    4.  自动将该发音合并入英语主词典。
    5.  重新打包生成 ASR 二进制文件。

*   **Phase 2 流程（增量测试集）**：
    1.  对 `excel_corpus_path` 下每个 `.xlsx` 计算语义哈希。
    2.  与 `{lang}_{msg}_testset_manifest.json` 比对，仅处理有变化的文件。
    3.  并行提取文本（`{msg}_staging/{xlsx_stem}.txt`）→ 串行 TTS 合成 → 打包 ZIP。
    4.  成功后更新 manifest，清理 staging 临时文件。

*   **日志位置**：
    - Phase 1：`logs/{lang}/{msg}/pak_{msg}_{model_type}_{datetime}.log`
    - Phase 2：`logs/{lang}/{msg}/testset_{xlsx_stem}_{datetime}.log`

---

### B. 流水线热身工具 (`warmup.sh` / `tools/pipeline_warmup.py`)
**功能**：首次部署或导入新语料后，预计算所有 Excel 的语义哈希写入 manifest，使 Phase 2 将现有文件识别为"已处理"，避免对存量语料触发全量 TTS 合成。

*   **详细用法**：
    ```bash
    # 推荐：通过 warmup.sh 调用（自动探测 config/global_config.yaml，-g 可省略）
    ./warmup.sh -j config/job.yaml
    ./warmup.sh -j config/job.yaml -g config/global_config.yaml
    ./warmup.sh -j config/job.yaml --dry-run   # 预览，不写入

    # 直接调用 Python（效果相同）
    python tools/pipeline_warmup.py -j config/job.yaml

    # 单任务模式（旧接口）
    python tools/pipeline_warmup.py -c corpus/en/ -m output/test_sets/english_en_nav_testset_manifest.json --msg en_nav
    ```

*   **manifest 路径**：`output/test_sets/{lang_name}_{msg}_testset_manifest.json`
    - warmup 和 pipeline_executor.py 使用**完全相同**的路径规则，确保互通。

*   **英语场景举例**：扫描 `en_nav.xlsx`。即使文件修改时间变了，只要内容没变，哈希不变，下次 Phase 2 直接跳过。

---

### C. 测试集自动生成器 (`tools/make_test_set.py`)
**功能**：输入文本，通过 TTS 引擎合成音频，生成 MLF 标注，打成标准 ZIP 包。通常由 `pipeline_executor.py` Phase 2 自动调用，也可独立使用。

*   **独立调用**：
    ```bash
    python tools/make_test_set.py \
      -e /path/to/engine_dir \
      -l 69260 \
      -i tmp/test_lines.txt \
      --output output/test_sets/english/en_nav \
      --tts \
      --replacement_list config/en_fix.list \
      --log_dir logs/english/en_nav
    ```

*   **输出结构**：
    ```
    output/test_sets/{lang}/{msg}/
    ├── {lang}_{file}_{user}_{YYYYMMDD_HHMMSS}/   # 工作目录（中间文件）
    │   ├── synthesize.txt                          # TTS 合成用（含替换）
    │   ├── filter.txt                              # MLF 标签用（原始文本）
    │   └── wavs_xxxxxx/                            # 合成音频
    └── {lang}_{file}_{user}_{YYYYMMDD}.zip        # 最终交付包
    ```

*   **两个文本文件的区别**：
    - `synthesize.txt`：经替换列表处理后送入 `./ttsSample`，控制发音
    - `filter.txt`：原始文本（仅字符过滤），写入 MLF 作为标注标签
    - 两个文件行数必须严格对齐，否则 wav 与 label 错位

*   **TTS 进度条**：合成时显示实时 tqdm 进度条（需安装 `tqdm`）：
    ```
      TTS |████████░░░░░░░░| 38/75 [00:24<00:23]
    ```

*   **发音修正替换列表 (Replacement List)**：
    - 格式：`原始词 : 修正词`（如 `A : Eh`, `St. : Street`），大小写不敏感
    - 仅影响 `synthesize.txt`（发音），不影响 `filter.txt`（标注）

---

### D. Excel 语料采样器 (`tools/excel_to_txt_sampler.py`)
**功能**：将 ASR 模板 Excel 转换为平铺文本，支持嵌套槽位递归展开（最大深度 20 层）。

*   **详细用法**：
    ```bash
    python tools/excel_to_txt_sampler.py -i corpus/en_nav.xlsx -o tmp/test_lines.txt -n 500
    ```

*   **支持的 Sheet 类型**：
    - `sent`：静态句子列表
    - `shuofa`：模板句（含 `<slot>` 占位符）
    - `<>`：槽位词表（列名即槽位名，如 `<city>`）

*   **英语场景举例**：模板 `Navigate to <city>` + 槽位 `London/New York/Los Angeles` → 随机采样输出 `navigate to new york`。

---

### E. 词典合并工具 (`tools/merge_dict.py`)
**功能**：将 G2P 预测结果安全合并入主词典，逐音素校验合法性。

*   **详细用法**：
    ```bash
    python tools/merge_dict.py -i g2p_out.dict -o res/en_res/ubctc_duan/new_dict -p res/en_res/ubctc_duan/phones.syms
    ```

*   **校验逻辑**：每个音素必须在 `phones.syms` 中存在，否则整词拒绝合并并输出 `[REJECTED]`，防止非法音素污染词典导致打包崩溃。

---

### F. 词典版本控制系统 (`tools/lexicon_vcs.py`)
**功能**：为词典提供快照与回滚，类似轻量级 Git。

*   **详细用法**：
    ```bash
    # 查看历史
    python tools/lexicon_vcs.py -i res/en_res/ubctc_duan/new_dict log

    # 回滚到指定快照
    python tools/lexicon_vcs.py -i res/en_res/ubctc_duan/new_dict rollback -t b3f5e12
    ```

*   **触发时机**：`pipeline_executor.py` Step 3 合并前自动调用 `pre_merge` 快照，合并成功后调用 `post_merge` 提交记录。

---

## 3. 路径配置说明

### `global_config.yaml` 中路径的基准目录

| 配置项 | 相对路径基准 |
|---|---|
| `tools_dir`, `merge_dict_script`, `g2p_root_dir`, `g2p_replacement_list` | `pipeline/` 目录 |
| `train_script`, `eval_script` | `asrmlg_exp_dir`（主工程目录） |
| 所有配置项 | 绝对路径直接使用，不做转换 |

### 默认路径自动推导（无需配置）

| 配置项 | 默认值 |
|---|---|
| `asrmlg_exp_dir` | `pipeline/` 的父目录（即 `asr_mlg/`） |
| `output_dir` | `asrmlg_exp_dir/output/` |
| `log_dir` | `output_dir/logs/` |
| `g2p_root_dir` | `pipeline/g2p/` |
| `tools_dir` | `pipeline/tools/` |

---

## 4. 技术实现细节

1.  **全局并发锁**：TTS 引擎（`.tts_global_engine.lock`）和 G2P 引擎（`.g2p_engine_exec.lock`）均使用 `fcntl.LOCK_EX` 排他锁，多任务并行时自动串行化引擎调用。

2.  **增量哈希策略**：使用**语义哈希**（基于 Excel 文本内容的 MD5），忽略文件元数据变化。manifest key 为文件名（非路径），与 `pipeline_warmup.py` 保持一致。

3.  **per-xlsx 粒度**：Phase 2 中每个 `.xlsx` 文件独立走 extract→TTS→package 流程，单个文件失败不影响其他文件，manifest 也按文件粒度更新。

4.  **递归槽位展开**：采样器支持 `<city_group>` 嵌套 `<major_city>`，最大深度 20 层，避免无限递归。

---

**维护者**：tyliu23
**更新日期**：2026-04-22
