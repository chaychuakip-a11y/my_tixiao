# ASR Pipeline 开发者深度手册 V3.0

> **阅读导航**：
> - 快速定位修改点 → 第 0 节速查表
> - 配置文件怎么写 → 第 1 节
> - 已知 Bug 和设计缺陷 → 第 2 节（重要，避坑必读）
> - 每个函数的精细逻辑 → 第 3～7 节

---

## 0. 快速修改速查表

| 你想改什么 | 文件 | 行号 | 改什么 |
| :--- | :--- | :--- | :--- |
| MD5 后缀取几位 | `pipeline_executor.py` | L38 | `suffix_len=4` |
| 默认打包脚本文件名 | `pipeline_executor.py` | L135 | `'corpus_process_package.py'` |
| Phase1 最大并发任务数 | `pipeline_executor.py` | L729 | `max_workers=4` |
| 所有任务共用的 log 文件路径 | `pipeline_executor.py` | L731 | `"logs/build.log"` |
| 新增语言 ID → 缩写映射 | `pipeline_executor.py` | L129 | `lang_abbr_map` 字典 |
| 新增 is_yun 架构类型 | `pipeline_executor.py` | L127 | `res_dir_map` 字典 |
| 输出目录名里的 `model_type` 来自哪里 | `pipeline_executor.py` | L703 | `scheme_map`（无默认值，必须在 global_config.yaml 里设） |
| Whisper 触发条件 | `pipeline_executor.py` | L625 | `is_yun == '3'` |
| Whisper 产物命名格式 | `pipeline_executor.py` | L684 | `exact_bin_name` |
| Whisper .bin 实际写到哪个目录 | `pipeline_executor.py` | L612 | `./output/` 相对 `wearlized_dir` |
| G2P input.txt 路径 | `pipeline_executor.py` | L431 | `g2p_lang_dir/"input.txt"` |
| G2P output.dict 路径（共享） | `pipeline_executor.py` | L432 | `g2p_lang_dir/"output.dict"` |
| G2P 私有产物路径（step2 存但 step3 不用） | `pipeline_executor.py` | L433 | `task_out_path_temp/g2p_output_{msg}.dict` |
| step3 实际读的 G2P 文件（潜在并发 bug） | `pipeline_executor.py` | L528 | 还是读 `output.dict` 共享文件 |
| G2P 全局锁文件名 | `pipeline_executor.py` | L446 | `.g2p_engine_exec.lock` |
| 走云端 G2P 的语言列表 | `pipeline_executor.py` | L469 | `cloud_g2p_langs` 配置项 |
| 判断是否希伯来语 | `pipeline_executor.py` | L456 | `['he','heb','hebrew']` |
| 希伯来语中用到的 `re` 模块（有 Bug） | `pipeline_executor.py` | L333 | 缺少 `import re`，详见第 2 节 |
| lang_abbr 找不到时的最终 fallback | `pipeline_executor.py` | L423 | `task.get('language', msg)` |
| 主词典路径拼法 | `pipeline_executor.py` | L518-519 | `res/{lang_name}_res/{res_dir_name}/new_dict` |
| phones.syms 找不到时的 fallback | `pipeline_executor.py` | L525 | `phones.list.noblank` |
| `predict_phone_for_new` 开关注入位置 | `pipeline_executor.py` | L544 | `merge_cmd.append(...)` |
| step3 merge 失败时的返回值（有 Bug） | `pipeline_executor.py` | L560 | 无论成败都 `return True` |
| `check_whisper_dependencies` 被谁调用 | `pipeline_executor.py` | L584 | **没有人调用**，是死代码 |
| Phase 2 测试集生成的实现状态 | `pipeline_executor.py` | L747 | **`pass`，完全未实现** |
| build_base_command 单横杠参数 | `pipeline_executor.py` | L358 | `single_dash_whitelist` |
| build_base_command 不传给核心脚本的键 | `pipeline_executor.py` | L361-364 | `internal_keys` |
| build_base_command 需要转绝对路径的键 | `pipeline_executor.py` | L366-372 | `path_keys` |
| 词典合并音素校验失败时的日志标记 | `tools/merge_dict.py` | L84 | `[REJECTED]` 打到 stderr |
| 词典写入强制 Linux 换行 | `tools/merge_dict.py` | L94 | `newline='\n'` |
| VCS 备份文件命名格式 | `tools/lexicon_vcs.py` | L76 | `{name}.v{ts}.{hash7}.bak` |
| VCS hash 取前几位（与 get_file_md5_suffix 不同） | `tools/lexicon_vcs.py` | L45 | `[:7]` 取前 7 位 |
| VCS 日志保留行数是 max_versions 的几倍 | `tools/lexicon_vcs.py` | L138 | `max_versions * 2` |
| TTS 全局锁文件名 | `tools/make_test_set.py` | L143 | `.tts_global_engine.lock` |
| TTS 引擎目录位置 | `tools/make_test_set.py` | L118 | `{engine_dir}/xtts20_for_asr/bin_tts` |
| TTS UUID 长度（隔离私有目录用） | `tools/make_test_set.py` | L124 | `hex[:6]` |
| 发音修正表文件格式 | `tools/make_test_set.py` | L237-238 | `原词 : 替换词`，冒号分隔 |
| 发音修正是否区分大小写 | `tools/make_test_set.py` | L246 | `.upper()` 不区分 |
| 槽位递归最大深度 | `tools/excel_to_txt_sampler.py` | L85 | `max_depth = 20` |
| 模板扩充最大尝试次数 | `tools/excel_to_txt_sampler.py` | L127 | `needed * 15` |
| warmup 跳过 Office 临时锁文件 | `tools/pipeline_warmup.py` | L95 | `~$` 前缀 |
| warmup 用文件名（非路径）作 manifest key | `tools/pipeline_warmup.py` | L98 | `file_key = file` |
| warmup 与 DeltaTracker 哈希逻辑是否同步 | 两处都要改 | executor:L181 / warmup:L20 | 完全相同逻辑，任意改一处需同步另一处 |

---

## 1. 配置文件完整格式说明

### 1.1 `job.yaml` — 任务定义文件（必须提供）

`job.yaml` 的顶层结构是 `tasks` 列表，每个元素是一个 task 字典。

```yaml
tasks:
  - msg: "en_nav_v2"           # 任务名，用于日志、产物目录、--msg 参数
    l: 26                      # 语言 ID（单横杠 -l 传给核心脚本）
    is_yun: 0                  # 架构类型：0=CTC, 1=RNNT+CTC, 2=RNNT_ED, 3=Whisper/云端
    
    # ---------- 路径参数（相对 asrmlg_exp_dir，自动转绝对路径） ----------
    excel_corpus_path: corpus/en_navigation.xlsx   # 语料 Excel
    cp: corpus/en_navigation.xlsx                  # 单横杠 -cp
    np: norm_corpus/en_nav_norm.xlsx               # 单横杠 -np（归一化语料）
    dict: res/En_res/ubctc_duan/new_dict           # 当前词典路径
    word_syms: res/En_res/ubctc_duan/words.syms
    phone_syms: res/En_res/ubctc_duan/phones.syms
    triphone_syms: res/En_res/ubctc_duan/triphones.syms
    hmm_list: res/En_res/ubctc_duan/hmm_list
    hmm_list_blank: res/En_res/ubctc_duan/hmm_list_blank
    mapping: res/En_res/ubctc_duan/mapping
    
    # ---------- 流水线阶段开关 ----------
    enable_g2p: true           # 是否执行 Step2 G2P 预测
    enable_merge_dict: true    # 是否执行 Step3 词典合并
    enable_testset: true       # 是否触发 Phase2 测试集生成（Phase2 当前未实现）
    enable_eval: false         # 是否触发 Phase3 评测
    enable_whisper_package: false  # 是否执行 Step5 Whisper 序列化（需 is_yun=3）
    
    # ---------- 可选行为开关 ----------
    predict_phone_for_new: true   # 合并词典时对新词重新预测音素（传给 merge_dict.py）
    
    # ---------- Whisper 子配置（仅 is_yun=3 时有效） ----------
    whisper_config:
      work_dir: "En_nav_patch_20260101"        # 工作目录名，在 whisper_tools_dir 下创建
      name: "tyliu23_en_nav_20260101"          # patch 名，注入产物文件名
      patch_type: "nav"                        # patch 类型，注入产物文件名
      patch_scale: "1.0"                       # LM 权重因子，写入 .cfg 的 common.lm_factor
      train_dict: "g2p/En/g2p_models/train.dict"  # 训练词典路径（相对 asrmlg_exp_dir）
      phoneset: "res/En_res/whisper/phoneset"     # 音素集路径
      package_ed_target: "res/En_res/whisper/ed_target"  # package_ed 的目标参数
```

**字段分类说明**：
- 在 `build_base_command`（L347）里，字典中所有未在 `internal_keys`（L361）中的键都会被组装成 CLI 参数。
- `internal_keys` 中的键（`enable_g2p`、`whisper_config` 等）只被 pipeline 内部读取，**不会传递给 `corpus_process_package.py`**。
- `single_dash_whitelist`（L358）中的键（`l`、`G`、`cp`、`np`）用单横杠，其余用双横杠。

---

### 1.2 `global_config.yaml` — 全局配置文件（可选，不提供则零配置推导）

```yaml
# ===== 路径覆盖（不写则自动推导，详见 resolve_and_bind_paths L91） =====
python_exec: /home/user/miniconda3/envs/asr/bin/python  # 不写则用 sys.executable
asrmlg_exp_dir: /data/asr_mlg                 # 不写则取 pipeline/ 的上一级目录
output_dir: /data/asr_mlg/output              # 不写则 asrmlg_exp_dir/output
tools_dir: /data/asr_mlg/pipeline/tools       # 不写则 pipeline/tools
g2p_root_dir: /data/asr_mlg/g2p               # 不写则 asrmlg_exp_dir/g2p

# ===== 脚本名（相对 asrmlg_exp_dir） =====
train_script: corpus_process_package.py       # 核心打包脚本，L135
eval_script: evaluate.py                      # 评测脚本，L137
language_map_name: language_map               # 语言映射文件名，L767（无扩展名）

# ===== 映射表（不写则用代码内置默认值） =====
res_dir_map:                                  # is_yun → 资源目录名，L127
  "0": ubctc_duan
  "1": rnnt_ctc_duan
  "2": rnnt_ed_duan
  "3": yun

lang_abbr_map:                                # 语言 ID → G2P 目录缩写，L129
  "26": En
  "5": En
  "69160": Ja
  "69500": Ko
  "69400": Th

scheme_map:                                   # is_yun → 产物目录名前缀，【无默认值！】
  "0": ctc                                    # 不写则 model_type='unknown'，L706
  "1": rnnt
  "2": rnnt_ed
  "3": whisper

res_dir_name: res                             # 资源根目录名，L131

# ===== 行为开关 =====
cloud_g2p_langs: ["Ja", "Ko"]                 # 使用 run_cloud.sh 的语言列表，L469
max_versions: 10                              # VCS 保留版本数，L557

# ===== Whisper 专属 =====
whisper_tools_dir: /data/whisper_tools        # Whisper 工具目录，L648（不写则用 asrmlg_exp_dir）

# ===== 其他 =====
g2p_replacement_list: config/g2p_fix.list     # G2P 替换列表，L147（相对 asrmlg_exp_dir）
```

**关键注意**：`scheme_map` 在 `resolve_and_bind_paths` 中**没有默认值**（L703 直接 `global_cfg.get('scheme_map', {})`）。不配置时 `model_type` 恒为 `'unknown'`，输出目录名将是 `unknown_20260101/`。

---

## 2. 已知设计缺陷与潜在 Bug

> 以下为通过代码审查发现的问题，修复前请了解影响范围。

---

### Bug-1：`re` 模块未导入，希伯来语必崩 ⚠️

- **位置**：`pipeline_executor.py:333`
- **现象**：当 `lang_abbr in ['he', 'heb', 'hebrew']` 时，`generate_context_for_hebrew_oov` 在 L333 执行 `re.sub(r'<[^>]+>', '', context_sent)`，但文件顶部（L13–33）**没有 `import re`**。
- **触发路径**：Hebrew 语言 + OOV 词属于某个槽位时（优先级 2 分支）触发。
- **报错**：`NameError: name 're' is not defined`
- **修复**：在文件顶部 import 区（约 L20 附近）添加 `import re`。

---

### Bug-2：Step3 读取 G2P 共享文件，并发场景有竞争窗口 ⚠️

- **位置**：`pipeline_executor.py:528`
- **现象**：Step2（L475）在拿到锁后把结果 copy 到私有文件 `g2p_output_{msg}.dict`，但 Step3（L528）直接读 G2P 引擎目录下的**共享** `output.dict`，而非私有副本。
- **触发条件**：两个不同语言任务并发，任务 A 的 Step3 运行时，任务 B 的 Step2 已经覆盖了 `output.dict`。
- **具体代码**：
  ```python
  # Step2 写私有副本 (L433, L475)
  private_output_dict = Path(task_out_path_temp) / f"g2p_output_{msg}.dict"
  shutil.copy2(g2p_output_dict_shared, private_output_dict)

  # Step3 却读共享文件 (L528) ← 与 private_output_dict 无关
  g2p_output_dict = os.path.join(g2p_root_dir, lang_abbr, "g2p_models", "output.dict")
  ```
- **修复方向**：Step3 应优先使用 `{task_out_path_temp}/g2p_output_{msg}.dict`，共享文件作 fallback。

---

### Bug-3：Step3 失败时静默返回 True，不中断流水线 ⚠️

- **位置**：`pipeline_executor.py:560`
- **现象**：`step3_merge_dict` 最后一行无论 merge 是否成功都 `return True`（`merge_success` 变量被计算但不影响返回值）。
- **影响**：词典合并失败后，Step4 仍会继续执行，用旧词典打包，不报错，产物悄悄变"假好"。
- **位置对比**：
  ```python
  merge_success = run_subprocess(merge_cmd, ...)  # L547，计算了返回值
  if merge_success and ...: vcs.post_merge(...)    # L550，只用于决定是否执行 VCS
  return True   # L560，永远返回 True！
  ```
- **修复**：将 L560 改为 `return merge_success`。

---

### Bug-4：`check_whisper_dependencies` 是死代码，从未被调用

- **位置**：`pipeline_executor.py:584–591`
- **现象**：函数定义了检查三个产物文件是否存在的逻辑，但在整个文件中没有任何地方调用它。
- **实际影响**：Step5 内部（L665–669）用 `if os.path.exists(src): ... else: return False` 手动检查，与 `check_whisper_dependencies` 逻辑等价但重复。
- **建议**：在 `step5_whisper_package` 的入口处调用 `check_whisper_dependencies(hybridcnn_gpatch)`，删除 L665–669 的手动检查。

---

### Bug-5：Whisper 产物 `.bin` 未被拷贝到 `final_whisper_out` 目录

- **位置**：`pipeline_executor.py:651–652` 与 `L612`
- **现象**：
  - `final_whisper_out` 目录被创建（L651–652），成功日志里也打印了这个路径（L693）。
  - 但 `generate_custom_cfg`（L612）把 `.bin` 输出路径写为 `./output/{bin_name}`，这是相对 `wearlized_dir` 的路径（即 `{whisper_tools_dir}/wearlized/output/`）。
  - **`.bin` 实际写入 `wearlized/output/`，`final_whisper_out` 目录永远是空的。**
- **影响**：交付给下游的路径是错的，`final_whisper_out` 里没有任何文件。
- **修复**：在 `step5_whisper_package` 末尾（L691 之后）添加把 `.bin` 从 `wearlized/output/` 复制到 `final_whisper_out` 的逻辑。

---

### Bug-6：Phase 2（测试集生成）完全未实现

- **位置**：`pipeline_executor.py:740–747`
- **现象**：`execute_testset_phase` 函数体只有一行 `pass`，只打了一行标题日志。
- **影响**：`main()` 中（L773）提交了这个函数但它不做任何事，`enable_testset: true` 配置完全没效果。
- **注意**：Phase 2 的实现逻辑（读 Excel → 增量判断 → TTS 生成 → 打包）在 `tools/make_test_set.py` 和 `tools/excel_to_txt_sampler.py` 中已存在，但尚未被 `execute_testset_phase` 调用。

---

### 设计限制-1：warmup 用文件名（不含路径）作 manifest key

- **位置**：`tools/pipeline_warmup.py:98`
- **现象**：`file_key = file`（只取文件名）。若不同子目录下有两个同名 Excel（如 `en/data.xlsx` 和 `zh/data.xlsx`），后扫描的会覆盖前者的 hash 记录。
- **影响**：增量判断可能失效，相同文件名的不同语言数据可能被跳过重建。

---

### 设计限制-2：所有并发任务写同一个 log 文件

- **位置**：`pipeline_executor.py:731`
- **现象**：4 个并发进程（`max_workers=4`）都往 `output/logs/build.log` 追加写。
- **影响**：多任务的日志行会交错混在一起，排查时需要依靠 `[HH:MM:SS]` 时间戳和 `for {msg}` 字样手工分离。

---

## 3. `pipeline_executor.py` — 逐函数精讲

### 3.1 `get_file_md5_suffix` (L38–48)

```python
def get_file_md5_suffix(file_path: str, suffix_len: int = 4) -> str:
```

- **用途**：给 `.bin` 产物文件打可追溯后缀。
- **读取方式**：4 MB 分块（`4096 * 1024`，L46），大文件安全。
- **取尾**：`hexdigest()[-suffix_len:]`（L48），取最后 N 位。
- **与 VCS hash 的区别**：VCS 的 `_get_md5`（`lexicon_vcs.py:45`）取 **前 7 位**，这里取**末尾 4 位**，注意不要混淆。

---

### 3.2 `load_language_map` (L51–68)

- **文件格式**：每行 `key: value`，冒号分隔，空行和无冒号行跳过（L63–64）。
- **文件位置**：`{asrmlg_exp_dir}/{language_map_name}`，`language_map_name` 默认为 `language_map`（L767），**无文件扩展名**。
- **值统一小写**：L67 → `.lower()`，存入的缩写全为小写（`en`、`ja` 等）。
- **找不到文件**：`sys.exit(1)`（L61–62），不静默失败。
- **注意**：`lang_abbr_map`（L129）中的值用大写（`'En'`、`'Ja'`），`load_language_map` 存的是小写（`'en'`、`'ja'`），两者用途不同，不要混用：
  - `lang_abbr_map`：用于拼 G2P 目录路径（`g2p/En/g2p_models/`）。
  - `parsed_language_map`（`load_language_map` 结果）：用于拼资源目录路径（`En_res/`）和输出目录名。

---

### 3.3 `run_subprocess` (L71–88)

所有外部命令的唯一执行入口，包括打包工具、G2P、合并脚本、VCS。

- **日志追加**：`open(log_file, 'a')`（L79），多次调用不覆盖，多进程并发追加写（无加锁，行可能交错）。
- **日志自动建目录**：L78 `Path(log_file).parent.mkdir(parents=True, exist_ok=True)`。
- **时间戳写法**：每条命令前写一行 `[HH:MM:SS] CMD: {命令}`（L80）。
- **env 参数**：可传入覆盖后的环境变量字典，不传则继承父进程环境（L76, L82）。
- **返回值**：`returncode == 0`（L84）；异常写 `[fatal error] {e}` 并返回 False（L86–88）。

---

### 3.4 `resolve_and_bind_paths` (L91–157)

**所有配置键的默认值推导逻辑**：

| 键名 | 有默认值？ | 默认值 | 推导基准 | 代码行 |
| :--- | :--- | :--- | :--- | :--- |
| `python_exec` | 有 | `sys.executable` | — | L101–105 |
| `asrmlg_exp_dir` | 有 | `pipeline/` 的上一级 | `__file__` | L108–111 |
| `output_dir` | 有 | `asrmlg_exp_dir/output` | `asrmlg_exp_dir` | L113–115 |
| `tools_dir` | 有 | `pipeline/tools` | `base_path` | L117–119 |
| `g2p_root_dir` | 有 | `asrmlg_exp_dir/g2p` | `asrmlg_exp_dir` | L121–123 |
| `res_dir_map` | 有 | 见上文 1.2 节 | — | L127 |
| `lang_abbr_map` | 有 | 见上文 1.2 节 | — | L129 |
| `res_dir_name` | 有 | `'res'` | — | L131 |
| `train_script` | 有 | `'corpus_process_package.py'` | — | L135 |
| `merge_dict_script` | 有 | `pipeline/tools/merge_dict.py` | `base_path` | L136 |
| `eval_script` | 有 | `'evaluate.py'` | — | L137 |
| **`scheme_map`** | **无** | **`{}` → `model_type='unknown'`** | — | **L703** |

**相对路径解析规则**（L144–155）：
- `tools_dir`、`merge_dict_script` → 相对 `pipeline/` 目录（`base_path`）。
- 其他路径键（`g2p_root_dir`、`eval_script`、`g2p_replacement_list`、`adapter_script`、`test_script`）→ 相对 `asrmlg_exp_dir`。

---

### 3.5 `DeltaTracker` 类 (L164–251)

#### `get_semantic_hash` (L181–237)

对 Excel 文件计算"语义哈希"，识别真实内容变化而非保存时间变化。

**Sheet 识别优先级（三档，按顺序执行）**：

| 档位 | 触发条件 | 提取的内容 | 代码行 |
| :--- | :--- | :--- | :--- |
| 优先 | sheet 名含 `sent` 或 `shuofa`（不区分大小写） | 整个 sheet 所有单元格扁平化后的非空字符串 | L197–206 |
| 次级 | sheet 名含 `<>`（含义：含槽位的 slot sheet） | 列名以 `<` 开头且以 `>` 结尾的列的所有值，前置列名本身 | L208–215 |
| fallback | 上面两档都没命中 | sheet[0] 的 `text` 列；没有 `text` 列则取整个 sheet[0] | L217–225 |

**哈希失败降级**（L235–237）：解析 Excel 抛任何异常 → 对整个文件做二进制 MD5（慢但安全）。

**存储 key**（L247）：用 `os.path.basename(file_path)`（只有文件名），与 warmup 的 key（`file_key = file`，L98）保持一致。

**save/update 时机**（L239–251）：
- `save()` → 将 `self.history` 序列化为 JSON 到 `manifest_path`（L239–243）。
- `update_history()` → 更新内存中的 dict（L245–251），需手动调用 `save()` 才落盘。

---

### 3.6 `generate_context_for_hebrew_oov` (L258–344)

**触发条件**：`step2_g2p_predict:L456` → `lang_abbr.lower() in ['he', 'heb', 'hebrew']`。

**从语料目录读取三类数据**（L275–306）：
- `sent_list`：所有 `sent` sheet 的句子。
- `shuofa_list`：所有 `shuofa` sheet 的说法模板。
- `slot_dict`：所有 `<>` sheet 的槽位词表。
- fallback：无特殊 sheet 时读 `text` 列或第一列（L301–306）。

**为每个 OOV 生成上下文的三级逻辑**：

| 优先级 | 策略 | 代码行 |
| :--- | :--- | :--- |
| 1 | 在 `sent_list` 里找第一个包含该 OOV 的完整句子 | L315–320 |
| 2 | 找 OOV 所在的槽位，随机选含该槽位的 shuofa 模板，填入 OOV，其他槽位随机填，最后用 `re.sub(r'<[^>]+>', '', ...)` 清除剩余未填槽位 | L322–337 |
| 3 | 兜底：直接写 OOV 单词本身 | L338–340 |

**⚠️ Bug-1（见第 2 节）**：L333 使用 `re.sub` 但顶部没有 `import re`，优先级 2 分支会抛 `NameError`。

---

### 3.7 `build_base_command` (L347–394)

**命令头**（L352–355）：
- 若 `train_script` 以 `.py` 结尾 → 用 `python_exec` 执行。
- 否则 → 用 `bash` 执行（支持 `.sh` 脚本）。

**四类参数处理规则**：

| 分类 | 判断条件 | 处理方式 | 代码行 |
| :--- | :--- | :--- | :--- |
| 内部参数（不传出） | key 在 `internal_keys` 里 | 跳过 | L362–364, L375–376 |
| 单横杠参数 | key 在 `single_dash_whitelist` 里 | `-key val` | L358, L379–380 |
| 其他多字母参数 | 默认 | `--key val` | L382 |
| 单字母参数（非白名单） | `len(key) == 1` | `-key val` | L382 |
| bool 参数（True） | `isinstance(val, bool) and val` | 只追加 flag，不加 val | L384–387 |
| bool 参数（False） | `isinstance(val, bool) and not val` | 完全跳过，不加 flag | L384–387 |
| None 值 | `val is None` | 跳过 | L376 |
| 路径键（相对路径） | key 在 `path_keys` 里且是相对路径 | 转为绝对路径（`asrmlg_exp_dir` 为基） | L389–390 |

**path_keys 完整列表**（L366–372）：
```
excel_corpus_path, norm_excel_corpus_path, norm_train_data_slot,
norm_train_data_shuofa, np, train_data_slot, train_data_shuofa, cp,
word_syms, phone_syms, triphone_syms, dict,
hmm_list, hmm_list_blank, mapping
```

---

### 3.8 Step 1：`step1_extract_oov` (L397–406)

- **临时目录**：`task_out_path + "_temp"`（L403），OOV 提取专用。
- **追加参数**：`--only_corpus_process --output {temp_path}`（L404），不会生成 `.bin`，只跑语料处理流程。
- **OOV 产出文件**（被 Step2 消费）：
  ```
  {task_out_path}_temp/custom_corpus_process/dict_dir/aaa_oov_base_dict
  ```
  这是 Step2（L416–417）读取的固定路径，不可改变（由核心脚本 `corpus_process_package.py` 决定）。

---

### 3.9 Step 2：`step2_g2p_predict` (L409–487)

**完整执行流程**：

```
1. 读 OOV 文件 (L416-420) ─→ 空则直接 return True（跳过 G2P）
2. 拼接 G2P 目录 (L422-424)
   lang_abbr = lang_abbr_map.get(lang_id)
               OR task.get('language', msg)  ← 双重 fallback (L423)
   g2p_dir = g2p_root_dir / lang_abbr / "g2p_models"
3. 目录不存在 (L426-429) ─→ 写 [warning] 日志，return True（不中断）
4. 探测编码 (L438-443)
   读 input.txt 前 2 字节：
   \xff\xfe 或 \xfe\xff → utf-16 + CRLF
   否则 → utf-8 + LF
5. 获取文件锁 (L449-451)
   锁文件：{g2p_dir}/.g2p_engine_exec.lock
   fcntl.LOCK_EX（阻塞直到获得）
6. 写 G2P 引擎输入 (L455-466)
   希伯来语 → generate_context_for_hebrew_oov(...)
   其他语言 → 直接把 OOV 列表写入 input.txt
7. 选 G2P 脚本 (L469-470)
   lang_abbr 或 lang_id 在 cloud_g2p_langs → run_cloud.sh
   否则 → run.sh
8. 执行 G2P 引擎 (L472)
   bash run.sh (在 g2p_dir 目录下)
9. copy 结果到私有目录 (L474-477)
   output.dict → {temp_path}/g2p_output_{msg}.dict
10. 释放锁 (L479)
```

**lang_abbr 三步回退**（L422–423）：
1. `lang_abbr_map[lang_id]`（如 `'26' -> 'En'`）
2. `task.get('language', msg)`（task 里的 `language` 字段）
3. `msg`（任务名本身，如 `'en_nav_v2'`）

---

### 3.10 Step 3：`step3_merge_dict` (L490–560)

**词典目录路径拼接（完整计算链）**（L510–519）：
```python
lang_id     = str(task.get('l', 0))                  # 从 task 取
lang_abbr   = lang_abbr_map.get(lang_id)             # 如 '26' → 'En'
is_yun_val  = str(task.get('is_yun', '0'))           # 如 '0'
res_dir_name = res_dir_map.get(is_yun_val, 'unknown') # 如 'ubctc_duan'
lang_name   = parsed_language_map.get(lang_id, '')   # 从 language_map 文件读，如 'En'

# 最终路径
target_res_dir = {asrmlg_exp_dir}/res/{lang_name}_res/{res_dir_name}
target_dict    = {target_res_dir}/new_dict
```

**phones.syms 查找顺序**（L521–526）：
1. `{target_res_dir}/phones.syms`
2. fallback → `{target_res_dir}/phones.list.noblank`
3. 都没有 → `load_valid_phones` 返回空 set，校验跳过（不报错）

**G2P 输出文件路径**（L528，⚠️ 见 Bug-2）：
```python
# 读的是共享文件，不是 step2 存的私有副本
g2p_output_dict = {g2p_root_dir}/{lang_abbr}/g2p_models/output.dict
```

**VCS 调用时序**（L532–558）：
```
pre_merge  → 当前词典创建快照
merge_dict → G2P 词典合并进 new_dict
post_merge → 记录统计日志（只有 merge_success=True 时执行）
                       └─ 传入 task.get('msg',''), lang_id, max_versions
```

**⚠️ Bug-3**：L560 `return True` 与 merge 结果无关（见第 2 节）。

---

### 3.11 Step 4：`step4_full_build` (L562–581)

- **清理临时目录**：L569 `shutil.rmtree(task_out_path + "_temp", ignore_errors=True)`。
- **`--output` 指向正式目录**（L573）：`base_cmd + ["--output", task_out_path]`（非 `_temp`）。
- **`--msg` 注入 patch_type**（L575–579）：
  - 若 `--msg` 已在命令中 → 原地把 `msg` 改为 `{msg}_{patch_type}`。
  - 若不存在 → 追加 `["--msg", "{msg}_{patch_type}"]`。
  - `patch_type` 来自 `model_type`（`scheme_map[is_yun]`）。

---

### 3.12 Step 5：`step5_whisper_package` (L620–694)

**`whisper_config` 子字段与默认值**（L636–643）：

| 字段 | 默认值（不设时） | 代码行 |
| :--- | :--- | :--- |
| `work_dir` | `{lang_name}_{msg}_patch_{YYYYMMDD}` | L636 |
| `name` | `{USER}_{msg}_{YYYYMMDD}`（`USER` 来自环境变量） | L637 |
| `patch_type` | `msg` | L638 |
| `patch_scale` | `'1.0'` | L639 |
| `train_dict` | 无（必须提供，否则 L645 `return False`） | L641 |
| `phoneset` | 无（必须提供） | L642 |
| `package_ed_target` | 无（必须提供） | L643 |

**完整工具执行链**（L672–690）：

```
工具 1：run_replace_dict.sh（bash 脚本，在 whisper_tools_dir 下运行）
  参数：train_dict  work_dir  lang_id
  产出：{work_dir}/aaa_dict_for_use.remake

工具 2：./package_ed（二进制，在 whisper_tools_dir 下运行）
  参数：aaa_dict_for_use.remake  phoneset  package_ed_target  work_dir
  产出：{work_dir}/edDictPhones.syms, {work_dir}/words.syms 等

工具 3：./wfst_serialize（二进制，在 wearlized/ 下运行）
  参数：task_{uuid8}.cfg（每次生成的临时配置文件）
  环境：LD_LIBRARY_PATH=./:原值
  产出：wearlized/output/{exact_bin_name}
```

**`generate_custom_cfg` 改写的 `.cfg` 字段**（L600–613）：

| cfg section | 字段 | 写入的值 |
| :--- | :--- | :--- |
| `[common]` | `lm_factor` | `patch_scale`（如 `"1.0"`） |
| `[input]` | `wfst_net_txt` | `{abs_work_dir}/output.wfst.mvrd.txt` |
| `[input]` | `edDcitSymsFile` | `{abs_work_dir}/edDictPhones.syms` |
| `[input]` | `phoneSymsFile` | `{abs_work_dir}/edDictPhones.syms` |
| `[input]` | `wordsSymsFile` | `{abs_work_dir}/words.syms` |
| `[input]` | `word2PhoneFile` | `{abs_work_dir}/aaa_dict_for_use.remake` |
| `[output]` | `OutWfst.bin` | `./output/{bin_output_name}`（相对 `wearlized/`） |

**`exact_bin_name` 命名格式**（L684）：
```
whisper_{patch_type}_{patch_scale}_{patch_name}_{uuid8}.bin
```
举例：`whisper_nav_1.0_tyliu23_en_nav_20260101_3f8ab12c.bin`

**⚠️ Bug-5**：`.bin` 实际写在 `wearlized/output/`，`final_whisper_out` 目录为空（见第 2 节）。

---

### 3.13 `run_phase1_pipeline` (L697–719)

**输出目录命名**（L709）：
```
{output_dir}/{lang_name}/{msg}/{model_type}_{YYYYMMDD}
```
- `lang_name` 来自 `parsed_language_map`，fallback 为 `lang_{lang_id}`（L705）。
- `model_type` 来自 `scheme_map[is_yun]`，无默认值，fallback 为 `'unknown'`（L706）。

**各步骤失败行为对比**（L713–717）：

| 步骤 | 控制开关 | 失败行为 | 代码行 |
| :--- | :--- | :--- | :--- |
| Step1 OOV 提取 | 无（强制） | `return False`，后续全中断 | L713 |
| Step2 G2P | `enable_g2p` | `return False`，后续全中断 | L714 |
| Step3 合并词典 | `enable_merge_dict` | **返回值被忽略**，永远继续 | L715 |
| Step4 全量打包 | 无（强制） | `return False`，后续全中断 | L716 |
| Step5 Whisper | `enable_whisper_package` | 直接返回 step5 的结果 | L717 |

**Step3 开关行为细节**（L715）：
```python
if task.get('enable_merge_dict'): step3_merge_dict(task, global_cfg, msg, log_file)
```
返回值完全被抛弃。即使 `enable_merge_dict=True` 且 merge 失败，Step4 仍会继续执行。

---

### 3.14 `execute_phase1` (L722–733) 与 `main` (L749–776)

**并发模型**：
```
main() 里的 ThreadPoolExecutor(max_workers=2)
  ├── Thread A: execute_phase1(tasks) → ProcessPoolExecutor(max_workers=4)
  │                                         ├── Process 1: run_phase1_pipeline(task[0])
  │                                         ├── Process 2: run_phase1_pipeline(task[1])
  │                                         ├── Process 3: run_phase1_pipeline(task[2])
  │                                         └── Process 4: run_phase1_pipeline(task[3])
  └── Thread B: execute_testset_phase(tasks) → pass（未实现）
```

**`main()` 启动序列**（L749–776）：
1. 解析参数 `-g global_config.yaml`（可选） `-j job.yaml`（必须）（L751–754）。
2. 读 YAML 文件（L759–760），`global_config` 不存在时用空 dict。
3. `resolve_and_bind_paths` 补全所有默认路径（L763）。
4. `load_language_map` 读语言映射文件（L767–768），存入 `global_cfg['parsed_language_map']`。
5. 启动 Phase1 + Phase2 并发（L771–774，Phase2 当前为 `pass`）。

---

## 4. `tools/merge_dict.py` — 词典合并工具

### 4.1 `load_valid_phones` (L16–31)

- 读取 `phones.syms` 或 `phones.list.noblank`，取**每行第一列**为合法音素（L29 `parts[0]`）。
- 文件不存在 → 返回空 set（L23–24），后续校验直接跳过，不报错。
- **设计意图**：空 set 意味着"不做校验"，而非"所有音素非法"。

### 4.2 `merge_dictionaries` (L33–97)

**完整流程（一次性内存操作）**：
1. 把现有 `base_dict` 全部读入内存（L43–52），同时构建 `existing_entries` set 用于 O(1) 去重。
2. 逐行读 `new_dict`，经过四道过滤（L60–91）。
3. 全部过滤完毕后，**一次性写回**到 `base_dict`（L93–95），`newline='\n'` 强制 Linux 换行。

**四道过滤详情**：

| 顺序 | 检查 | 失败处理 | 计数器 | 代码行 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `split('\t')` 结果必须是 2 段（一个 tab） | `continue`，不报错 | `skip_format` | L67–69 |
| 2 | `word\tphones_str` 完全一致的条目已存在 | `continue`，不报错 | `skip_duplicate` | L75–77 |
| 3 | `phones_str.split(' ')` 每个音素必须在 `valid_phones` 里（若 valid_phones 为空则跳过此检查） | `continue`，打 `[REJECTED]` 到 **stderr** | `skip_abnormal_phone` | L79–86 |
| 4 | 通过所有检查 | 追加到 `base_lines` 和 `existing_entries` | `added_count` | L88–91 |

**统计输出**（L97，打到 stdout）：
```
Merge Results: Added=N, Dups=M, FormatErr=K, IllegalPhone=J
```

**注意**：`[REJECTED]` 打到 `stderr`，在 `run_subprocess` 的 log 文件中可以看到（因为 L82 `stderr=subprocess.STDOUT` 合并了两个流）。

---

## 5. `tools/lexicon_vcs.py` — 词典版本控制

### 5.1 目录结构与文件命名

```
{new_dict 所在目录}/
├── new_dict                                   ← 当前词典（被管理的目标文件）
└── .history/
    ├── history.log                            ← 所有操作历史记录
    ├── new_dict.v20260101_120000.abc1234.bak  ← 快照文件
    └── new_dict.v20260102_090000.def5678.bak
```

- `.history/` 在同级目录，`__init__`（L31）自动创建。
- hash 取**前 7 位**（L45）：`hexdigest()[:7]`（与 `get_file_md5_suffix` 的末尾 4 位不同）。
- 备份文件名格式（L74–77）：`{dict_name}.v{YYYYMMDD_HHMMSS}.{hash7}.bak`。

### 5.2 `pre_merge` (L65–81)

- 若 `new_dict` 不存在 → 先创建空文件（L72 `open(..., 'w').close()`），再备份。
- 备份用 `shutil.copy2`（L79），保留原始时间戳。

### 5.3 `post_merge` (L83–118)

**词汇差异统计**（L93–99）：
- 调用 `_load_vocab` 读取**第一列**（按空格分列）作为词汇集合（L53–63）。
- `added_words = new_vocab - old_vocab`（set 差集），只比较词，不比较发音。

**`history.log` 每行格式**（L105–109）：
```
[YYYYMMDD_HHMMSS] TASK: {msg} | LANG: {lang_id} | HASH: {hash7} | TOTAL_WORDS: N | ADDED_WORDS: M
```

**`_prune` 规则**（L120–143）：
- 保留最新 `max_versions` 个 `.bak` 文件，删除最老的（L129–131）。
- `history.log` 保留最后 `max_versions * 2` 行（L138）。

### 5.4 `rollback` (L156–184)

**完整流程**：
1. glob 匹配 `{dict_name}.v*.{target_hash}.bak`（L161），精确匹配 hash 值。
2. 若有多个匹配 → 哈希碰撞，报错退出（L168–170）。
3. **先 `pre_merge()` 备份当前（被破坏的）状态**（L175），防止误回滚无法挽救。
4. `shutil.copy2(backup, dict_path)`（L177），覆盖当前文件。
5. 在 `history.log` 追加 `[ts] ROLLBACK | Restored to Hash: {hash}`（L182–183）。

**CLI 用法**：
```bash
# 查看历史
python tools/lexicon_vcs.py -i res/En_res/ubctc_duan/new_dict log

# 回滚到 hash=abc1234 的版本
python tools/lexicon_vcs.py -i res/En_res/ubctc_duan/new_dict rollback -t abc1234
```

---

## 6. `tools/make_test_set.py` — 测试集生成器

### 6.1 启动时环境注入（L27–44，模块级代码）

```
脚本启动
  ↓
提前解析 -e/--engine_dir（L27–29，使用 add_help=False 的 pre-parser）
  ↓
ENGINE_DIR = Path(engine_dir).resolve()       # L31
PYTHON_LIB_PATH = ENGINE_DIR / "python_lib"  # L32
  ↓
检查 python_lib 存在（L34–36），不存在 → sys.exit(1)
  ↓
sys.path.insert(0, ENGINE_DIR)               # L39
sys.path.insert(0, PYTHON_LIB_PATH)          # L41
  ↓
from corpus_process import *                  # L44
  （num2LagDict, need_split, ttsdict, get_corpus_process 等）
```

- `-e/--engine_dir` 是**必须参数**，脚本无法无此参数运行。
- `python_lib` 路径不存在即退出，无法 fallback。

### 6.2 `generate_mlf` (L46–68)

**输入格式**：`wave_name\ttranscript`（tab 分隔）。

**输出 HTK MLF 格式**（L51–68）：
```
#!MLF!#
"*/audio_001.lab"
<s>
navigate
to
new
york
</s>
.
```
- 标签路径用 `*/stem.lab` 通配符格式（L62）。
- `<s>`/`</s>` 是 HTK 标准的句子边界标记。

### 6.3 `process_text_corpus` (L70–111)

对测试文本做两步处理，使其与训练时的格式对齐：

**步骤 1：子词切分**（L77–93，仅对 `need_split` 语言执行）
- 判断条件：`num2LagDict[language] in need_split`（如泰语、日语需要切分）。
- 处理：调用 `corpus_process.get_split_function().split(...)` 切分词汇。
- 中间文件：`{txt}_before_split`（备份）、`{txt}_split_oov`（切分 OOV 记录）。

**步骤 2：字符过滤**（L96–110，所有语言都执行）
- 调用 `corpus_proc_inst.filter_corpus_by_char(lab_line, outfile, oov_file, ispost)`。
- 过滤掉不在词典中的字符。
- `ispost` 参数由命令行 `--post` 控制（`L217`），区分是否是 post-normalization 格式。
- 中间文件：`{txt}_before_filter`（备份）、`{txt}_filter_oov`（过滤 OOV 记录）。

### 6.4 `run_tts_generation` (L113–181)

**并发保护与隔离机制**（完整流程）：
```
1. 生成 6 位 UUID 作为任务 ID (L124)
2. 设置私有目录 wavs_{uuid6}，准备接收 wav (L125)
3. 设置环境变量 (L128-131)
   TTSKNL_DOMAIN = {tts_base_dir}
   LD_LIBRARY_PATH = {tts_base_dir}:{原值}（前置追加）
   OMP_NUM_THREADS = 1（限制线程，避免 TTS 并发崩溃）
4. 打开锁文件并申请 fcntl.LOCK_EX（L146-147，阻塞等待）
   ── 以下在锁内执行 ──
5. 清理共享输出目录 (L151-154)
   删除 frontinfo.txt（上次残留的前端信息）
   删除并重建 wav_outdir/（清空上次音频）
6. 运行 TTS 引擎 ./ttsSample (L157-158)
   -l libttsknl.so -v {lang_param} -x 1 -i {input_txt}
   -o wav_outdir/ -m 1 -f 1 -g 1
7. 把 wav_outdir/ 完整 copy 到 wavs_{uuid6}/ (L161-162)
   ── 锁内 copy 完毕才释放锁，防止被下一个任务的清理操作删除 ──
8. 释放锁 (L167，finally 块)
   ── 锁外 ──
9. 按顺序匹配 wav 文件名与标注文本 (L172-179)
   wav_files = sorted(wavs_{uuid6}/)  ← 按文件名字母序
   逐行匹配 label_source 的行
```

**TTS 失败处理**（L164–165）：`subprocess.CalledProcessError` → 打日志 + `sys.exit(1)`，不重试。

**label_txt 参数的作用**（L172–179）：
- 若传了 `label_txt`（TTS 模式下传 `filter_txt`） → 用 `filter_txt` 的行作标注（原始文本）。
- 若没传 → 用 `input_abs_path`（synthesize_txt）的行作标注（可能含发音修正）。
- 这样确保 MLF 标注是原始文本，而不是发音修正后的文本。

### 6.5 发音修正替换表（`--replacement_list`）（L234–248）

**文件格式**：每行 `原词 : 替换词`，冒号两侧有空格（L237–238）。

**处理逻辑**（L240–248）：
```python
for line in open(replacement_list):
    parts = line.strip().split(':', 1)
    if len(parts) == 2:
        replacements[parts[0].strip().upper()] = parts[1].strip()
# 应用替换（L246）：
replaced_line = " ".join([replacements.get(w.upper(), w) for w in line.split()])
```

- key 存储为大写（`parts[0].strip().upper()`）。
- 查找时也用大写（`w.upper()`），因此**不区分大小写**。
- 替换后的文本写入 `synthesize_txt`（用于 TTS）；原始文本写入 `filter_txt`（用于 MLF 标注）。

### 6.6 `build_testset_package` (L183–208)

**文件组织（ZIP 内结构）**：
```
{output_dir_name}.zip
└── {output_dir_name}/
    ├── {output_dir_name}.mlf    ← HTK 标注文件
    ├── audio_001.wav
    ├── audio_002.wav
    └── ...
```

- ZIP 根目录名为 `output_dir` 的 basename（L201, L204）。
- 只有 `input_wav_dir` 存在时才打包（L198），否则只生成 `.mlf`。

---

## 7. `tools/excel_to_txt_sampler.py` — 语料采样器

### 7.1 `parse_excel` (L32–77)

**Sheet 识别（三档互斥）**：

| 档位 | 触发条件 | 存储位置 | 数据类型 | 代码行 |
| :--- | :--- | :--- | :--- | :--- |
| sent | `'sent' in sheet.lower()` | `self.sent_list` | 扁平化所有单元格，无 header | L48–51 |
| shuofa | `'shuofa' in sheet.lower()` | `self.templates` | 扁平化所有单元格，无 header | L54–57 |
| slot | `'<>' in sheet`（含 `<>` 字样） | `self.slot_dict[列名]` | 有 header，按列名存（`<city>` 等） | L60–67 |
| fallback | 上面都无 | `self.sent_list`（设 `is_standard_corpus=True`） | sheet[0] 的 `text` 列或第一列 | L70–77 |

**fallback 列选逻辑**（L72–76）：
```python
if 'text' in df.columns:
    raw_sents = df['text'].dropna().astype(str).str.strip().tolist()
else:
    raw_sents = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
```

### 7.2 `_expand_template` (L79–101)

**递归展开流程**：
```
while 模板中还有 <...> 且 depth < 20:
  regex 找第一个 <slot_name>
  ├─ slot_name 在 slot_dict 且有值
  │    → random.choice(slot_dict[slot_name]) 替换
  └─ slot_name 不在 slot_dict 或为空
       → break（保留未展开的 <slot_name>）
  depth += 1
```

**含未展开槽位的结果会被丢弃**（`generate_testset:L132`）：
```python
if '<' not in generated:
    final_set.add(generated)
```
所以 slot 不在 dict 里时，该模板的这次展开不会出现在最终输出中。

### 7.3 `generate_testset` (L103–142)

**三条执行路径**：

| 路径 | 触发条件 | 行为 | 代码行 |
| :--- | :--- | :--- | :--- |
| A：纯静态 | `is_standard_corpus` 或 `templates` 为空 | sent_list 去重后，超出则 random.sample，否则全返回 | L111–115 |
| B：静态已够 | `len(sent_list) >= target_count` | 直接 `random.sample(sent_list, target_count)` | L118–119 |
| C：模板扩充 | 默认路径（两者都不够） | 先放入全部 sent_list，循环展开 templates 补足 | L121–141 |

**路径 C 的退出条件**（L129）：
```python
while len(final_set) < target_count and attempts < max_attempts and self.templates:
```
- 达到 `target_count` → 停止。
- 超过 `needed * 15` 次尝试 → 停止（L127）。
- `self.templates` 为空 → 停止。

最终结果 `random.shuffle`（L141），顺序随机。

---

## 8. `tools/pipeline_warmup.py` — 流水线热身

### 8.1 与 `DeltaTracker.get_semantic_hash` 的关系

`pipeline_warmup.py:L20` 和 `pipeline_executor.py:L181` 的 `get_semantic_hash` 逻辑**完全相同**，但是两个独立的函数副本，**不共享代码**。

若修改 Sheet 识别逻辑，**必须同时修改两处**，否则 warmup 生成的 hash 与运行时计算的 hash 不一致，导致：
- warmup 认为文件已处理（hash 相同）。
- 运行时重新计算 hash 不同，触发全量重建。
- 或反之，warmup 认为需重建，运行时认为跳过。

### 8.2 `warmup_manifest` (L74–117)

**key 冲突问题**（L98，详见第 2 节设计限制-1）：
```python
file_key = file   # 只用文件名，不用路径
```
不同子目录下的同名文件会覆盖 manifest key。

**增量 warmup**（L101–110）：已在 manifest 中且 hash 相同的文件会被跳过（`skip_count`）。

**`processed_time` 格式**（L106）：`WARMUP_YYYYMMDD_HHMMSS`，可与 pipeline 正常运行（`YYYYMMDD_HHMMSS` 格式）区分。

---

## 9. 完整数据流图

```
job.yaml + global_config.yaml
         │
         ▼
       main()
    ┌──────────────────────────────────────────────────────────────┐
    │  ThreadPool: Phase1 和 Phase2 并发（实际上 Phase2 是 pass）    │
    └──────────────────────────────────────────────────────────────┘
         │
         ▼ Phase1
execute_phase1()
    ProcessPool (max 4 并发)
         │
         ▼ 每个 task
run_phase1_pipeline(task)
         │
    ┌────┴──────────────────────────────────────────────┐
    │  输出目录: output/{lang_name}/{msg}/{model_type}_{date}  │
    └─────────────────────────────────────────────────────┘
         │
Step1: corpus_process_package.py --only_corpus_process
         │ 产出：{dir}_temp/custom_corpus_process/dict_dir/aaa_oov_base_dict
         ↓
Step2: G2P（若 enable_g2p）
         │ 读：aaa_oov_base_dict
         │ 写：g2p/En/g2p_models/input.txt（持锁内）
         │ 执行：g2p/En/g2p_models/run.sh
         │ 读：g2p/En/g2p_models/output.dict
         │ copy：{dir}_temp/g2p_output_{msg}.dict（私有副本）
         ↓
Step3: merge_dict.py（若 enable_merge_dict）
         │ 读：g2p/En/g2p_models/output.dict（⚠️ 共享文件，非私有副本）
         │ VCS pre_merge → 备份 res/En_res/ubctc_duan/new_dict
         │ 合并 → res/En_res/ubctc_duan/new_dict（原地修改）
         │ VCS post_merge → 记录 .history/history.log
         ↓
Step4: corpus_process_package.py（全量打包）
         │ 读：已更新的 res/En_res/ubctc_duan/new_dict
         │ 产出：{dir}/ 下的 .bin 产物（含 MD5 后缀）
         ↓
Step5: Whisper 序列化（若 enable_whisper_package && is_yun==3）
         │ 读：Step4 产出的三个关键文件
         │ run_replace_dict.sh → aaa_dict_for_use.remake
         │ ./package_ed → edDictPhones.syms 等
         │ ./wfst_serialize → wearlized/output/{bin_name}
         │ ⚠️ final_whisper_out 目录创建但未填充（Bug-5）
         ↓
    完成
```

---

## 10. 常见排查路径速查

### `.bin` 文件没生成

1. 查 `output/logs/build.log`，找 `for {msg}` 的时间段。
2. 搜 `[fatal error]` 或 `returncode`。
3. Step4 是主嫌：找 `STARTING: phase1_step4` 之后的报错。
4. 若 `aaa_oov_base_dict` 找不到 → Step1 失败，先查语料路径。

### G2P 没跑，OOV 词无发音

1. 确认 `enable_g2p: true`（`L714`）。
2. 检查 `aaa_oov_base_dict` 是否存在且非空（`L419`）。
3. 检查 `g2p_root_dir/{lang_abbr}/g2p_models/` 是否存在（`L424`）。
4. `lang_abbr` 怎么来的：`lang_abbr_map[lang_id]` → `task.get('language')` → `msg`（`L423`）。
5. 若 G2P 目录不存在 → 只写 warning，不报错（`L426–429`），继续执行。

### 词典合并后打包出来模型性能变差

1. 查 `build.log` 搜 `[REJECTED]` → 是否有大量音素被拒。
2. 检查 `phones.syms` 路径是否指向了正确的语言模型资源（`L521–526`）。
3. 执行手动回滚：
   ```bash
   python tools/lexicon_vcs.py -i res/En_res/ubctc_duan/new_dict log
   python tools/lexicon_vcs.py -i res/En_res/ubctc_duan/new_dict rollback -t {hash7}
   ```

### 多任务并行时 G2P 结果互相污染

1. 查 `build.log` 看 `WAITING LOCK`/`ACQUIRED LOCK`/`RELEASED LOCK` 序列是否正常。
2. 检查锁文件 `{g2p_dir}/.g2p_engine_exec.lock` 是否残留（进程异常退出可能留下锁）。
3. 长期存在的残留锁文件需手动删除。
4. 注意 Bug-2：即使 G2P 本身不污染，Step3 仍然读共享文件，多语言同时 merge 仍有风险。

### Excel 改了但增量没触发重建

1. 手动删除 `output/test_sets/*_manifest.json`，强制全量。
2. 检查两处 `get_semantic_hash` 实现是否同步（`L181` vs `warmup.py:L20`）。
3. 确认修改的是 `sent`/`shuofa`/`<>` 类型的 sheet（只有这些才纳入哈希）。

### Whisper 产物 `.bin` 找不到

1. ⚠️ Bug-5：`.bin` 不在 `final_whisper_out` 里，在 `{whisper_tools_dir}/wearlized/output/` 下找。
2. 检查 `generate_custom_cfg`（`L612`）写入的 `OutWfst.bin` 路径是否以 `./output/` 开头。

### 希伯来语 G2P 报 `NameError: re`

- ⚠️ Bug-1：在 `pipeline_executor.py` 顶部添加 `import re`（第 20 行附近）。

### Phase 2 测试集生成没有效果

- ⚠️ Bug-6：`execute_testset_phase` 是 `pass`，需要实现该函数才能让 `enable_testset: true` 生效。

---

**维护者**：tyliu23  
**状态**：开发者手册 V3.0，全量源码精讲 + Bug 清单。
