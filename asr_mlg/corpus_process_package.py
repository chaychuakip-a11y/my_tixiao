#coding=utf-8
import sys
sys.path.insert(0, "./python_lib")
import argparse
import os
import datetime
import shutil
from corpus_process import *
from net_maker import *

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass
 
    try:
        import unicodedata
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass
 
    return False


package_map = {
        0:"ubctc_duan",
        1:"rnnt_ctc_duan",
        2:"rnnt_ed_duan",
        3:"yun",
}

class Package:
    
    def __init__(self,language, norm_train_ctc,norm_cut,custom_train_ctc,custom_cut,ismerge,outputdir,voca_dict,hmmlist,hmmlistblank,mapping,word_syms,phone_syms,triphone_syms,is_yun,G_argument,expand_argument):
        self.language = language

        self.norm_path = None
        self.norm_train_ctc = norm_train_ctc
        self.norm_cut = norm_cut

        self.custom_path = None
        self.custom_train_ctc = custom_train_ctc
        self.custom_cut = custom_cut

        self.dict = voca_dict
        self.hmm_list = hmmlist
        self.hmm_list_blank = hmmlistblank
        self.mapping = mapping
        self.word_syms = word_syms
        self.phone_syms = phone_syms
        self.triphone_syms = triphone_syms
         
        self.ismerge = ismerge
        self.outputdir = outputdir

        self.out_main_wfst_path = None
        self.out_main_sub_path = None
        self.is_yun = is_yun
        self.G_argument = G_argument
        self.slot_path = None

        self.slot_argument ={}
        if expand_argument is not None:
            templist = expand_argument.split(',')
            for elem in templist:
                self.slot_argument[elem.split('-')[0]] = int(elem.split('-')[1])
        
        self.allslot={}
    
    def set_custom_corpus(self,custom_path):
        self.custom_path = custom_path

    def set_norm_corpus(self,norm_path):
        self.norm_path = norm_path
    
    def set_dict(self,voca_dict):
        self.dict = voca_dict
    
    def set_slot_path(self,slot_path):
        
        self.slot_path = slot_path
        print(self.slot_path)
        
    
    def getallslot(self):
        if self.slot_path is None:
            return
        for root ,dirs,files in os.walk(self.slot_path):
            for file in files:
                encoding='utf-8'
                # with open(os.path.join(root,file),'rb') as checkcode:
                #     encoding = chardet.detect(checkcode.read())['encoding']
                f = io.open(os.path.join(root,file), mode='r',encoding=encoding) if sys.version_info[0]==2 else open(os.path.join(root,file), mode='r',encoding=encoding)
                self.allslot[file] = set(f.read().splitlines())
                if " " in self.allslot[file]:
                    self.allslot[file].remove(" ")
                if "" in self.allslot[file]:
                    self.allslot[file].remove("")
                f.close()
    
    def pack_ngram(self):

        if self.dict is None:
            self.dict = "./res/%s_res/%s/new_dict" % (num2LagDict[self.language],package_map[self.is_yun])
        if self.hmm_list is None:
            self.hmm_list = "./res/%s_res/%s/hmmlist_nosp.final" % (num2LagDict[self.language],package_map[self.is_yun])
        if self.hmm_list_blank is None:
            self.hmm_list_blank = "./res/%s_res/%s/hmmlist_nosp_blank.final" % (num2LagDict[self.language],package_map[self.is_yun])
        

        if self.G_argument:
            out_sub_path = os.path.join(self.outputdir,'custom_G_pak')
            self.generate_G_pak(self.custom_path, out_sub_path)
            return
            
        out_main_path = os.path.join(self.outputdir,'norm_3gram')
        os.makedirs(out_main_path)
        self.train_ngram_pak(self.norm_path, os.path.join(out_main_path,'lm_norm_3gram'), self.norm_train_ctc, self.norm_cut)

        out_sub_path = os.path.join(self.outputdir,'custom_3gram')
        os.makedirs(out_sub_path)
        self.train_ngram_pak(self.custom_path, os.path.join(out_sub_path,'lm_custom_3gram'), self.custom_train_ctc, self.custom_cut)

        
    def serial(self,msg):
        if self.is_yun ==1 or self.is_yun ==2 :
            self.serial_rnnt(msg)
        else:
            self.serial_ubctc_yun(msg)

    def serial_rnnt(self,msg):

        if self.dict is None:
            self.dict = "./res/%s_res/%s/new_dict" % (num2LagDict[self.language],package_map[self.is_yun])
        if self.word_syms is None:
            self.word_syms = (os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram_%s'%self.custom_cut) if self.custom_cut else os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram')) +'_ce_pak/words.syms'
        if self.phone_syms is None:
            self.phone_syms = (os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram_%s'%self.custom_cut) if self.custom_cut else os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram')) +'_ce_pak/edDictPhones.syms'


        # change serialization cfg
        self.out_main_wfst_path = (os.path.join(self.outputdir,'norm_3gram','lm_norm_3gram_%s'%self.norm_cut) if self.norm_cut else os.path.join(self.outputdir,'norm_3gram','lm_norm_3gram')) +'_ce_pak/output.wfst.mvrd.txt'
        self.out_main_sub_path = (os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram_%s'%self.custom_cut) if self.custom_cut else os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram')) +'_ce_pak/output.wfst.mvrd.txt'


        serial_base_path = "pack_wfst_rnnt.cfg"
        serial_path = os.path.join(self.outputdir,"pack_wfst_"+num2LagDict[self.language]+".cfg")
        shutil.copy2(serial_base_path,serial_path)
        print(serial_path)

        if self.G_argument:
            self.word_syms = os.path.join(self.outputdir,'custom_G_pak',"words.syms")
            self.out_main_sub_path = os.path.join(self.outputdir,'custom_G_pak',"output.wfst.mvrd.txt")
            self.phone_syms = os.path.join(self.outputdir,'custom_G_pak',"edDictPhones.syms")


        
        
        changeConfig(serial_path,"wordsSymsFile",os.path.abspath(self.word_syms),sectionName="input")
        changeConfig(serial_path,"edDictSymsFile",os.path.abspath(self.phone_syms),sectionName="input")

        changeConfig(serial_path,"wordsym_subdict",os.path.abspath(self.dict),sectionName="input")
        changeConfig(serial_path,"OutWfst.bin",os.path.abspath(os.path.join(self.outputdir,'wfst.bin')),sectionName="output")

        if self.ismerge and not self.G_argument:
            self.merge(msg)
        else:
            self.not_merge(msg)

    
    def serial_ubctc_yun(self,msg):

        if self.dict is None:
            self.dict = "./res/%s_res/%s/new_dict" % (num2LagDict[args.language],package_map[self.is_yun])
        if self.mapping is None:
            self.mapping = "./res/%s_res/%s/mapping.txt" % (num2LagDict[args.language],package_map[self.is_yun])
        if self.word_syms is None:
            self.word_syms = (os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram_%s'%self.custom_cut) if self.custom_cut else os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram')) +'_ce_pak/words.syms'
        if self.phone_syms is None:
            self.phone_syms = "./res/%s_res/%s/phones.syms" % (num2LagDict[args.language],package_map[self.is_yun])
        if self.triphone_syms is None:
            self.triphone_syms = "./res/%s_res/%s/triphones.syms" % (num2LagDict[args.language],package_map[self.is_yun])

        # change serialization cfg
        self.out_main_wfst_path = (os.path.join(self.outputdir,'norm_3gram','lm_norm_3gram_%s'%self.norm_cut) if self.norm_cut else os.path.join(self.outputdir,'norm_3gram','lm_norm_3gram')) +'_ce_pak/output.wfst.mvrd.txt'
        self.out_main_sub_path = (os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram_%s'%self.custom_cut) if self.custom_cut else os.path.join(self.outputdir,'custom_3gram','lm_custom_3gram')) +'_ce_pak/output.wfst.mvrd.txt'

        if self.is_yun:
            serial_base_path = "pack_wfst_yun.cfg"
        else:
            serial_base_path = "pack_wfst_duan.cfg"
        serial_path = os.path.join(self.outputdir,"pack_wfst_"+num2LagDict[self.language]+".cfg")
        shutil.copy2(serial_base_path,serial_path)
        print(serial_path)

        if self.G_argument:
            self.word_syms = os.path.join(self.outputdir,'custom_G_pak',"words.syms")
            self.out_main_sub_path = os.path.join(self.outputdir,'custom_G_pak',"output.wfst.mvrd.txt")
        if self.is_yun:
            changeConfig(serial_path,"mappingFile",os.path.abspath(self.mapping),sectionName="input_option")
            changeConfig(serial_path,"phoneSymsFile",os.path.abspath(self.phone_syms),sectionName="input")
        else:
            changeConfig(serial_path,"mappingFile",os.path.abspath(self.mapping),sectionName="input")
            changeConfig(serial_path,"phonesymsFile",os.path.abspath(self.phone_syms),sectionName="input")
        
        changeConfig(serial_path,"wordsSymsFile",os.path.abspath(self.word_syms),sectionName="input")
        changeConfig(serial_path,"triphoneSymsFile",os.path.abspath(self.triphone_syms),sectionName="input")
        changeConfig(serial_path,"word2PhoneFile",os.path.abspath(self.dict),sectionName="input")
        if self.language == 0:
            changeConfig(serial_path,"language_type",'0',sectionName="common")
            changeConfig(serial_path,"hmmlistFile",os.path.abspath(self.hmm_list_blank),sectionName="input")
        changeConfig(serial_path,"OutWfst.bin",os.path.abspath(os.path.join(self.outputdir,'wfst.bin')),sectionName="output")

        if self.ismerge and not self.G_argument:
            self.merge(msg)
        else:
            self.not_merge(msg)
    
    def merge(self, msg):
        out_merge_path = os.path.join(self.outputdir,'MERGE_model')
        os.makedirs(out_merge_path)
        if os.path.exists(self.out_main_wfst_path) and os.path.exists(self.out_main_sub_path):
            base_maxnode, base_endnode = findmaxnode(self.out_main_wfst_path)
            kunei_maxnode, kunei_endnode = findmaxnode(self.out_main_sub_path)
            modify_nodes(self.out_main_sub_path,os.path.join(out_merge_path,'output.wfst.mvrd.sub_modified.txt'),base_maxnode,base_endnode,kunei_endnode)
            if not os.path.exists(os.path.join(out_merge_path,'output.wfst.mvrd.sub_modified.txt')):
                print ("\n\n\n***************modify sub net node failed********\n\n\n")
                exit()
             # if not 'LD_LIBRARY_PATH' in os.environ:
            os.environ['LD_LIBRARY_PATH'] =os.path.abspath('fst_lib/')
            os.system('echo $LD_LIBRARY_PATH')
            os.system('cat %s %s > %s'%(self.out_main_wfst_path,os.path.join(out_merge_path,'output.wfst.mvrd.sub_modified.txt'),os.path.join(out_merge_path,'output.wfst.merge.txt')))
            os.system('./tools/fstcompile --isymbols=%s --osymbols=%s %s %s'%(self.triphone_syms,self.word_syms,os.path.join(out_merge_path,"output.wfst.merge.txt"),os.path.join(out_merge_path,"output.wfst.mvrd.fst")))
            os.system('./tools/fstprint --isymbols=%s --osymbols=%s %s %s'%(self.triphone_syms,self.word_syms,os.path.join(out_merge_path,"output.wfst.mvrd.fst"),os.path.join(out_merge_path,"output.wfst.mvrd.txt")))

            serial_path = os.path.join(self.outputdir,"pack_wfst_"+num2LagDict[self.language]+".cfg")
            changeConfig(serial_path,"wfst_net_txt",os.path.abspath(os.path.join(out_merge_path,'output.wfst.mvrd.txt')),sectionName="input")
        
            if(self.is_yun==3):
                changeConfig(serial_path,"net_type",'0',sectionName="input")
                print('cd ./yun_ser/wfst_serialize_tool_V5.2/ && export LD_LIBRARY_PATH=./ && ./wfst_serialize_V5.2 %s'%os.path.abspath(serial_path))
                os.system('cd ./yun_ser/wfst_serialize_tool_V5.2/ && export LD_LIBRARY_PATH=./ && ./wfst_serialize_V5.2 %s'%os.path.abspath(serial_path))
            elif(self.is_yun==1 or self.is_yun==2):
                os.system('./duan_ser/pack_wfst_rnnt %s'%(serial_path))
            else:
                os.system('./duan_ser/pack_wfst %s'%(serial_path))
            md5_code = os.popen('md5sum %s'%(os.path.join(self.outputdir,'wfst.bin'))).readline().split(" ")[0]
            print(md5_code)

            newname = "%s_%s_wfst_main_%s_%s_%s.bin"%(num2LagDict[self.language], msg, os.popen('whoami').readline().strip(), datetime.datetime.now().strftime('%Y%m%d'),md5_code[-4::])
            print(newname)
            os.rename((os.path.join(self.outputdir,'wfst.bin')), (os.path.join(self.outputdir,newname)))
    
    def not_merge(self,msg):
        print("*******************not merge***********************")
        print(self.out_main_sub_path)
        if not (os.path.exists(self.out_main_wfst_path) or os.path.exists(self.out_main_sub_path)):
            print("\n\n\ntrain failed\n\n\n")
            exit()

        if os.path.exists(self.out_main_wfst_path):
            # change serialization cfg
            # serialization wfst
            serial_path = os.path.join(self.outputdir,"pack_wfst_"+num2LagDict[self.language]+".cfg")
            word_syms_path = (os.path.join(self.outputdir,'norm_3gram','lm_norm_3gram_%s'%self.norm_cut) if self.norm_cut else os.path.join(self.outputdir,'norm_3gram','lm_norm_3gram')) +'_ce_pak/words.syms'
            changeConfig(serial_path,"wordsSymsFile",os.path.abspath(word_syms_path),sectionName="input")
            changeConfig(serial_path,"wfst_net_txt",os.path.abspath(self.out_main_wfst_path),sectionName="input")

            if(self.is_yun==3):
                changeConfig(serial_path,"net_type",'0',sectionName="common")
                print('cd ./yun_ser/wfst_serialize_tool_V5.2/ && export LD_LIBRARY_PATH=./ && ./wfst_serialize_V5.2 %s'%os.path.abspath(serial_path))
                os.system('cd ./yun_ser/wfst_serialize_tool_V5.2/ && export LD_LIBRARY_PATH=./ && ./wfst_serialize_V5.2 %s'%os.path.abspath(serial_path))
            elif(self.is_yun==1 or self.is_yun==2):
                os.system('./duan_ser/pack_wfst_rnnt %s'%(serial_path))
            else:
                os.system('./duan_ser/pack_wfst %s'%(serial_path))

            md5_code = os.popen('md5sum %s'%(os.path.join(self.outputdir,'wfst.bin'))).readline().split(" ")[0]
            print(md5_code)

            newname = "%s_%s_wfst_main_%s_%s_%s.bin"%(num2LagDict[self.language], msg, os.popen('whoami').readline().strip(), datetime.datetime.now().strftime('%Y%m%d'),md5_code[-4::])
            print(newname)
            os.rename((os.path.join(self.outputdir,'wfst.bin')), (os.path.join(self.outputdir,newname)))

        if os.path.exists(self.out_main_sub_path):
            # serialization patch
            serial_path = os.path.join(self.outputdir,"pack_wfst_"+num2LagDict[self.language]+".cfg")

            changeConfig(serial_path,"wfst_net_txt",os.path.abspath(self.out_main_sub_path),sectionName="input")
        
            if(self.is_yun==3):
                
                if self.G_argument and  is_number(self.G_argument.split('-')[1]) and float(self.G_argument.split('-')[1]) == 0 :
                    changeConfig(serial_path,"net_type",'4',sectionName="common")
                    changeConfig(serial_path,"penalty_factor",'0',sectionName="common")
                else:
                    changeConfig(serial_path,"net_type",'5',sectionName="common")
                print('cd ./yun_ser/wfst_serialize_tool_V5.2/ && export LD_LIBRARY_PATH=./ && ./wfst_serialize_V5.2 %s'%os.path.abspath(serial_path))
                os.system('cd ./yun_ser/wfst_serialize_tool_V5.2/ && export LD_LIBRARY_PATH=./ && ./wfst_serialize_V5.2 %s'%os.path.abspath(serial_path))
            elif(self.is_yun==1 or self.is_yun==2):
                os.system('./duan_ser/pack_wfst_rnnt %s'%(serial_path))
            else:
                os.system('./duan_ser/pack_wfst %s'%(serial_path))
            
            md5_code = os.popen('md5sum %s'%(os.path.join(self.outputdir,'wfst.bin'))).readline().split(" ")[0]
            print(md5_code)

            newname = "%s_%s_custom_patch_%s_%s_%s.bin"%(num2LagDict[self.language], msg, os.popen('whoami').readline().strip(), datetime.datetime.now().strftime('%Y%m%d'),md5_code[-4::])
            print(newname)
            os.rename((os.path.join(self.outputdir,'wfst.bin')), (os.path.join(self.outputdir,newname)))

    
    def generate_G_pak(self,corpus_path,output_path):
        self.getallslot()
        if corpus_path is not None and os.path.exists(corpus_path):
            os.makedirs(output_path)

            isarc = True if self.G_argument.split('-')[0]=="0" else False
            score = float(self.G_argument.split('-')[1]) if is_number(self.G_argument.split('-')[1]) else 6
           
            Gnet = G_net_maker(os.path.join(output_path,"G_base"),os.path.join(output_path,"oov_G_base"),self.allslot,isarc,score,self.slot_argument)
            all_corpus_file = io.open(corpus_path, mode='r',encoding='utf-8') if sys.version_info[0]==2 else open(corpus_path, mode='r',encoding='utf-8')
            while True:
                inline = all_corpus_file.readline()
                if not inline:
                    break
                Gnet.write_one_regular_line(inline.strip())
            Gnet.flush()
            all_corpus_file.close()


            word_syms_file = io.open(os.path.join(output_path,"words.syms"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(output_path,"words.syms"), mode='w',encoding='utf-8')

            dictfile =io.open(self.dict,"r",encoding='utf-8') if sys.version_info[0]==2 else open(self.dict,"r",encoding='utf-8')
            words_set = list()
            words_set.append('-')
            words_set.append('<s>')
            words_set.append('</s>')
            words_set.append('-pau-')

            all_word_set = set()

            for line in dictfile.read().splitlines():
                dict_iteam, phone_iteam = line.split('\t')
                all_word_set.add(dict_iteam)
            dictfile.close()

            words_set.extend(list(all_word_set))
            
            word_id = 0
            for word in words_set:
                word_syms_file.write(word+"\t"+str(word_id)+"\n")
                word_id = word_id+1
            word_syms_file.close()

            os.environ['LD_LIBRARY_PATH'] =os.path.abspath('fst_lib/')
            os.system('echo $LD_LIBRARY_PATH')
            os.system('./fst_bin/fstcompile --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G_base"),os.path.join(output_path,"G.comple")))
            # os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G.comple"),os.path.join(output_path,"G.comple_debug")))
            os.system('./fst_bin/fstdeterminize %s %s'%(os.path.join(output_path,"G.comple"),os.path.join(output_path,"G.det")))
            # os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G.det"),os.path.join(output_path,"G.det_debug")))
            os.system('./fst_bin/fstminimize %s %s'%(os.path.join(output_path,"G.det"),os.path.join(output_path,"G.det.min")))
            # os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G.det.min"),os.path.join(output_path,"G.det.min_debug")))
            os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G.det.min"),os.path.join(output_path,"G")))
            os.system('echo DNOE >%s'%(os.path.join(output_path,"GeneratedG.DONE")))
            # exit()
            if self.language==0 and (self.is_yun==0):
                print('./bin/esr_package_20201224_noctc %s %s ./temp.3gram %s > %s'%(self.dict, self.hmm_list, output_path, os.path.join(self.outputdir,'pak.log')))
                os.system('./bin/esr_package_20201224_noctc %s %s ./temp.3gram %s > %s'%(self.dict, self.hmm_list, output_path, os.path.join(self.outputdir,'pak.log')))
            elif(self.is_yun==1 or self.is_yun==2):
                os.environ['LD_LIBRARY_PATH'] =os.path.abspath('/opt/compiler/gcc-7.3.0-os7.2/lib64/')
                print('./bin/package_ed_sp_v2 %s %s ./temp.3gram %s > %s'%(self.dict, self.hmm_list, output_path, os.path.join(self.outputdir,'pak.log')))
                os.system('./bin/package_ed_sp_v2 %s %s ./temp.3gram %s > %s'%(self.dict, self.hmm_list, output_path, os.path.join(self.outputdir,'pak.log')))
            else:
                print('./bin/package_speed_mhwu %s %s ./temp.3gram 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, os.path.join(self.outputdir,'pak.log')))
                os.system('./bin/package_speed_mhwu %s %s ./temp.3gram 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, os.path.join(self.outputdir,'pak.log')))

        return

    def train_ngram_pak(self,corpus_path, output_path, train_ctc, cut):
        if corpus_path is not None and os.path.exists(corpus_path):
            print('./bin/ngram-count -order 3 -vocab %s -text %s -lm %s -gt1min 0 -gt2min 0 -gt3min 0 -interpolate -cdiscount 0.5 > %s'%(self.dict,corpus_path,output_path,os.path.join(self.outputdir,'ngram-count.log')))
            os.system('./bin/ngram-count -order 3 -vocab %s -text %s -lm %s -gt1min 0 -gt2min 0 -gt3min 0 -interpolate -cdiscount 0.5 > %s'%(self.dict,corpus_path,output_path,os.path.join(self.outputdir,'ngram-count.log')))
            if cut :
                os.system('./bin/ngram-prune -order 3 -lm %s -write-lm %s -size %s > ngram-prune.log'%(output_path, output_path+"_"+cut , cut))
                output_path=output_path+"_"+cut
            os.makedirs(output_path+'_ce_pak')
            if self.language==0 and (self.is_yun==0):
                print('./bin/esr_package_20201224_noctc %s %s %s 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, output_path+'_ce_pak',os.path.join(self.outputdir,'pak_ce.log')))
                os.system('./bin/esr_package_20201224_noctc %s %s %s 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, output_path+'_ce_pak',os.path.join(self.outputdir,'pak_ce.log')))
            elif(self.is_yun==1 or self.is_yun==2):
                os.environ['LD_LIBRARY_PATH'] =os.path.abspath('/opt/compiler/gcc-7.3.0-os7.2/lib64/')
                print('./bin/package_ed_sp_v2 %s %s %s 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, output_path+'_ce_pak',os.path.join(self.outputdir,'pak_ce.log')))
                os.system('./bin/package_ed_sp_v2 %s %s %s 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, output_path+'_ce_pak',os.path.join(self.outputdir,'pak_ce.log')))
            else:
                print('./bin/package_speed_mhwu %s %s %s 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, output_path+'_ce_pak',os.path.join(self.outputdir,'pak_ce.log')))
                os.system('./bin/package_speed_mhwu %s %s %s 20.0 %s > %s'%(self.dict, self.hmm_list, output_path, output_path+'_ce_pak',os.path.join(self.outputdir,'pak_ce.log')))
            if train_ctc and os.path.exists(self.hmm_list_blank) :
                os.makedirs(output_path+'_ctc_pak')
                os.system('./bin/package_add_blank %s %s %s 20.0 %s > %s'%(self.dict, self.hmm_list_blank, output_path, output_path+'_ctc_pak',os.path.join(self.outputdir,'pak_ctc.log')))
    
# merge wfst -------find maxnode and endnode
def findmaxnode(inputname):
#	filein = open(inputname,"r",encoding="utf8")
    filein = open(inputname,"r")
    newline = filein.readline()
    maxnode=0
    endnode=0
    count=0
    while newline!="":
        count+=1
        newline = newline.strip().split("\t")
        if len(newline)!=1:
            if newline[0].isdigit() and newline[1].isdigit():
                    maxnode = max(maxnode,int(newline[0]),int(newline[1]))
            else:
                specialine = " ".join(newline)
                print("Warning1: Special line - \""+specialine+"\"")
        else:
            if newline[0].isdigit():
                maxnode =max(maxnode,int(newline[0]))
                endnode=newline[0]
                print("Endnode: "+endnode)
            else:
                print("Warning2: Special line - \""+newline[0]+"\"")
        if count==10000000:
            count=0
            print("Current Maxnode: "+str(maxnode))
        newline = filein.readline()
    print("Final Maxnode and Endnode: " + str(maxnode) + " " + str(endnode))
    return maxnode,endnode
# merge wfst ------modify mode index
def modify_nodes(inputname,outputname,maxnode,endnode,endnode_self):
#   filein = open(inputname,"r",encoding="utf8")
    filein = open(inputname,"r")
    #fileout = open(outputname,"w",encoding="utf8")
    fileout = open(outputname,"w")
    maxnode_G = int(maxnode)
    endnode_G = int(endnode)
    endnode_L = int(endnode_self)
    
    linein = filein.readline()
    while linein !="":
        linein = linein.strip().split("\t")
        if len(linein)!=1:
            if linein[0] != "0":
                linein[0] = str(int(linein[0])+maxnode_G)
            if linein[1] == str(endnode_L):
                linein[1] = str(endnode_G)
            else:
                linein[1] = str(int(linein[1])+maxnode_G)
            fileout.write("\t".join(linein)+"\n")
        linein = filein.readline()
    fileout.close()
    return 0
# change serialization cfg
def changeConfig(configFile,paramName,paramValue,sectionName=None):  
    print(configFile)  
    print("start change config, %s" % configFile)
    fconfig=io.open(configFile, mode='r',encoding='gbk') if sys.version_info[0]==2 else open(configFile, mode='r',encoding='gbk')
    lines=fconfig.readlines()
    fconfig.close()
    param_find=r'^\s*(.*?)\s*=\s*(.*?)\s*(#+.*)*$'
    section_find=r'^\s*\[(.*?)\]\s*'
    config_line=[]
    if sectionName==None:
        find=False
        for i in range(0,len(lines)):
            one_line=lines[i].strip()
            m=re.match(param_find,one_line)
            if m:
                temp_param=m.group(1)
                temp_value=m.group(2)
                if temp_param==paramName:
                    theValue="%s =%s \n"%(paramName,paramValue)
                    config_line.append(theValue)
                    find=True
                else:
                    config_line.append(lines[i])
                #print '%s=%s'%(temp_param,temp_value)
            else:
                config_line.append(lines[i])
        if not find:
            config_line.append('\n')
            theValue="%s =%s \n"%(paramName,paramValue)
            config_line.append(theValue)
    else:
        find=False
        find_section=False        
        for i in range(0,len(lines)):
            one_line=lines[i].strip()            
            m=re.match(section_find,one_line)
            if m:               
                temp_section=m.group(1)               
                if temp_section==sectionName:                    
                    find_section=True
                    config_line.append(lines[i])
                    continue
                if find_section:
                    find_section=False
                    if not find:
                        theValue="%s =%s \n"%(paramName,paramValue)
                        config_line.append(theValue)
                        config_line.append('\n')
                        find_section=False
                        find=True               
        
            if find_section:
                param_m=re.match(param_find,one_line)
                if param_m:
                    temp_param=param_m.group(1)
                    temp_value=param_m.group(2)
                    if temp_param==paramName:                        
                        theValue="%s =%s \n"%(paramName,paramValue)
                        config_line.append(theValue)
                        find=True
                    else:
                        config_line.append(lines[i])
                else:
                    config_line.append(lines[i])
            else:
                config_line.append(lines[i])
        if not find:
            theValue="%s =%s \n"%(paramName,paramValue)
            config_line.append(theValue)
            config_line.append('\n')
        
    f=io.open(configFile, mode='w',encoding='gbk') if sys.version_info[0]==2 else open(configFile, mode='w',encoding='gbk')
    f.writelines(config_line)
    f.close() 

# process: 
# 1銆乪xpand slot and shuofa
# 2銆乫ilter all corpus by allowlist and lower
# 3銆乻pecial process Uper(add)
# 4銆乬et dict 

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-l','--language', type=int,required=True, default=None, help=str(num2LagDict))
    parser.add_argument('--norm_train_ctc', action='store_true')
    parser.add_argument('--norm_cut', type=str, default='7e5', help='argument for norm cut.')
    parser.add_argument('--custom_train_ctc', action='store_true')
    parser.add_argument('--custom_cut', type=str, default=None, help='Argument for custom cut.')

    parser.add_argument('-G','--G_argument', type=str, default=None, help='Argument for G package.')
    parser.add_argument('--G_expand', action='store_true')

    parser.add_argument('--ismerge', action='store_true',help='Train norm and custom and package ,merge two wfst')
    parser.add_argument('--word_syms', type=str, default=None, help='Path of word_syms.')
    parser.add_argument('--phone_syms', type=str, default=None, help='Path of phone_syms.')
    parser.add_argument('--triphone_syms', type=str, default=None, help='Path of triphone_syms.')
    parser.add_argument('--dict', type=str, default=None, help='Path of phone dict.')
    parser.add_argument('--hmm_list', type=str, default=None, help='Path of hmm_list.')
    parser.add_argument('--hmm_list_blank', type=str, default=None, help='Path of hmm_list_blank.')
    parser.add_argument('--mapping', type=str, default=None, help='Path of mapping.txt.')
    parser.add_argument('--msg', type=str, default="projectname_", help='Name of the output file')
    parser.add_argument('--output', type=str, default="output", help='Path of output dir')

    parser.add_argument('--norm_excel_corpus_path', type=str, default=None, help='Norm train data excel path')
    parser.add_argument('--norm_train_data_slot', type=str, default=None, help='Norm train slot data path')
    parser.add_argument('--norm_train_data_shuofa', type=str, default=None, help='Norm train shuofa data path')
    parser.add_argument('-np','--norm_train_data_corpus', type=str, default=None, help='Norm train sent data path')

    parser.add_argument('--excel_corpus_path', type=str, default=None, help='Custom train data excel path')
    parser.add_argument('--train_data_slot', type=str, default=None, help='Custom train slot data path')
    parser.add_argument('--train_data_shuofa', type=str, default=None, help='Custom train shuofa data path')
    parser.add_argument('-cp','--train_data_corpus', type=str, default=None, help='Custom train sent data path')

    parser.add_argument('--expand_argument', type=str, default=None, help='Argument for corpus expand exp: poi-16,city-20')
    parser.add_argument('--dict_max', type=int, default=600000, help='')
    parser.add_argument('--predict_phone_for_new', action='store_true',help='Use tts tools predict new word phone')
    parser.add_argument('--use_old_phone_system', action='store_true',help='Use a map fuction trans new phone system to old system')
    parser.add_argument('--only_corpus_process', action='store_true',help='Only process corpus not package or serlia')
    parser.add_argument('--is_yun', type=int,required=True,help=str(package_map))
    args = parser.parse_args()


    if os.path.exists(args.output):
        os.rename(args.output, args.output+datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S'))

    if args.dict is None or not os.path.exists(args.dict):
        args.dict = "./res/%s_res/%s/new_dict" % (num2LagDict[args.language],package_map[args.is_yun])

    corpus_process = None

    if not (args.G_argument and (not args.G_expand)):
        # ****************************corpus_process****************************
        # create object
        corpus_process = get_corpus_process(args.language, args.norm_excel_corpus_path, args.norm_train_data_slot, args.norm_train_data_shuofa, args.norm_train_data_corpus, os.path.join(args.output,"norm_corpus_process"), args.expand_argument,args.dict, args.dict_max, args.predict_phone_for_new, args.use_old_phone_system, args.is_yun)
        # corpus process
        corpus_process.corpus_process()
        # reset patch
        corpus_process.reset()

        corpus_process.set_corpus_path(args.excel_corpus_path, args.train_data_slot, args.train_data_shuofa, args.train_data_corpus, os.path.join(args.output,"custom_corpus_process"),args.expand_argument)

        corpus_process.corpus_process()
        # ****************************corpus_process****************************

        # ****************************combiecorpus****************************
        # combine all final corpus
        if os.path.exists(os.path.join(args.output,"norm_corpus_process","final_train")) and len(os.listdir(os.path.join(args.output,"norm_corpus_process","final_train")))!=0:
            cmd = 'cat'
            for root,dirs,files in os.walk(os.path.join(args.output,"norm_corpus_process","final_train")):
                for file in files:
                    if file.startswith("oov_"):
                        continue
                    else:
                        cmd = cmd +" "+ os.path.join(root,file)
            print('%s > %s'%(cmd,os.path.join(args.output,"norm_final_train_corpus.txt")))
            os.system('%s > %s'%(cmd,os.path.join(args.output,"norm_final_train_corpus.txt")))
        
        if os.path.exists(os.path.join(args.output,"custom_corpus_process","final_train")) and len(os.listdir(os.path.join(args.output,"custom_corpus_process","final_train")))!=0:
            cmd = 'cat'
            for root,dirs,files in os.walk(os.path.join(args.output,"custom_corpus_process","final_train")):
                for file in files:
                    if file.startswith("oov_"):
                        continue
                    else:
                        cmd = cmd +" "+ os.path.join(root,file)
            print('%s > %s'%(cmd,os.path.join(args.output,"custom_final_train_corpus.txt")))
            os.system('%s > %s'%(cmd,os.path.join(args.output,"custom_final_train_corpus.txt")))
    
        # ****************************combiecorpus****************************
    
    else:
        # ****************************corpus_process****************************
        corpus_process = get_G_corpus_process(args.language, args.excel_corpus_path, args.train_data_slot, args.train_data_shuofa, args.train_data_corpus, os.path.join(args.output,"custom_corpus_process"), args.expand_argument,args.dict, args.dict_max, args.predict_phone_for_new, args.use_old_phone_system, args.is_yun)
        corpus_process.corpus_process()
        # ****************************corpus_process****************************


        # ****************************combiecorpus****************************
        if os.path.exists(os.path.join(args.output,"custom_corpus_process","shuofa_final_train")) and len(os.listdir(os.path.join(args.output,"custom_corpus_process","shuofa_final_train")))!=0:
            cmd = 'cat'
            for root,dirs,files in os.walk(os.path.join(args.output,"custom_corpus_process","shuofa_final_train")):
                for file in files:
                    if file.startswith("oov_"):
                        continue
                    else:
                        cmd = cmd +" "+ os.path.join(root,file)
            print('%s > %s'%(cmd,os.path.join(args.output,"custom_final_train_corpus.txt_noset")))
            os.system('%s > %s'%(cmd,os.path.join(args.output,"custom_final_train_corpus.txt_noset")))
            with open (os.path.join(args.output,"custom_final_train_corpus.txt_noset"),'r',encoding = "utf-8") as f:
               all_line_set = set(f.read().splitlines())
            infile = open(os.path.join(args.output,"custom_final_train_corpus.txt"), mode='w',encoding="utf-8")
            for sent in all_line_set:
                infile.write(sent+'\n')
            infile.close()
        # ****************************combiecorpus****************************



        

# ****************************package****************************
    if not args.only_corpus_process:
        package = Package(args.language, \
        args.norm_train_ctc, \
        args.norm_cut, \
        args.custom_train_ctc, \
        args.custom_cut, \
        args.ismerge, \
        args.output, \
        args.dict, \
        args.hmm_list, \
        args.hmm_list_blank, \
        args.mapping, \
        args.word_syms, \
        args.phone_syms, \
        args.triphone_syms, \
        args.is_yun, \
        args.G_argument,\
        args.expand_argument)

        package.set_dict(corpus_process.get_dict_path())
        if (args.G_argument and (not args.G_expand)):
            package.set_slot_path(corpus_process.get_slot_path())
        if os.path.exists(os.path.join(args.output,"norm_final_train_corpus.txt")):
            package.set_norm_corpus(os.path.join(args.output,"norm_final_train_corpus.txt"))
        
        if os.path.exists(os.path.join(args.output,"custom_final_train_corpus.txt")):
            package.set_custom_corpus(os.path.join(args.output,"custom_final_train_corpus.txt"))

        print("pack_ngram_begin")
        package.pack_ngram()
        

        package.serial(args.msg)

# ****************************package****************************
