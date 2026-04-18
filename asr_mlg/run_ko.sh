
# 使用示例：
# python corpus_process_package.py \
# -l                        语种
# --norm_train_ctc          通用语料是否训练CTC 不配置 默认false
# --norm_cut                通用语料训练裁剪参数可以输入7e5 默认不裁剪
# --custom_train_ctc        定制语料是否训练CTC 默认false
# --custom_cut              定制语料训练裁剪参数 默认不裁剪
# -G                        打包G网络方式训练patch 不配默认训练ngram
# --ismerge                 训练合并，通用语料和定制语料训练打包后的文本wfst 进行合并。训练主wfst需要
# --word_syms               word.syms 不配：res/language_res/（yun/duan）/*  配置时使用配置的资源
# --phone_syms              phone_syms 不配：res/language_res/（yun/duan）/*  配置时使用配置的资源
# --triphone_syms           triphone_syms 不配：res/language_res/（yun/duan）/*  配置时使用配置的资源
# --dict                    dict 不配：res/language_res/（yun/duan）/*  配置时使用配置的资源
# --hmm_list                hmm_list 不配：res/language_res/（yun/duan）/*  配置时使用配置的资源
# --hmm_list_blank          hmm_list_blank 不配：res/language_res/（yun/duan）/*  配置时使用配置的资源
# --mapping                 mapping 不配：res/language_res/（yun/duan）/*  配置时使用配置的资源
# --msg                     打包输出的二进制文件名前缀 不配默认projectname
# --output                  输出文件夹 不配默认output
# --norm_excel_corpus_path  通用语料excel 格式输入 不配默认为None 没有可以不配
# --norm_train_data_slot    通用语料槽内容所在文件夹 不配默认为None 没有可以不配
# --norm_train_data_shuofa  通用语料说法内容所在文件夹 不配默认为None 没有可以不配
# -np                       通用语料句子所在文件夹 不配默认为None 没有可以不配
# --excel_corpus_path       定制语料excel 格式输入 不配默认为None 没有可以不配
# --train_data_slot         定制语料槽内容所在文件夹 不配默认为None 没有可以不配
# --train_data_shuofa       定制语料说法内容所在文件夹 不配默认为None 没有可以不配
# -cp                       定制语料句子所在文件夹 不配默认为None 没有可以不配
# --expand_argument         说法+槽扩展 参数 exp: poi-20,city-100
# --dict_max                打包词典最大个数 
# --predict_phone_for_new   为新词语测发音 不配默认为false  
# --use_old_phone_system    使用映射工具将新音素体系映射回老的音素体系,会造成识别效果问题
# --only_corpus_process     只处理语料不打包 不配置默认为false
# --is_yun                  控制不同版本语言模型或patch 打包

# package_map = {
#         0:"ubctc_duan",
#         1:"rnnt_ctc_duan",
#         2:"rnnt_ed_duan",
#         3:"yun",
# }


# 使用文本语料作为输入打包patch：
/home3/asrdictt/kezhao/anaconda3/envs/temp3.7/bin/python corpus_process_package.py \
-l 26 `#语种`\
-G 1-6 \
--excel_corpus_path /yrfs4/asrdictt/tyliu23/patch_demo/project_corpus/car/korean `#定制语料所在文件夹`\
--msg requirement_0918_mode `#模型message`\
--output arabic_test `#output 目录` \
--is_yun 0

# # 使用excel预料作为输入打包patch：
# /home3/asrdictt/kezhao/anaconda3/envs/temp3.7/bin/python corpus_process_package.py \
# -l 5 `#语种`\
# -G 1-6 \
# --excel_corpus_path project_corpus/car/english/local/dayun/ `#定制语料所在文件夹`\
# --msg requirement_0918_mode `#模型message`\
# --output arabic_test `#output 目录` \
# --is_yun 1


# # 使用文本语料作为输入打包ngram 的语言模型：
# /home3/asrdictt/kezhao/anaconda3/envs/temp3.7/bin/python corpus_process_package.py \
# -l 5 `#语种`\
# --train_data_shuofa /raw7/asrdictt/kezhao/asrmlg_edgen_hw/shuofa `#定制语料所在文件夹`\
# --msg requirement_0918_mode `#模型message`\
# --output arabic_test `#output 目录` \
# --is_yun 1


# # 使用excel语料作为输入打包ngram 的语言模型：
# /home3/asrdictt/kezhao/anaconda3/envs/temp3.7/bin/python corpus_process_package.py \
# -l 0 `#语种`\
# --norm_excel_corpus_path project_corpus/car/english/local/dayun/ `#定制语料所在文件夹`\
# --msg requirement_0918_mode `#模型message`\
# --output ebglish_test `#output 目录` \
# --is_yun 0