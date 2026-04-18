# ASR MLG & Pipeline 集成文档

本文档说明了将 `asr_pipeline` 功能集成到 `asr_mlg` 项目后的结构、环境配置及使用方法。

## 1. 项目结构变更

集成后的目录结构如下（主要新增内容）：

```text
asr_mlg/
├── pipeline/                # 原 asr_pipeline 核心逻辑
│   ├── pipeline_executor.py # 调度执行器（已针对新路径适配）
│   ├── tools/               # 辅助工具脚本
│   │   ├── excel_to_txt_sampler.py
│   │   ├── lexicon_vcs.py
│   │   ├── make_test_set.py
│   │   ├── merge_dict.py
│   │   └── pipeline_warmup.py
│   └── README.md            # 原 pipeline 说明文档
├── language_map             # [新增] 语种 ID 与简称映射表，供 corpus_process.py 使用
├── bin/                     # 二进制工具 (ngram-count, package_ed_sp_v2 等)
├── yun_ser/                 # WFST 序列化工具
├── corpus_process.py        # 语料处理核心逻辑
├── corpus_process_package.py # 打包主程序
└── run_*.sh                 # 各语种执行示例脚本
```

## 2. 环境配置

项目依赖 Python 3.9+ 及以下库。建议使用 `mamba` 或 `conda` 安装：

### 2.1 安装基础依赖
```bash
mamba install -y pandas xlrd pythainlp spacy pyyaml sudachipy sudachidict-core
```

### 2.2 下载 NLP 模型
针对日语处理，需要下载 `spacy` 模型：
```bash
python -m spacy download ja_core_news_lg --no-deps
```

## 3. 核心功能说明

### 3.1 自动化流水线 (Pipeline Executor)
位于 `asr_mlg/pipeline/pipeline_executor.py`。它可以串联 OOV 提取、G2P 预测、词典合并及 ASR 资源打包的全过程。

**执行命令示例：**
```bash
python asr_mlg/pipeline/pipeline_executor.py -g global_config.yaml -j job.yaml
```

*注：`pipeline_executor.py` 已修改 `resolve_and_bind_paths` 逻辑，默认将 `asrmlg_exp_dir` 指向 `asr_mlg` 根目录。*

### 3.2 语料处理与打包 (ASR MLG Core)
原有的 `corpus_process_package.py` 逻辑保持不变。你可以继续使用根目录下的 `run_*.sh` 脚本进行单步或手动任务。

**主要参数参考：**
- `-l`: 语种 ID (参考 `language_map`)
- `--excel_corpus_path`: 定制语料路径
- `--is_yun`: 打包版本控制 (0: ubctc, 1: rnnt_ctc, 2: rnnt_ed, 3: yun)

## 4. 重要修正与适配

1.  **路径解耦**：`pipeline_executor.py` 现在位于子目录中，其内部通过 `os.path.abspath(os.path.join(base_path, '..'))` 自动定位主项目的资源和脚本，无需手动修改代码中的硬编码路径。
2.  **缺失资源补全**：
    *   创建了 `asr_mlg/language_map`：解决了 `corpus_process.py` 初始化时因读取不到该文件而报错的问题。
    *   模型兼容：集成了 `pythainlp` (泰语) 和 `spacy` (日语) 的分词与处理依赖。
3.  **安全性**：所有集成操作均在 `asr_mlg/pipeline/` 下进行，未修改 `asr_mlg` 原始的核心算法脚本（如 `corpus_process.py`），确保了原始功能的稳定性。

---
**维护者：** tyliu23  
**最后更新：** 2026-04-18
