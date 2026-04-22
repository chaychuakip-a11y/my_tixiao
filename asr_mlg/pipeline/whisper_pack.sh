#!/bin/bash

# --- 1. 参数配置 ---
# 建议：如果是生产环境，这些可以用 $1, $2 等外部参数传入
hybridCNN_Gpatch='/b3-mix05/sli/temporary/wwgong3/asrmlg_edgen_hw/yun_es_patch_0331'
work_dir='es_gongban_patch_spanish_20260417_test'
lan_id='69520'
train_dict='/work2/asrdictt/wwgong3/asrmlg_edgen_hw/bin_spanish/res/sp_es_linux_all.dict'
phoneset='/work2/asrdictt/wwgong3/asrmlg_edgen_hw/bin_spanish/res/phones.es.linux'
patch_scale='1.0'
name='wwgong3_20260417'
patch_type='gongban'

# --- 2. 环境准备 ---
mkdir -p ${work_dir}
cp ${hybridCNN_Gpatch}/custom_G_pak/G ${work_dir}
cp ${hybridCNN_Gpatch}/custom_G_pak/GeneratedG.DONE ${work_dir}
cp ${hybridCNN_Gpatch}/custom_corpus_process/dict_dir/aaa_dict_for_use ${work_dir}

# --- 3. 字典替换与模型处理 ---
bash run_replace_dict.sh ${train_dict} ${work_dir} ${lan_id}

# 此处 LM 路径保留你原始脚本中的俄语路径（请根据实际需求确认是否需要更换）
./package_ed ${work_dir}/aaa_dict_for_use.remake ${phoneset} \
    /train8/asrmlg/ddye2/asr/russian/russian_gongban_forpatch_cloud_20240918_5_train_lm/output_model_240927/chazhi/lm.chazhi_norm035_poi015_music015_weather015_cz_02.3gram \
    ${work_dir}

# --- 4. 动态生成 CFG (基于图片模板) ---
python3 - <<EOF
import sys

# 从 Bash 注入变量
work_dir = "${work_dir}"
lm_scale = "${patch_scale}"
lan_id = "${lan_id}"
name = "${name}"
patch_type = "${patch_type}"

# 读取语言映射表
lan_message = {}
try:
    with open('lans.txt', 'r') as f:
        for line in f:
            parts = line.strip().split(' ')
            if len(parts) >= 3:
                lan_message[parts[0]] = [parts[1], parts[2]] # {id: [full_name, short_name]}
except Exception as e:
    print(f"Error loading lans.txt: {e}")
    sys.exit(1)

lang_full = lan_message[lan_id][0]
lang_short = lan_message[lan_id][1]

# 处理 patch_type 命名逻辑 (gongban -> yun_es)
actual_patch_str = "yun_es" if patch_type == "gongban" else patch_type

# 构建配置内容
cfg_content = f"""[common]
business=
lm_factor= {lm_scale}
penalty_factor= 5
lang_name= {lang_full}
pack_name= car

[WFST]
net_type= 5

class_type= pername

[input]
wfst_net_txt=../{work_dir}/output.wfst.mvrd.txt
edDcitSymsFile=../{work_dir}/edDictPhones.syms
phoneSymsFile=../{work_dir}/edDictPhones.syms
wordsSymsFile=../{work_dir}/words.syms
word2PhoneFile=../{work_dir}/aaa_dict_for_use.remake

[input_option]
mappingFile=
stateSymsFile=
pinyinSymsFile=
PYDictFile=
UpCaseConvertFile=
phoneDistanceFile=

[output]
OutWfst.bin=./output/{lang_short}_{actual_patch_str}_whisper_44phones_patch{lm_scale}_{name}.bin
"""

# 写入配置文件
with open('wfst_serialize_large.241227_patch.cfg', 'w') as f:
    f.write(cfg_content)
EOF

# --- 5. 执行序列化与打包 ---
export LD_LIBRARY_PATH=./
./wfst_serialize wfst_serialize_large.241227_patch.cfg

# 加载环境并计算 MD5
source /raw22/asrdictt/permanent/wwyang9/car_asr/V2_model_work/cloud_asr/whipser/whisper_tune_upenc/hulk_bak.bashrc

out_dir='md5_output'
mkdir -p ${out_dir}

# 根据类型匹配输出文件并生成 MD5
if [ "${patch_type}" = "gongban" ]; then
    python3 filename_add_md5sum.py output/*yun_es*${patch_scale}*${name}.bin ${out_dir}
else
    python3 filename_add_md5sum.py output/*${patch_type}*${patch_scale}*${name}.bin ${out_dir}
fi

echo "Done. Results in ${out_dir}"