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
**功能**：整个系统的“大脑”。它负责读取任务定义（`job.yaml`），并按顺序执行语料处理、OOV 提取、G2P 预测、词典合并及最终打包。

*   **详细用法**：
    ```bash
    # 只需要指定任务文件，路径会自动推导
    python pipeline/pipeline_executor.py -j pipeline/job_en.yaml
    ```
*   **英语场景流程**：
    1.  检测到 `en_navigation.xlsx` 中出现了新词 `London`，但在 `new_dict` 中找不到。
    2.  自动提取 `London` 到 OOV 列表。
    3.  调用 G2P 模型预测 `London` 的发音：`l ah n d ah n`。
    4.  自动将该发音合并入英语主词典。
    5.  调用 `bin/` 下的工具压制成最后的 ASR 二进制文件。

### B. Excel 语料采样器 (`tools/excel_to_txt_sampler.py`)
**功能**：将复杂的 ASR 模板 Excel 转换为平铺的文本文件，用于制作测试集或语音合成。支持嵌套槽位递归展开。

*   **详细用法**：
    ```bash
    python pipeline/tools/excel_to_txt_sampler.py -i corpus/en_nav.xlsx -o tmp/test_lines.txt -n 500
    ```
*   **英语场景举例**：
    *   **输入**：模板 `Navigate to <city>`。
    *   **处理**：随机从槽位表挑选 `New York`。
    *   **输出**：文本文件中写入 `navigate to new york`。

### C. 测试集自动生成器 (`tools/make_test_set.py`)
**功能**：输入文本，通过 TTS 引擎自动合成音频，并生成 MLF 标注文件，最后打成标准的 ZIP 包。

*   **详细用法**：
    ```bash
    # --tts 开启合成，--replacement_list 指定发音修正表
    python pipeline/tools/make_test_set.py -e . -l 26 -i tmp/test_lines.txt --output output/en_testset --tts --replacement_list config/en_fix.list
    ```

*   **核心特性：发音修正替换列表 (Replacement List)**：
    *   **文件格式**：每行一个映射，格式为 `原始词 : 修正词`（例如 `A : Eh`, `St. : Street`）。
    *   **英语场景举例**：
        1.  **缩写展开**：原始文本是 `Drive to St. John`，通过修正表 `St. : Street`，TTS 引擎会合成 `Drive to Street John` 的音频，但 MLF 标注依然保留原始的 `St.`。
        2.  **强制音标引导**：如果 TTS 把 `Adele` 读错了，你可以在修正表里写 `Adele : Ah-dell`，引导引擎发出正确的重音，从而生成更高质量的测试音频。

*   **英语场景流程**：
    1.  读取 `navigate to new york`。
    2.  **应用替换列表**：检查是否有需要修正的词汇。
    3.  调用 **XTTS 引擎** 合成 `audio_001.wav`。
    4.  生成 `en_testset.mlf` 记录音频与文字的对应关系。
    5.  打包为 `en_testset.zip`。

### D. 词典合并工具 (`tools/merge_dict.py`)
**功能**：安全性极高的合并工具。在将 G2P 结果并入主词典前，它会检查每一个音素是否在项目定义的音素表（`phones.syms`）中。

*   **详细用法**：
    ```bash
    python pipeline/tools/merge_dict.py -i g2p_out.dict -o res/en_res/new_dict -p res/en_res/phones.syms
    ```
*   **英语场景举例**：
    *   G2P 预测 `Adele` -> `ah d eh l`。
    *   工具检查 `ah`, `d`, `eh`, `l` 是否全都在英语音素表里。
    *   如果有非法音素（如模型幻觉产生的符号），该词会被拒绝合并，防止后续打包流程崩溃。

### E. 词典版本控制系统 (`tools/lexicon_vcs.py`)
**功能**：为词典文件提供类似 Git 的快照和回滚功能。

*   **详细用法 (自动备份)**：
    ```bash
    python pipeline/tools/lexicon_vcs.py -i res/en_res/new_dict pre_merge
    ```
*   **详细用法 (回滚)**：
    ```bash
    python pipeline/tools/lexicon_vcs.py -i res/en_res/new_dict rollback -t b3f5e12
    ```
*   **英语场景举例**：在一次性合并 1000 个美国地名发音前，系统会自动创建备份。如果合并后发现格式错误，可以通过哈希值一键秒回滚。

### F. 流水线热身工具 (`tools/pipeline_warmup.py`)
**功能**：预先对所有 Excel 语料计算 **语义哈希 (Semantic Hash)**，实现“秒级增量打包”。

*   **详细用法**：
    ```bash
    python pipeline/tools/pipeline_warmup.py -c corpus/ -m manifest.json --msg "EnProject"
    ```
*   **英语场景举例**：扫描 `en_nav.xlsx`。即使文件修改时间变了，只要里面的句子没变，哈希值就保持不变。下次运行流水线时，程序会直接跳过已经处理过的文件。

---

## 3. 技术实现细节 (Maintainer: tyliu23)

1.  **全局并发锁**：由于底层的 TTS 二进制引擎和某些 G2P 引擎不是线程安全的，`pipeline_executor.py` 和 `make_test_set.py` 内部实现了基于文件的排他锁 (`.lock`)，确保多个任务并行时不会抢夺同一个引擎资源导致崩溃。
2.  **智能路径识别**：所有工具均支持零配置。它们通过识别自身位于 `pipeline/` 目录，自动向上定位 `asr_mlg` 根目录下的 `bin/`、`res/` 和核心脚本。
3.  **递归槽位展开**：在采样英语语料时，支持 `Navigate to <city_group>`，其中 `<city_group>` 可以继续嵌套 `<major_city> | <small_town>`，实现复杂逻辑的极简定义。

---
**维护者**：tyliu23  
**日期**：2026-04-18
