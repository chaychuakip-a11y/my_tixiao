#coding=utf-8
import sys
sys.path.insert(0, "./python_lib")
import os
import io
import re
import sys
import random
import collections
import xlrd
from multiprocessing import Pool
import pickle
from pythainlp.tokenize import subword_tokenize
import spacy

global_symbols = globals()
MAX_WORD_LENGTH=64
nlp = None
nlp=spacy.load('ja_core_news_lg')


need_split = {'japan','thai'}
number_set = {u'0', u'1', u'2', u'3', u'4', u'5', u'6', u'7', u'8', u'9'}
regular_char_set = {"[","]","(",")","|"}
def has_digits(s):
    return any((char in number_set) for char in s)
def parsenumber(word):
    try:
        if word.startswith("0X") or word.startswith("0x"):
            code_point = int(word, 16)
            return chr(code_point)
        elif word.startswith("0"):
            code_point = int(word, 8)
            return chr(code_point)
        code_point = int(word)
        return chr(code_point)
    except ValueError:
        print("deal %s got problem"%word)
        exit()



languageList="69260:En:EnGam.txt 69160:Ja:JaJp.txt 69180:Ar:ArEn.txt 69240:Fr:FrRgM.txt 69520:Sp:SpEs.txt 69340:De:DeEm.txt 69380:It:ItIt.txt 70061:Pt:PtPt.txt 69200:Ru:RuRu.txt 70600:Fa:FaIr.txt 69400:Th:ThTh.txt 70030:Ms:MsMy.txt 70440:Id:IdId.txt 70520:Sv:SvSe.txt 69280:Nl:NlNl.txt"

ttsdict = {
        "english":69260,
		"japan":69160,
		"arabic":69180,
		"french":69240,
		"spanish":69520,
		"german":69340,
		"italy":69380,
		"portugal":70061,
		"russian":69200,
		"persian":70600,
		"thai":69400,
		"malaysia":70030,
		"indonesia":70440,
		"sweden":70520,
		"netherlands":69280,
		"BgBg":70110,
		"BnBd":70720,
		"BoCn":79351,
		"CsCz":70490,
		"ElGr":70670,
		"HaNg":70550,
		"hindi":69580,
		"korean":69500,
		"kazakh":69360,
		"MmnMn":69420,
		"poland":69320,
		"RoRo":	70650,
		"SwTz":	70680,
		"TaIn":	70700,
		"filipino":	69301,
		"UgSp":70560,
		"UkUa":70510,
		"UrPk":70590,
		"uzbekistan":70620,
		"vietnamese":69540,
		"turkey":69650,
}

num2LagDict = {int(iteam.split(":")[0].strip()):iteam.split(":")[1].strip() for iteam in open("language_map","r",encoding='utf-8').read().splitlines() if iteam.strip()}

post_set = {u'0', u'1', u'2', u'3', u'4', u'5', u'6', u'7', u'8', u'9', u'%'}

def get_merged_cell_value(sheet, row, col):
    """
    获取合并单元格的值
    """
    merged_cells = sheet.merged_cells
    for (start_row, end_row, start_col, end_col) in merged_cells:
        if row >= start_row and row < end_row and col >= start_col and col < end_col:
            cell_value = sheet.cell_value(start_row, start_col)
            return cell_value
    return sheet.cell_value(row, col)

def parse_word_phone_block(word_phone_block):
    block_list=[]
    word = ''
    one_block=''
    stack=[]
    for character in word_phone_block.strip():
        if(character=="#" or character=="*" or (character==' 'and len(stack)==0)):
            continue
        if character=='[' or character=='(':
            stack.append(character)
        elif character==']' or character==')':
            stack.pop()
            if len(stack) ==1:
                block_list.append(one_block.strip())
                one_block=''
        else:
            if len(stack)==0:
                word = word + character
            else:
                if len(stack)==3:
                    one_block = one_block + character
    return word.strip(), block_list

def parse_word_phone(word_phone_block):
    word=''
    phone=''
    stack=[]
    # for subword in inline.strip().split('*'):
    for character in word_phone_block.strip():
        if(character=="#" or character=="*"or (character==' 'and len(stack)==0)):
            continue
        if character=='[' or character=='(':
            stack.append(character)
        elif character==']' or character==')':
            stack.pop()
            if len(stack)==1:
                phone = phone + " "
        else:
            if len(stack)==0:
                word = word + character
            else:
                if len(stack)==3:
                    phone = phone + character
    return word.strip(), phone.strip().split()

class Phone_map:

    def __init__(self, language,is_yun):
        self.language = language
        self.map_dict = None
        map_dict_path = "./res/%s_res/yun/phone_map.pk" % num2LagDict[language] if is_yun else "./res/%s_res/duan/phone_map.pk"% num2LagDict[language]
        if(os.path.exists(map_dict_path)):
            with open(map_dict_path,'rb') as file_to_read:
                self.map_dict = pickle.load(file_to_read)
    
    def get_map_phone(self,new_sequence):
        if self.map_dict is None:
            return None
        old_sequence=''
        start = 0
        while(start < len(new_sequence)):
            exist = False
            for end in range(len(new_sequence) ,start , -1):
                exist,key = self.is_exist(new_sequence[start:end])
                if exist:
                    old_sequence = old_sequence+' '+self.map_dict[key]
                    start = end
                    break
            if exist:
                continue
            for key in new_sequence[start].split(' '):
                old_sequence = old_sequence+' '+self.map_dict[key]
                start = start + 1
        return old_sequence.strip()
    
    def is_exist(self,phone_block):
        key = ''
        for phone in phone_block:
            key = key + ' ' + phone
        if (key.strip() in self.map_dict.keys()):
            return True,key.strip()
        return False,key.strip()


class repalce_Node:
    def __init__(self):
        self.char_node = dict()
        self.char = None
        self.depth = 0
        self.is_final = False
        self.final_replace = None
        self.fail_node = None
        self.char_set = set()

    def search(self,char):
        if char in self.char_node:
            return self.char_node[char]
        return None
    
    def add(self,char):
        self.char_node[char] = repalce_Node()
        return self.char_node[char]

    def __str__(self):
        return str(self.char) + str(self.depth) + "("+",".join(self.char_node.keys())+")"


class slot_begin_end:
    def __init__(self,begin,end):
        self.begin = begin
        self.end = end
    def __str__(self):
        return self.begin + self.end
    def __hash__(self):
        return hash((self.begin, self.end))


    def __eq__(self, other):

        if not isinstance(other, slot_begin_end):
            return False
        return self.begin == other.begin and self.end == other.end

    def __repr__(self):
        return "begin=" + self.begin + " end=" + self.end

class Tree_Node:
    def __init__(self,word,node):
        self.word = word
        self.node = node


class repalce_Tree:
    def __init__(self):
        self.root = repalce_Node()
    
    def search(self,corpus):
        result = list()
        temp_root = self.root
        search_start = 0
        str_index = 0
        while((str_index < len(corpus)) and (search_start < len(corpus))):

            find_node = temp_root.search(corpus[str_index])
            if find_node is not None:
                temp_root = find_node
                str_index = str_index + 1
                if (find_node.is_final):
                    result.append(match_case(search_start,find_node.depth,find_node.final_replace))
            else:
                if temp_root.fail_node!=None:
                    search_start = search_start + (temp_root.depth-temp_root.fail_node.depth)
                    temp_root = temp_root.fail_node
                    if (temp_root.is_final):
                        result.append(match_case(search_start,temp_root.depth,temp_root.final_replace))
                else:
                    if temp_root==self.root:
                        str_index = str_index+1
                        search_start = str_index
                    else:
                        search_start = str_index
                        temp_root = self.root
                
        return result
    
    def search_fail(self,sent_str):
        j = 0
        temp_root = self.root
        while(j<len(sent_str)):
            temp_node = temp_root.search(sent_str[j])
            if temp_node == None:
                return None
            else:
                temp_root = temp_node
                j = j+1
        return temp_root

    def build_fail_node(self):
        queue = list()
        queue.append(Tree_Node("",self.root))
        while(len(queue)>0):
            temp_node = queue[0].node
            word = queue[0].word
            queue.pop(0)
            for key,value in temp_node.char_node.items():
                queue.append(Tree_Node(word+key,value))
            
            if ((temp_node.depth > 1)):
                for i in range(1,len(word)):
                    # print(word[i::])
                    fail_node = self.search_fail(word[i::])
                    if fail_node is not None:
                        temp_node.fail_node = fail_node
                        break

    def add_itedm(self,replace1,replace2):
        temp_root = self.root
        for index,char in enumerate(replace1):
            find_node = temp_root.search(char)
            if find_node == None:
                new_node = temp_root.add(char)
                new_node.depth = temp_root.depth +1
                new_node.char = char
                temp_root = new_node
            else:
                temp_root = find_node
            
            if index == len(replace1)-1:
                temp_root.is_final = True
                temp_root.final_replace = replace2
            

    def dump(self):
        with open ("dump.txt","w",encoding = "utf-8") as f:
            queue = list()
            queue.append(self.root)
            visit_num = 0
            current_depth_num = 1
            next_depth_num = 0
            while len(queue) > 0:

                f.write(str(queue[0])+"\t")
                visit_num = visit_num +1

                for key,value in queue[0].char_node.items():
                    next_depth_num = next_depth_num+1
                    queue.append(value)
                
                if visit_num == current_depth_num:
                    f.write("\n")
                    current_depth_num = next_depth_num
                    next_depth_num = 0
                    visit_num = 0
                queue.pop(0)

class match_case:
    def __init__(self,begin,num,replace):
        self.begin = begin
        self.num = num
        self.replace = replace
    def __str__(self):
        return str(self.begin) + " " + str(self.num) + " " + str(self.replace)

class replace:
    def __init__(self,replace_dict,allow_list):
        self.Tree = repalce_Tree()
        self.all_list = allow_list
        for key,value in replace_dict.items():
            self.Tree.add_itedm(key,value)
        # self.Tree.build_fail_node()
        self.match = list()
        # self.Tree.dump()
    
    def clear_overide_match(self):
        if len(self.match)==0:
            return
    
        temp_match_list = list()
        temp_match_list.append(self.match[0])
        start_index = self.match[0].begin
        end_index = start_index + self.match[0].num -1 

        for i in range (1,len(self.match)):
            if start_index == self.match[i].begin:
                temp_match_list[-1] = self.match[i]
                end_index = start_index + self.match[i].num -1 
            elif self.match[i].begin > end_index:
                temp_match_list.append(self.match[i])
                start_index = self.match[i].begin
                end_index = start_index + self.match[i].num -1 
        
        self.match = temp_match_list
    
    def clear_uncomplete_match(self,corpus):

        for i in range (len(self.match)-1,-1,-1):
            start_index = self.match[i].begin
            end_index = start_index+self.match[i].num-1

            if corpus[end_index] == ">" and (end_index < len(corpus)-1):
                if corpus[end_index +1] == "\'":
                    del self.match[i]
            if corpus[start_index] == "<" and (start_index > 0):
                if corpus[start_index -1] == "\'":
                    del self.match[i]

            if (start_index==0):
                if (end_index==len(corpus)-1):
                    continue
                elif ((corpus[end_index] in self.all_list) and (corpus[end_index+1] in self.all_list)):
                    del self.match[i]
                else:
                    continue
            elif (end_index==len(corpus)-1):
                if ((corpus[start_index] in self.all_list) and (corpus[start_index-1] in self.all_list)):
                    del self.match[i]
                else:
                    continue
            else:
                if (((corpus[start_index] in self.all_list) and (corpus[start_index-1] in self.all_list)) or ((corpus[end_index] in self.all_list) and (corpus[end_index+1] in self.all_list))):
                    del self.match[i]
    
    def update_match(self,corpus):
        str_index = 0
        result_list = list()
        for item in self.match:
            result_list.append(corpus[str_index:item.begin])
            result_list.append(item.replace)
            str_index = item.begin + item.num
        # print(str_index)
        result_list.append(corpus[str_index::])
        return "".join(result_list)

    def replace(self,corpus):
        # str_index = 0
        # while(str_index<len(corpus)):
        #     str_index = str_index+1
        # return corpus
        self.match = self.Tree.search(corpus)
        # for item in self.match:
        #     print(item)

        self.clear_uncomplete_match(corpus)
        self.clear_overide_match()
        # print("clear_over_ride")

        # for item in self.match:
        #     print(item)

        
        # print("clear_uncomplete")
        # for item in self.match:
        #     print(item)
        # return corpus

        return self.update_match(corpus)

class filewriter:
    def __init__(self,path,mode,encoding):
        self.file = open(path, mode=mode,encoding=encoding)
        self.buffer = []
    def write(self,line):
        self.buffer.append(line)
        if len(self.buffer) > 10000000:
            self.file.write("".join(self.buffer))
            self.buffer.clear()
    def close(self):
        if len(self.buffer) > 0:
            self.file.write("".join(self.buffer))
            self.buffer.clear()
        self.file.close()

class Corpus_process:
    
    def __init__(self, language,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument, dict_base, dict_max, predict_phone_for_new,use_old_phone_system,is_yun):

        self.output_dir = output_dir
        self.excel_path = excel_path
        self.slot_path = slot_path
        self.shuofa_path = shuofa_path
        self.train_corpus = train_corpus
        self.language = language
        self.replace_list = dict()
        self.pattern = None
        

        self.allow_list = {u'A', u'a', u'B', u'b', u'C', u'c', u'D', u'd', u'E', u'e', u'F', u'f', u'G', u'g', u'H', u'h', u'I', u'i', u'J', u'j', u'K', u'k', u'L', u'l', u'M', u'm', u'N', u'n', u'O', u'o', u'P', u'p', u'Q', u'q', u'R', u'r', u'S', u's', u'T', u't', u'U', u'u', u'V', u'v', u'W', u'w', u'X', u'x', u'Y', u'y', u'Z', u'z','\''}
        if os.path.exists(os.path.join("allow_list",num2LagDict[language]+"_character.txt")):
            self.allow_list = self.allow_list.union({char for word in open(os.path.join("allow_list",num2LagDict[language]+"_character.txt"),"r",encoding='utf-8').read().split() for char in (set(word) if not has_digits(word) else parsenumber(word))})
        
        if os.path.exists(os.path.join("replace_list",num2LagDict[language]+"_replace_list.txt")):
            self.replace_list = {iteam.split(':')[0]:iteam.split(':')[1] for iteam in open(os.path.join("replace_list",num2LagDict[language]+"_replace_list.txt"),"r",encoding='utf-8').read().splitlines() if (iteam.strip() and (":" in iteam))}
        self.replace_list["<"] = " <"
        self.replace_list[">"] = "> "
        self.replace_list["><"] = "> <"
        self.pattern = replace(self.replace_list,self.allow_list)
        
        self.allow_word = set()
        if os.path.exists(os.path.join("allow_list",num2LagDict[language]+"_word.txt")):
            self.allow_word = self.allow_word.union({word.lower() for word in open(os.path.join("allow_list",num2LagDict[language]+"_word.txt"),"r",encoding='utf-8').read().split()})

        self.split_fuction = None

        self.word_counts = collections.Counter()
        self.dict_max = dict_max
        # restore all lower word and phone
        self.final_dict = dict()
        # restore all lower_words
        self.dict_set = None
        self.use_old_phone_system = use_old_phone_system
        
        self.predict_phone_for_new = predict_phone_for_new
        self.phone_map = Phone_map(language,is_yun)
        self.all_dict_set = set()
        self.is_yun = is_yun
              
        if dict_base is not None and os.path.exists(dict_base):
            dictfile =io.open(dict_base,"r",encoding='utf-8') if sys.version_info[0]==2 else open(dict_base,"r",encoding='utf-8')
            for line in dictfile.read().splitlines():
                if len(line.split('\t'))!=2:
                    continue
                dict_iteam, phone_iteam = line.split('\t')
                if len(dict_iteam) > MAX_WORD_LENGTH:
                    continue
                lower_dict = dict_iteam.casefold()
                if lower_dict not in self.final_dict.keys():
                    self.final_dict[lower_dict]=set()
                self.final_dict[lower_dict].add(phone_iteam.strip())
            dictfile.close()
        
        self.dict_set = set(self.final_dict.keys())

        self.slot_argument ={}
        if expand_argument is not None:
            templist = expand_argument.split(',')
            for elem in templist:
                self.slot_argument[elem.split('-')[0]] = int(elem.split('-')[1])
        
        self.allslot={}
        self.allslot_begin_end={}
        self.content_net = {}

        self.begin_notallow = set()
        self.end_notallow = set()
        self.set_begin_end_notallow()
    
    def set_begin_end_notallow(self):
        self.begin_notallow.add("\'")
        self.begin_notallow.add("-")
        self.begin_notallow.add(" ")

        self.end_notallow.add("\'")
        self.end_notallow.add("-")
        self.end_notallow.add(" ")
    
    def reset(self):
        self.output_dir = None
        self.excel_path = None
        self.slot_path = None
        self.shuofa_path = None
        self.train_corpus = None
        # self.slot_argument.clear()
        self.allslot.clear()
    
    def set_corpus_path(self,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument=None):
        self.output_dir = output_dir
        self.excel_path = excel_path
        self.slot_path = slot_path
        self.shuofa_path = shuofa_path
        self.train_corpus = train_corpus


        if expand_argument is not None:
            templist = expand_argument.split(',')
            for elem in templist:
                self.slot_argument[elem.split('-')[0]] = int(elem.split('-')[1])

    def check_slot_circle(self):
        slot_set = set()
        for key,value in self.allslot.items():
            slot_set.add(key)
            self.content_net[key] = set()
            self.allslot_begin_end[key] = set()
            self.allslot_begin_end[key].add(slot_begin_end("",""))
            for line in value:
                matches = re.findall(r'\S*<.*?>\S*',line)
                for one_match in matches:
                    left = re.findall(r'(\S*)<',one_match)
                    right = re.findall(r'>(\S*)',one_match)
                    middle = re.findall(r'<(.*?)>',one_match)

                    slot_set.add(middle[0])
                    self.content_net[key].add(middle[0])

                    if (left[0] != '') and (right[0] != ''):
                        print("got one slot have left and right ",one_match)
                    if middle[0] not in self.allslot_begin_end.keys():
                        self.allslot_begin_end[middle[0]] = set()
                        self.allslot_begin_end[middle[0]].add(slot_begin_end("",""))
                    
                    self.allslot_begin_end[middle[0]].add(slot_begin_end(left[0],right[0]))

        for slot in slot_set:
            if slot not in self.allslot.keys():
                self.allslot[slot] = set()
            if slot not in self.content_net.keys():
                self.content_net[slot] = set()
            if slot not in self.allslot_begin_end.keys():
                self.allslot_begin_end[slot] = set()
                self.allslot_begin_end[slot].add(slot_begin_end("",""))


        input_num = {key:0 for key in slot_set}
        for node,arc_set in self.content_net.items():
            for node_end in arc_set:
                input_num[node_end] = input_num[node_end]+1


        queue = []
        for slot,num in input_num.items():
            if num==0:
                queue.append(slot)

        node_count = 0
        while len(queue) !=0:
            one_slot = queue.pop(0)
            if len(self.allslot_begin_end[one_slot]) > 0:
                for line in self.allslot[one_slot]:
                    temp_list = line.split(" ")

                    left = re.findall(r'(\S*)<',temp_list[-1])
                    right = re.findall(r'>(\S*)',temp_list[-1])
                    middle = re.findall(r'<(.*?)>',temp_list[-1])

                    if len(middle)==0:
                        continue

                    if middle[0] != "":
                        for item in self.allslot_begin_end[one_slot]:
                            if item.end != "" and right[0] != "":
                                print("got one slot have two right ",temp_list[-1],item.end)
                                exit()
                            self.allslot_begin_end[middle[0]].add(slot_begin_end(left[0],item.end))

                    left = re.findall(r'(\S*)<',temp_list[0])
                    right = re.findall(r'>(\S*)',temp_list[0])
                    middle = re.findall(r'<(.*?)>',temp_list[0])
                    if len(middle)==0:
                        continue

                    if middle[0] != "":
                        for item in self.allslot_begin_end[one_slot]:
                            if item.begin != "" and left[0] != "":
                                print("got one slot have two right ",temp_list[-1],item.begin)
                                exit()
                            self.allslot_begin_end[middle[0]].add(slot_begin_end(item.begin,right[0]))

            for node_end in self.content_net[one_slot]:
                input_num[node_end] = input_num[node_end] -1 
                if input_num[node_end]==0:
                    queue.append(node_end)
            node_count = node_count+1


        if node_count == len(input_num):
            return
        
        print("slot got circle ")
        for slot,num in input_num.items():
            if num !=0:
                print("slot :" + slot)
        exit()
        return
        


    def corpus_process(self):
        print("\n\ngather_corpus_to_raw_begin:\n")
        self.gather_corpus_to_raw()
        print(self.language)
        if num2LagDict[self.language] in need_split:
            self.split_fuction = self.get_split_function()
            self.split_corpus()
        print("\n\nfilter_corpus_to_fortrain_begin:\n")
        self.filter_corpus_to_fortrain()
        print("\n\nget_dict_from_fortrain_begin:\n")
        self.get_dict_from_fortrain()
        print("\n\nfilter_corpus_by_finaldict_begin:\n")
        self.filter_corpus_by_finaldict()

    
    def get_split_function(self):
        if num2LagDict[self.language] =="japan":
            return Corpus_split_Japan()
        if num2LagDict[self.language] == "thai":
            return Corpus_split_Thai()
        return Corpus_split()

    def gather_corpus_to_raw(self):
        os.makedirs(os.path.join(self.output_dir,"slot"))
        os.makedirs(os.path.join(self.output_dir,"shuofa"))
        if self.slot_path is not None and os.path.exists(self.slot_path):
            os.system('cp %s/* %s'%(self.slot_path,os.path.join(self.output_dir,"slot")))
        if self.shuofa_path is not None and os.path.exists(self.shuofa_path):
            os.system('cp %s/* %s'%(self.shuofa_path,os.path.join(self.output_dir,"shuofa")))
        if self.excel_path is not None and os.path.exists(self.excel_path):
            for root ,dirs,files in os.walk(self.excel_path):
                for one_excel_path in files:
                # for one_excel_path in excel_path_set:
                    if os.path.exists(os.path.join(root,one_excel_path)):
                        data = xlrd.open_workbook(os.path.join(root,one_excel_path))
                        #print(f"DEBUG: Processing file: {one_excel_path}")
                        for sheet in data.sheets():
                            #print(f"DEBUG: Found sheet: '{sheet.name}'") # 确认是否有不可见字符
                            if sheet.name=="-" or "wfst" in sheet.name.casefold():
                                continue
                            if ('<' in sheet.name) and ('>' in sheet.name):
                                for i in range(sheet.ncols):
                                    one_slot_data = sheet.col_values(i)
                                    sub_slot_name = (one_slot_data[0] if one_slot_data[0]!='' else '')
                                    #print(f"DEBUG: Checking column {i}, header: '{sub_slot_name}'")
                                    if ('<' in sub_slot_name) and ('>' in sub_slot_name):
                                        #print(f"DEBUG: Column {sub_slot_name} matched, row count: {len(one_slot_data)-1}")
                                        sub_slot_name = sub_slot_name[1:-1]
                                    slot_name = sheet.name[1:-1]+ ('_' if sheet.name[1:-1]!="" else "") + sub_slot_name
                                    outfile = filewriter(os.path.join(self.output_dir,"slot",slot_name), mode='a',encoding='utf-8')
                                    for j in range(1,len(one_slot_data)):
                                        if (one_slot_data[j]!=''):
                                            temp_str = str(one_slot_data[j])
                                            if "\\" in temp_str:
                                                temp_str = temp_str.replace("\\","\n")
                                            if "/" in temp_str:
                                                temp_str = temp_str.replace("/","\n")
                                            outfile.write(temp_str)
                                            outfile.write('\n')
                                    outfile.close()
                            else:
                                outfile = filewriter(os.path.join(self.output_dir,"shuofa",sheet.name), mode='a',encoding='utf-8')
                                for i in range(sheet.ncols):
                                    one_slot_data = sheet.col_values(i)
                                    for j in range(0,len(one_slot_data)):
                                        if (one_slot_data[j]!=''):
                                            outfile.write(str(one_slot_data[j]))
                                            outfile.write('\n')
                                outfile.close()
            
        self.slot_path = os.path.join(self.output_dir,"slot")
        self.shuofa_path = os.path.join(self.output_dir,"shuofa")

        #### copy all scent corpus to raw dir ###
        os.makedirs(os.path.join(self.output_dir,"raw"))
        if self.train_corpus is not None and os.path.exists(self.train_corpus):
            print(self.train_corpus)
            for root ,dirs,files in os.walk(self.train_corpus):
                for file in files:
                    if os.path.getsize(os.path.join(root,file))/(1024*1024) < 500:
                        os.system('cp %s %s'%(os.path.join(root,file),os.path.join(self.output_dir,"raw")))
                        # shutil.copy2(os.path.join(root,file),os.path.join(self.output_dir,"raw"))
                    else:
                        os.system('split -l 625000 %s %s'%(os.path.join(root,file),os.path.join(self.output_dir,"raw",file+'_part_')))
        
        # expand slot and shuofa to raw
        self.read_slot_and_expand()

    def read_slot_and_expand(self):
        self.getallslot()
        self.check_slot_circle()
        self.process_file_in_dir(self.expand_corpus,self.shuofa_path,os.path.join(self.output_dir,"raw"))
    
    def split_corpus(self):
        os.rename(os.path.join(self.output_dir,"raw"),os.path.join(self.output_dir,"raw_before_split"))
        os.makedirs(os.path.join(self.output_dir,"raw"))
        self.process_file_in_dir(self.split_fuction.split,os.path.join(self.output_dir,"raw_before_split"),os.path.join(self.output_dir,"raw"))


    def filter_corpus_to_fortrain(self):
        os.makedirs(os.path.join(self.output_dir,"for_train"))
        #  filter raw corpus by allowchar to for_train dir
        self.process_file_in_dir(self.filter_corpus_by_char,os.path.join(self.output_dir,"raw"),os.path.join(self.output_dir,"for_train"))


        oov_set = set()
        for root ,dirs,files in os.walk(os.path.join(self.output_dir,"for_train")):
            for file in files:
                if file.startswith('oov_'):
                    file_oov = io.open(os.path.join(self.output_dir,"for_train",file), mode='r',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"for_train",file), mode='r',encoding='utf-8')# oov dict from for_train
                    for line in file_oov.readlines():
                        oov_set.add(line)
                    file_oov.close()


        gather_oov = io.open(os.path.join(self.output_dir,"for_train","oov_gather_oov"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"for_train","oov_gather_oov"), mode='w',encoding='utf-8')# oov dict from for_train
        for line in oov_set:
            gather_oov.write(line)
        gather_oov.close()

    def get_dict_from_fortrain(self):
        os.makedirs(os.path.join(self.output_dir,"dict_dir"))
        # count all word in for_train 
        self.process_file_in_dir(self.get_dict_from_corpus,os.path.join(self.output_dir,"for_train"),os.path.join(self.output_dir,"dict_dir"))

        # outfile = open(os.path.join(self.output_dir,"dict_dir","new_dict"),"w",encoding='utf-8')

        oov_count = collections.Counter()
        dict_count = collections.Counter()
        for root ,dirs,files in os.walk(os.path.join(self.output_dir,"dict_dir")):
            for file in files:
                if file.startswith('oov_'):
                    file_oov = io.open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8')# oov dict from for_train
                    for line in file_oov.readlines():
                        oov_count.update(collections.Counter({line.split('\t')[0]:int(line.split('\t')[1])}))
                    file_oov.close()
                else:
                    file = io.open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8')# oov dict from for_train
                    for line in file.readlines():
                        dict_count.update(collections.Counter({line.split('\t')[0]:int(line.split('\t')[1])}))
                    file.close()
    
        # # write all dict word in new_dict file for predict phone
        outfile = io.open(os.path.join(self.output_dir,"dict_dir","aaa_all_word"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_all_word"), mode='w',encoding='utf-8') #dict from for_train
        file_oov = io.open(os.path.join(self.output_dir,"dict_dir","aaa_oov_base_dict"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_oov_base_dict"), mode='w',encoding='utf-8')# oov dict from for_train
        base_dict_file = io.open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict"), mode='w',encoding='utf-8')# oov dict from for_train

        if self.is_yun ==1 or self.is_yun ==2 :
            base_dict_file.write(u'<s>\t<s>\n')
            base_dict_file.write(u'</s>\t</s>\n')
        else:
            base_dict_file.write(u'<s>\tsil\n')
            base_dict_file.write(u'</s>\tsil\n')
        # deal in set word
        for word,count in dict_count.most_common():
            lower_word = word.casefold()
            if lower_word in self.dict_set:
                #get all word has 
                self.all_dict_set.add(word)
                for phone in self.final_dict[lower_word]:
                    base_dict_file.write(word+'\t'+phone+'\n')
            if word !='':
                outfile.write(word+'\n')
        # deal out set word
        for word,count in oov_count.most_common():
            if word !='':
                file_oov.write(word+'\n')

        base_dict_file.close()
        outfile.close()
        file_oov.close()

        # print all dict_phone processed data
        dict_for_use = io.open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"), mode='w',encoding='utf-8')# oov dict from for_train
        if self.is_yun ==1 or self.is_yun ==2 :
            dict_for_use.write(u'<s>\t<s>\n')
            dict_for_use.write(u'</s>\t</s>\n')
        else:
            dict_for_use.write(u'<s>\tsil\n')
            dict_for_use.write(u'</s>\tsil\n')
        for word in self.all_dict_set:
            for phone in self.final_dict[word.casefold()]:
                dict_for_use.write(word+'\t'+phone+'\n')
        dict_for_use.close()
        

        if self.predict_phone_for_new:

            print("\n\npredict dict_to_phone syms begin")
            self.generate_phone_dict(os.path.join(self.output_dir,"dict_dir","aaa_oov_base_dict"),os.path.join(self.output_dir,"dict_dir"))
            print("predict dict_to_phone syms end")

            # cat base and oov
            os.system('cat %s %s > %s'%(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"),os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),os.path.join(self.output_dir,"dict_dir","aaa_dict_for_use")))
            # 
            # dictfile =io.open(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),"r",encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),"r",encoding='utf-8')
            # for line in dictfile.read().splitlines():
            #     dict_iteam, phone_iteam = line.split('\t')
            #     if dict_iteam not in self.dict_set:
            #         self.dict_set.add(dict_iteam)
            # dictfile.close()

            # update dict
            # self.final_dict.clear()
            # gather predicted word and base word which has phone
            if os.path.join(self.output_dir,"dict_dir","aaa_dict_phone") is not None and os.path.exists(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone")):
                dictfile =io.open(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),"r",encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),"r",encoding='utf-8')
                for line in dictfile.read().splitlines():
                    dict_iteam, phone_iteam = line.split('\t')
                    self.all_dict_set.add(dict_iteam)
                    lower_dict = dict_iteam.casefold()
                    if lower_dict not in self.final_dict.keys():
                        self.final_dict[lower_dict]=set()
                    self.final_dict[lower_dict].add(phone_iteam.strip())
                dictfile.close()
            # update all word restored
            self.dict_set = set(self.final_dict.keys())


        else:
            os.system('cp %s %s'%(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"),os.path.join(self.output_dir,"dict_dir","aaa_dict_for_use")))


    def filter_corpus_by_finaldict(self):
        os.makedirs(os.path.join(self.output_dir,"final_train"))
        # final filter corpus by final_dict
        self.process_file_in_dir(self.filter_corpus_by_dict,os.path.join(self.output_dir,"for_train"),os.path.join(self.output_dir,"final_train"))


    
    def generate_phone_dict(self,dict_file,out_dir):
        if os.path.exists("./xtts20_for_asr/bin_predict/frontinfo.txt"):
            os.remove("./xtts20_for_asr/bin_predict/frontinfo.txt")

        if not os.path.exists("./xtts20_for_asr/bin_predict/wav_outdir"):
            os.makedirs("./xtts20_for_asr/bin_predict/wav_outdir")
        
        if os.path.exists(dict_file):
            if num2LagDict[self.language] == "english":
                os.environ['LD_LIBRARY_PATH'] = os.path.abspath('fst_lib/')
                os.system("phonetisaurus/bin/phonetisaurus-g2pfst --model=predict_for_english/model.20200118.min.fst --nbest=2 --beam=10000 --thresh=99.0 --accumulate=false --pmass=0.0 --nlog_probs=true --wordlist=%s >%s"%(os.path.abspath(dict_file),os.path.join(out_dir,"aaa_dict_phone_map")))
                infile = open(os.path.join(out_dir,"aaa_dict_phone_map"),"r",encoding='utf-8')
                final_dict_file = open(os.path.join(out_dir,"aaa_dict_phone"),"w",encoding='utf-8')
                while True:
                    inline = infile.readline()
                    if not inline:
                        print(inline)
                        break
                    parts = inline.strip().split("\t")
                    if len(parts) != 3:
                        continue
                    word = parts[0].strip()
                    phones_list = parts[-1].strip().split()
                    print(word)
                    print(phones_list)
                    phones = ""
                    for phone in phones_list:
                        striped_phone = phone.strip()
                        if striped_phone != "":
                            if striped_phone !="sp" and striped_phone !="sil":
                                phones = phones + "En_"+striped_phone + " "
                            else:
                                phones = phones + striped_phone + " "
                    
                    final_dict_file.write(word.strip()+'\t'+phones.strip()+'\n')
                infile.close()
                final_dict_file.close()
                return

            os.environ['TTSKNL_DOMAIN'] = os.path.abspath('xtts20_for_asr/bin_predict/')
            os.environ['LD_LIBRARY_PATH'] = os.path.abspath('xtts20_for_asr/bin_predict/')
            os.environ['OMP_NUM_THREADS'] = '5'
            os.environ['XTTS_VERSION'] = "Travis"
            #希伯来语打包时需要注释掉
            os.system("cd xtts20_for_asr/bin_predict/ && ./ttsSample -l libttsknl.so -v \"%s\" -x 1 -i \"%s\" -o wav_outdir/ -m 1 -f 1 -g 1 > xtts_predict.log"%(ttsdict[num2LagDict[self.language]] , os.path.abspath(dict_file)))

            if os.path.exists("./xtts20_for_asr/bin_predict/frontinfo.txt"):
                infile =io.open("./xtts20_for_asr/bin_predict/frontinfo.txt","r",encoding='utf-8') if sys.version_info[0]==2 else open("./xtts20_for_asr/bin_predict/frontinfo.txt","r",encoding='utf-8')
                dictfile =io.open(dict_file,"r",encoding='utf-8') if sys.version_info[0]==2 else open(dict_file,"r",encoding='utf-8')
                mapfile =io.open(os.path.join(out_dir,"aaa_dict_phone_map"),"w",encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(out_dir,"aaa_dict_phone_map"),"w",encoding='utf-8')
                final_dict_file =io.open(os.path.join(out_dir,"aaa_dict_phone"),"w",encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(out_dir,"aaa_dict_phone"),"w",encoding='utf-8')
                while True:
                    word=''
                    phone=''
                    dict_word = dictfile.readline()
                    inline = infile.readline()
                    if not inline:
                        print(inline)
                        break
                    if not self.use_old_phone_system:
                        word,phone = parse_word_phone(inline.strip())
                    else:
                        word,phone_block = parse_word_phone_block(inline.strip())
                        phone = self.phone_map.get_map_phone(phone_block)
                    if len(word) > MAX_WORD_LENGTH:
                        continue
                    if len(phone)==0:
                        continue
                    mapfile.write(word+'\t'+dict_word.strip()+'\n')
                    final_dict_file.write(dict_word.strip()+'\t'+" ".join(phone)+'\n')
                final_dict_file.close()
                dictfile.close()
                mapfile.close()
                infile.close()

    def get_dict_path(self):
        return os.path.join(self.output_dir,"dict_dir","aaa_dict_for_use")
                    

    def get_dict_from_corpus(self,corpus,outfile,outfile_oov):
        '''
        outfile.write()
        outfile_oov.write()
        outfile_oov and outfile for every file dict allow and filter log not use for now
        '''

        self.word_counts.update(collections.Counter(corpus.split()))  


    
    def expand_corpus(self,corpus,outfile,outfile_oov):
        temp_list = list(corpus)
        index = 0
        while "<" in temp_list[index::]:
            index = temp_list.index("<", index)
            if index !=0:

                if not temp_list[index-1] == '\'':
                    temp_list.insert(index," ")
                    index = index + 1
            index = index + 1
        index = 0
        while ">" in temp_list[index::]:
            index = temp_list.index(">", index)
            if index !=len(temp_list)-1:
                if not temp_list[index+1] == '\'':
                    temp_list.insert(index+1," ")
            index = index + 1
        corpus = "".join(temp_list)

        isleagal = True
        pattern = r'<.*?>'
        matches = re.findall(pattern,corpus)
        if len(matches)==0:
            outfile.write(corpus + '\n')
            return
        else:
            slot = re.findall(r'<(.*?)>',matches[0])[0]
            if slot in self.allslot.keys():
                templist = random.sample(self.allslot[slot], min(self.slot_argument[slot],len(self.allslot[slot]))) if slot in self.slot_argument.keys() else self.allslot[slot]
                for elem in templist:
                    self.expand_corpus(corpus.replace(matches[0],elem,1),outfile,outfile_oov)
                isleagal = True
            else:
                isleagal = False
        if not isleagal:
            outfile_oov.write(corpus+'\n')
    
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
                # self.allslot[file].remove(" ")
                # self.allslot[file].remove("")
                f.close()
    
    def replace_step(self,corpus):
        return self.pattern.replace(corpus)
        # if self.replace_list and self.pattern:
        #     return self.pattern.sub(lambda m: self.replace_list[m.group(1)], corpus)
        # return corpus
    
    def delete_invalid_char(self,word,left=False,right=False):
        word_list = []
        for one_word in word.split():
            if one_word=="" or one_word == " ":
                continue
            if left:
                while (len(one_word)>0 and one_word[0] in self.begin_notallow):
                    one_word = one_word[1::]
            if right:
                while (len(one_word)>0 and one_word[-1] in self.end_notallow):
                    one_word = one_word[:-1]
            word_list.append(one_word)
        if len(word_list)==0:
            return ""
        word = " ".join(word_list)
        if word =="":
            return ""
        return word

    def filter_corpus_by_char(self,corpus,outfile,outfile_oov,ispost = False):
        # ******replace_step*******
        corpus = self.replace_step(corpus)

 
        templist = corpus.split(" ")
        output_line=""
        for index, word in enumerate(templist):
            if(word == ' ' or word == ''):
                continue
            
            # lower the first word
            word = word.lower()
            if word not in self.allow_word:

                wordset = set(word)
                allow_char_set = None
                if ispost:
                    allow_char_set = self.allow_list.union(post_set)
                else:
                    allow_char_set = self.allow_list



                if not wordset.issubset(allow_char_set):
                    # outfile_oov.write("before_filter:\t%s\n"%word)
                    notallowset = wordset.difference(allow_char_set)
                    outfile_oov.write(word+'\t')
                    for character in notallowset:
                        outfile_oov.write(character+r"(unicode:"+str(ord(character))+r")"+'\t')
                        word = word.replace(character,' ')
                    # outfile_oov.write("after_filter:\t%s\n"%word)
                    # for character in notallowset:
                    #     outfile_oov.write(character+"\t")
                    outfile_oov.write("\n")

                word = self.delete_invalid_char(word,True,True)

            output_line = output_line+word.strip()+" "
        output_line = self.replace_step(output_line.strip())
        outfile.write(output_line.strip() + '\n')
    
    def filter_corpus_by_dict(self,corpus,outfile,outfile_oov):
        word_set = set(corpus.casefold().split())
        # print(word_set)
        if word_set.issubset(self.dict_set):
            outfile.write(corpus +'\n')
        else:
            outfile_oov.write(corpus +':\t'+','.join(word_set.difference(self.dict_set))+'\n')

    def process_file_in_dir(self,func,path_in,path_out):
        p = Pool(10)
        for root ,dirs,files in os.walk(path_in):
            for file in files:
                if file.startswith("oov_"):
                    continue
                p.apply_async(self.mutil_thread_func, args=(func,root,file,path_in,path_out))
        p.close()
        p.join()
        # processes = []
        # for root ,dirs,files in os.walk(path_in):
        #     for file in files:
        #         if file.startswith("oov_"):
        #             continue
        #         processes.append(Process(target=self.mutil_thread_func,args=(func,root,file,path_in,path_out,)))

        # for p in processes:
        #     p.start()
        # for p in processes:
        #     p.join()
        #         p.apply_async(self.mutil_thread_func, args=(func,root,file,path_in,path_out))
        # p.close()
        # p.join()
                
    
    def mutil_thread_func(self,func,root,file,path_in,path_out):
        encoding='utf-8'
        # with open(os.path.join(root,file), 'rb') as checkcode:
        #     encoding = chardet.detect(checkcode.read())['encoding']
        print("\none thread begin!!!!!!")
        infile_path = os.path.join(path_in,file)
        outfile_path = os.path.join(path_out,file)
        outfileoov_path = os.path.join(path_out,'oov_'+file)
        print("process:"+infile_path+'\tencoding:'+encoding+'\n')
        infile = io.open(infile_path, mode='r',encoding=encoding) if sys.version_info[0]==2 else open(infile_path, mode='r',encoding=encoding)
        outfile = filewriter(outfile_path, mode='w',encoding='utf-8')
        outfile_oov = filewriter(outfileoov_path, mode='w',encoding='utf-8')
        # for inline in tqdm(infile):
        while True:
            inline = infile.readline()
            if not inline:
                break
            func(inline.strip(), outfile, outfile_oov)
        self.collect_word(outfile,outfile_oov)


        infile.close()
        outfile.close()
        outfile_oov.close()

    def collect_word(self,outfile,outfile_oov):
        for word,count in self.word_counts.most_common():
            if word !='':
                if word.casefold() not in self.final_dict.keys():
                    outfile_oov.write(word+'\t'+str(count)+'\n')
                outfile.write(word+'\t'+str(count)+'\n')


class italy_Corpus_process(Corpus_process):
    def set_begin_end_notallow(self):
        self.begin_notallow.add("-")
        self.begin_notallow.add(" ")
        
        self.end_notallow.add("-")
        self.end_notallow.add(" ")

class french_Corpus_process(Corpus_process):
    def set_begin_end_notallow(self):
        self.begin_notallow.add("\'")
        self.begin_notallow.add("-")
        self.begin_notallow.add(" ")
        

        self.end_notallow.add("-")
        self.end_notallow.add(" ")

def get_corpus_process(language,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument, dict_base, dict_max, predict_phone_for_new,use_old_phone_system,is_yun):
    class_name = "Corpus_process"
    if language in num2LagDict.keys():
        class_name = num2LagDict[language]+"_Corpus_process"
    
    if class_name in global_symbols:
        return global_symbols[class_name](language,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument, dict_base, dict_max, predict_phone_for_new,use_old_phone_system,is_yun)
    else:
        return Corpus_process(language,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument, dict_base, dict_max, predict_phone_for_new,use_old_phone_system,is_yun)
    



class G_Corpus_process(Corpus_process):

    def process_file_in_dir(self,func,path_in,path_out):
        for root ,dirs,files in os.walk(path_in):
            for file in files:
                if file.startswith("oov_"):
                    continue
                self.mutil_thread_func(func,root,file,path_in,path_out)

    def collect_word(self,outfile,outfile_oov):
        if len(self.word_counts)==0:
            return

        used_set = set()
        for word,count in self.word_counts.most_common():
            if word !='':
                matches =re.findall(r'<.*?>',word)
                if len(matches) == 0:
                    if word.casefold() not in self.final_dict.keys():
                        outfile_oov.write(word+'\t'+str(count)+'\n')
                    outfile.write(word+'\t'+str(count)+'\n')
                else:

                    left = re.findall(r'(\S*)<',word)
                    right = re.findall(r'>(\S*)',word)
                    middle = re.findall(r'<(.*?)>',word)
                    if middle[0] not in self.allslot_begin_end.keys():
                        self.allslot_begin_end[middle[0]] = set()
                        self.allslot_begin_end[middle[0]].add(slot_begin_end("",""))

                    self.allslot_begin_end[middle[0]].add(slot_begin_end(left[0],right[0]))

                    used_set.add(middle[0])
        

        # print(used_set)
        # print(self.allslot_begin_end)
        # exit()

        if not os.path.exists(os.path.join(self.output_dir,"slot_final_train")):
            os.makedirs(os.path.join(self.output_dir,"slot_final_train"))
        


        input_num = {key:0 for key in self.allslot.keys()}
        visit = {key:False for key in self.allslot.keys()}

        for node,arc_set in self.content_net.items():
            for node_end in arc_set:
                input_num[node_end] = input_num[node_end]+1


        queue = []
        for slot,num in input_num.items():
            if num==0 and (slot in used_set):
                queue.append(slot)

        node_count = 0
        while len(queue) !=0:
            one_slot = queue.pop(0)
            if not visit[one_slot]:
                oov_slot =set()
                slot_oov_file = open(os.path.join(self.output_dir,"slot_final_train","oov_"+one_slot), mode='a',encoding='utf-8')
                for slot_iteam in self.allslot[one_slot]:
                    for item in self.allslot_begin_end[one_slot]:
                        joint_str = item.begin+slot_iteam+item.end
                        word_set = set(joint_str.split())
                        all_lower_set = {word_item.casefold() for word_item in word_set}
                        out_word = {word_item for word_item in all_lower_set if ((word_item not in self.dict_set) and (len(re.findall(r'<(.*?)>',word_item))==0)) }
                        if len(out_word) == 0:
                            for temp_word in word_set:
                                if (len(re.findall(r'<(.*?)>',temp_word))==0):
                                    outfile.write(temp_word+'\t'+str(1)+'\n')
                        else:
                            slot_oov_file.write(joint_str +':\t'+','.join(out_word)+'\n')
                            for temp_word in word_set:
                                if (temp_word.casefold() not in self.dict_set) and (len(re.findall(r'<(.*?)>',temp_word))==0):
                                    outfile_oov.write(temp_word+'\t'+str(1)+'\n')
                            oov_slot.add(slot_iteam)
                                
                self.allslot[one_slot] = [item for item in self.allslot[one_slot] if item not in oov_slot]
                visit[one_slot] = True
                slot_oov_file.close()

            for node_end in self.content_net[one_slot]:
                if not visit[node_end]:
                    queue.append(node_end)

        
                    # oov_slot = set()
                    # if not ((slot_name not in self.allslot.keys()) or len(self.allslot[slot_name])==0):
                        
                    #     for slot_iteam in self.allslot[slot_name]:
                    #         for item in self.allslot_begin_end[slot_name]:
                    #             joint_str = item.begin+slot_iteam+item.end
                    #             word_set = set(joint_str.split())
                    #             all_lower_set = {word_item.casefold() for word_item in word_set}
                    #             out_word = all_lower_set - self.dict_set
                    #             if len(out_word) == 0:
                    #                 for temp_word in word_set:
                    #                     outfile.write(temp_word+'\t'+str(count)+'\n')
                    #             else:
                    #                 flag = True
                    #                 for one_out in out_word:
                    #                     if len(re.findall(r'<(.*?)>',one_match)) == 0:
                    #                         flag = False
                    #                         break
                                    
                    #                 if flag:
                    #                     for temp_word in word_set:
                    #                         outfile.write(temp_word+'\t'+str(count)+'\n')
                    #                 else:
                    #                     slot_oov_file.write(replaced_word +':\t'+','.join(word_set.difference(self.dict_set))+'\n')
                    #                     for temp_word in word_set:
                    #                         if temp_word.casefold() not in self.dict_set:
                    #                             outfile_oov.write(temp_word+'\t'+str(count)+'\n')
                    #                     oov_slot.add(slot_iteam)
                                    
                    #     self.allslot[slot_name] = [item for item in self.allslot[slot_name] if item not in oov_slot]

        self.word_counts.clear()
        return

    def filter_corpus_to_fortrain(self):
        os.makedirs(os.path.join(self.output_dir,"shuofa_for_train"))
        os.makedirs(os.path.join(self.output_dir,"slot_for_train"))
        #  filter raw corpus by allowchar to for_train dir
        self.process_file_in_dir(self.filter_corpus_by_char,os.path.join(self.output_dir,"slot"),os.path.join(self.output_dir,"slot_for_train"))
        self.process_file_in_dir(self.filter_corpus_by_char,os.path.join(self.output_dir,"shuofa"),os.path.join(self.output_dir,"shuofa_for_train"))
       
        
        oov_set = set()
        for root ,dirs,files in os.walk(os.path.join(self.output_dir,"shuofa_for_train")):
            for file in files:
                if file.startswith('oov_'):
                    file_oov = open(os.path.join(self.output_dir,"shuofa_for_train",file), mode='r',encoding='utf-8')# oov dict from for_train
                    for line in file_oov.readlines():
                        oov_set.add(line)
                    file_oov.close()


        gather_oov = open(os.path.join(self.output_dir,"shuofa_for_train","oov_gather_oov"), mode='w',encoding='utf-8')# oov dict from for_train
        for line in oov_set:
            gather_oov.write(line)
        gather_oov.close()

        oov_set.clear()
        for root ,dirs,files in os.walk(os.path.join(self.output_dir,"slot_for_train")):
            for file in files:
                if file.startswith('oov_'):
                    file_oov = open(os.path.join(self.output_dir,"slot_for_train",file), mode='r',encoding='utf-8')# oov dict from for_train
                    for line in file_oov.readlines():
                        oov_set.add(line)
                    file_oov.close()


        gather_oov = open(os.path.join(self.output_dir,"slot_for_train","oov_gather_oov"), mode='w',encoding='utf-8')# oov dict from for_train
        for line in oov_set:
            gather_oov.write(line+'\n')
        gather_oov.close()

    def get_dict_from_fortrain(self):
        self.getallslot()
        self.check_slot_circle()
        os.makedirs(os.path.join(self.output_dir,"dict_dir"))
        # count all word in for_train 
        # self.process_file_in_dir(self.get_dict_from_corpus,os.path.join(self.output_dir,"slot_for_train"),os.path.join(self.output_dir,"dict_dir"))
        self.process_file_in_dir(self.get_dict_from_corpus,os.path.join(self.output_dir,"shuofa_for_train"),os.path.join(self.output_dir,"dict_dir"))

        oov_count = collections.Counter()
        dict_count = collections.Counter()
        for root ,dirs,files in os.walk(os.path.join(self.output_dir,"dict_dir")):
            for file in files:
                if file.startswith('oov_'):
                    file_oov = io.open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8')# oov dict from for_train
                    for line in file_oov.readlines():
                        oov_count.update(collections.Counter({line.split('\t')[0]:int(line.split('\t')[1])}))
                    file_oov.close()
                else:
                    file = io.open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir",file), mode='r',encoding='utf-8')# oov dict from for_train
                    for line in file.readlines():
                        dict_count.update(collections.Counter({line.split('\t')[0]:int(line.split('\t')[1])}))
                    file.close()
    
        # # write all dict word in new_dict file for predict phone
        outfile = io.open(os.path.join(self.output_dir,"dict_dir","aaa_all_word"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_all_word"), mode='w',encoding='utf-8') #dict from for_train
        file_oov = io.open(os.path.join(self.output_dir,"dict_dir","aaa_oov_base_dict"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_oov_base_dict"), mode='w',encoding='utf-8')# oov dict from for_train
        base_dict_file = io.open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict"), mode='w',encoding='utf-8')# oov dict from for_train

        if self.is_yun ==1 or self.is_yun ==2 :
            base_dict_file.write(u'<s>\t<s>\n')
            base_dict_file.write(u'</s>\t</s>\n')
        else:
            base_dict_file.write(u'<s>\tsil\n')
            base_dict_file.write(u'</s>\tsil\n')
         # deal in set word
        for word,count in dict_count.most_common():
            lower_word = word.casefold()
            if lower_word in self.dict_set:
                #get all word has 
                self.all_dict_set.add(word)
                for phone in self.final_dict[lower_word]:
                    base_dict_file.write(word+'\t'+phone+'\n')
            if word !='':
                outfile.write(word+'\n')
        # deal out set word
        for word,count in oov_count.most_common():
            if word !='':
                file_oov.write(word+'\n')

        base_dict_file.close()
        outfile.close()
        file_oov.close()

        # print all dict_phone processed data
        dict_for_use = io.open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"), mode='w',encoding='utf-8')# oov dict from for_train
        if self.is_yun ==1 or self.is_yun ==2 :
            dict_for_use.write(u'<s>\t<s>\n')
            dict_for_use.write(u'</s>\t</s>\n')
        else:
            dict_for_use.write(u'<s>\tsil\n')
            dict_for_use.write(u'</s>\tsil\n')
        for word in self.all_dict_set:
            for phone in self.final_dict[word.casefold()]:
                dict_for_use.write(word+'\t'+phone+'\n')
        dict_for_use.close()
        

        if self.predict_phone_for_new:

            print("\n\npredict dict_to_phone syms begin")
            self.generate_phone_dict(os.path.join(self.output_dir,"dict_dir","aaa_oov_base_dict"),os.path.join(self.output_dir,"dict_dir"))
            print("predict dict_to_phone syms end")

            # cat base and oov
            os.system('cat %s %s > %s'%(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"),os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),os.path.join(self.output_dir,"dict_dir","aaa_dict_for_use")))
           
            # gather predicted word and base word which has phone
            if os.path.join(self.output_dir,"dict_dir","aaa_dict_phone") is not None and os.path.exists(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone")):
                dictfile =io.open(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),"r",encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"dict_dir","aaa_dict_phone"),"r",encoding='utf-8')
                for line in dictfile.read().splitlines():
                    dict_iteam, phone_iteam = line.split('\t')
                    self.all_dict_set.add(dict_iteam)
                    lower_dict = dict_iteam.casefold()
                    if lower_dict not in self.final_dict.keys():
                        self.final_dict[lower_dict]=set()
                    self.final_dict[lower_dict].add(phone_iteam.strip())
                dictfile.close()
            # update all word restored
            self.dict_set = set(self.final_dict.keys())


        else:
            os.system('cp %s %s'%(os.path.join(self.output_dir,"dict_dir","aaa_base_dict_cumulation"),os.path.join(self.output_dir,"dict_dir","aaa_dict_for_use")))


    def filter_corpus_by_finaldict(self):
        os.makedirs(os.path.join(self.output_dir,"shuofa_final_train"))
        if not os.path.exists(os.path.join(self.output_dir,"slot_final_train")):
            os.makedirs(os.path.join(self.output_dir,"slot_final_train"))
        # final filter corpus by final_dict
        # self.process_file_in_dir(self.filter_corpus_by_dict,os.path.join(self.output_dir,"slot_for_train"),os.path.join(self.output_dir,"slot_final_train"))
        
        self.process_file_in_dir(self.filter_corpus_by_dict,os.path.join(self.output_dir,"shuofa_for_train"),os.path.join(self.output_dir,"shuofa_final_train"))
        for slot in self.allslot.keys():
            outfile = io.open(os.path.join(self.output_dir,"slot_final_train",slot), mode='w',encoding='utf-8') if sys.version_info[0]==2 else open(os.path.join(self.output_dir,"slot_final_train",slot), mode='w',encoding='utf-8')
            for iteam in self.allslot[slot]:
                outfile.write(iteam+"\n")
            outfile.close()

    
    def get_dict_from_corpus(self,corpus,outfile,outfile_oov):
        '''
        outfile.write()
        outfile_oov.write()
        outfile_oov and outfile for every file dict allow and filter log not use for now
        '''

        self.word_counts.update(collections.Counter(re.split(r"\[|\]|\(|\)|\|| ",corpus)))  



    def corpus_process(self):
        print("\n\ngather_corpus_to_raw_begin:\n")
        self.gather_corpus_to_raw()
        print(self.language)
        if num2LagDict[self.language] in need_split:
            self.split_fuction = self.get_split_function()
            self.split_corpus()
        print("\n\nfilter_corpus_to_fortrain_begin:\n")
        self.filter_corpus_to_fortrain()
        print("\n\nget_dict_from_fortrain_begin:\n")
        self.get_dict_from_fortrain()
        print("\n\nfilter_corpus_by_finaldict_begin:\n")
        self.filter_corpus_by_finaldict()

    
    def split_corpus(self):
        os.rename(os.path.join(self.output_dir,"shuofa"),os.path.join(self.output_dir,"shuofa_before_split"))
        os.rename(os.path.join(self.output_dir,"slot"),os.path.join(self.output_dir,"slot_before_split"))
        os.makedirs(os.path.join(self.output_dir,"shuofa"))
        os.makedirs(os.path.join(self.output_dir,"slot"))
        self.process_file_in_dir(self.split_fuction.split,os.path.join(self.output_dir,"slot_before_split"),os.path.join(self.output_dir,"slot"))
        self.process_file_in_dir(self.split_fuction.split,os.path.join(self.output_dir,"shuofa_before_split"),os.path.join(self.output_dir,"shuofa"))
        
    
    def getallslot(self):
        for root ,dirs,files in os.walk(os.path.join(self.output_dir,"slot_for_train")):
            for file in files:
                if file.startswith("oov_"):
                    continue
                encoding='utf-8'
                # with open(os.path.join(root,file),'rb') as checkcode:
                #     encoding = chardet.detect(checkcode.read())['encoding']
                f = open(os.path.join(root,file), mode='r',encoding=encoding)
                print(os.path.join(root,file))
                self.allslot[file] = list(dict.fromkeys([item.strip() for item in f.readlines() if (item.strip()!=" " and item.strip()!="")]))
                # self.allslot[file].remove(" ")
                # self.allslot[file].remove("")
                f.close()
    
    def add_blank_in_slot(slef,corpus):
        temp_list = list(corpus)
        index = 0
        while "<" in temp_list[index::]:
            index = temp_list.index("<", index)
            if index !=0:

                if not temp_list[index-1] == '\'':
                    temp_list.insert(index," ")
                    index = index + 1
            index = index + 1
        index = 0
        while ">" in temp_list[index::]:
            index = temp_list.index(">", index)
            if index !=len(temp_list)-1:
                if not temp_list[index+1] == '\'':
                    temp_list.insert(index+1," ")
            index = index + 1
        templist = "".join(temp_list)
        return templist
    
    def filter_word_with_slot(self,word,outfile,outfile_oov):
        left_index = word.find("<")
        right_index = word.rfind(">")
        leftstr = self.filter_word(word[0:left_index],outfile,outfile_oov,True)
        rightstr = self.filter_word(word[right_index+1::],outfile,outfile_oov,False,True)

        return leftstr.lower()+word[left_index:right_index+1]+rightstr.lower()
    
    def filter_word(self,word,outfile,outfile_oov,left = False,right = False):
        # lower the first word
        word = word.lower()
        if word not in self.allow_word:
            wordset = set(word)
            if not wordset.issubset(self.allow_list):
                # outfile_oov.write("before_filter:\t%s\n"%word)
                notallowset = wordset.difference(self.allow_list)
                outfile_oov.write(word+'\t')
                for character in notallowset:
                    outfile_oov.write(character+r"(unicode:"+str(ord(character))+r")"+'\t')
                    word = word.replace(character,' ')
                # outfile_oov.write("after_filter:\t%s\n"%word)
                # for character in notallowset:
                #     outfile_oov.write(character+"\t")
                outfile_oov.write("\n")
            word = self.delete_invalid_char(word,left,right)
        return word
    
    def filter_step(self,word,outfile,outfile_oov):
        if(word == ' ' or word == ''):
            return ""
        
        if len(re.findall(r'<.*?>',word))==1:
            word = self.filter_word_with_slot(word,outfile,outfile_oov)
            return word
            
        else:
            return self.filter_word(word,outfile,outfile_oov,True,True)

    def filter_corpus_by_char(self,corpus,outfile,outfile_oov):
        corpus = self.replace_step(corpus)

        lineset = set(corpus)
        if len(lineset.intersection(regular_char_set)) !=0 :

            output_line=""
            anbf_character = {"[","]","(",")","|"," "}
            word_need_filter = ""
            output_line = ""
            for character in corpus:
                if character in anbf_character:
                    word_after_filter = self.filter_step(word_need_filter,outfile,outfile_oov)
                    output_line = output_line + word_after_filter + character
                    word_need_filter = ""
                else:
                    word_need_filter = word_need_filter + character

            word_after_filter = self.filter_step(word_need_filter,outfile,outfile_oov)
            output_line = output_line + word_after_filter
            word_need_filter = ""

            output_line = self.replace_step(output_line.strip())
            outfile.write(output_line.strip() + '\n')
        
        else:
            outfile.write(self.replace_step(" ".join([self.filter_step(item.strip(),outfile,outfile_oov) for item in corpus.split(" ") if item.strip()])) + "\n")

    
    def filter_corpus_by_dict(self,corpus,outfile,outfile_oov):
        #remve all <.*>

        pattern = r'<.*?>'
        got_oov = False
        oov_string = []
        for word in set(re.split(r"\[|\]|\(|\)|\|| ",corpus)):
            if word == "" or word == " ":
                continue
            matches = re.findall(pattern,word)
            if len(matches)==0:
                if word.casefold() not in self.dict_set:
                    oov_string.append(word)
                    got_oov = True
            else:
                continue
                
        if not got_oov:
            outfile.write(corpus +'\n')
        else:
            outfile_oov.write(corpus +':\t'+", ".join(oov_string) + "\n")
    
    def get_slot_path(self):
        return os.path.join(self.output_dir,"slot_final_train")

    def read_slot_and_expand(self):
        return



class G_italy_Corpus_process(G_Corpus_process):
    def set_begin_end_notallow(self):
        self.begin_notallow.add("-")
        self.begin_notallow.add(" ")
        
        self.end_notallow.add("-")
        self.end_notallow.add(" ")

class G_french_Corpus_process(G_Corpus_process):
    def set_begin_end_notallow(self):
        self.begin_notallow.add("\'")
        self.begin_notallow.add("-")
        self.begin_notallow.add(" ")
        

        self.end_notallow.add("-")
        self.end_notallow.add(" ")


def get_G_corpus_process(language,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument, dict_base, dict_max, predict_phone_for_new,use_old_phone_system,is_yun):
    class_name = "G_Corpus_process"
    if language in num2LagDict.keys():
        class_name = "G_"+num2LagDict[language]+"_Corpus_process"
    
    if class_name in global_symbols:
        return global_symbols[class_name](language,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument, dict_base, dict_max, predict_phone_for_new,use_old_phone_system,is_yun)
    else:
        return G_Corpus_process(language,excel_path, slot_path, shuofa_path, train_corpus, output_dir, expand_argument, dict_base, dict_max, predict_phone_for_new,use_old_phone_system,is_yun)
   

class Corpus_split:
    def split(self,inline,outfile,outfile_oov):
        return

class Corpus_split_Japan(Corpus_split):
    def split(self, inline,outfile,outfile_oov):
        doc = nlp(inline)
        nlp_mask_line = ' '.join('{word}/{tag}'.format(word=t.orth_, tag=t.pos_) for t in doc)
        outfile_oov.write(nlp_mask_line)
        inline = nlp_mask_line
        n_list=["/NOUN","/SCONJ","/ADP","/AUX","/VERB","/PROPN","/ADJ","/ADV","/CONJ","/DET","/INTJ","/NUM","/PART","/PRON","/PUNCT","/SYM","/X","/CCONJ","/SPACE"]
        for mask in n_list:
            inline = inline.replace(mask,"")
        outfile.write(inline +'\n')
        return
class Corpus_split_Thai(Corpus_split):
    def split(self, inline,outfile,outfile_oov):
        
        word_list = subword_tokenize(inline, engine="dict")
        label_tokenized = ' '.join(word_list)
        label_tokenized = ' '.join(label_tokenized.split())

        pattern = r'<.*?>'
        matches = re.findall(pattern,label_tokenized)
        for one_match in matches:
            before_split = one_match.replace(" ","")
            label_tokenized = label_tokenized.replace(one_match,before_split,1)
        if " ๆ " in label_tokenized or label_tokenized.endswith(" ๆ"):
            label_tokenized = label_tokenized.replace(" ๆ","ๆ")
        if " ร์ " in label_tokenized or label_tokenized.endswith(" ร์"):
            label_tokenized = label_tokenized.replace(" ร์","ร์")
        if " น์ " in label_tokenized or label_tokenized.endswith(" น์"):
            label_tokenized = label_tokenized.replace(" น์","น์")
        if " ํา " in label_tokenized or label_tokenized.endswith(" ํา"):
            label_tokenized = label_tokenized.replace(" ํา","ํา")
        if " ต์ " in label_tokenized or label_tokenized.endswith(" ต์"):
            label_tokenized = label_tokenized.replace(" ต์","ต์")
        if " ค์ " in label_tokenized or label_tokenized.endswith(" ค์"):
            label_tokenized = label_tokenized.replace(" ค์","ค์")
        if " ซ์ " in label_tokenized or label_tokenized.endswith(" ซ์"):
            label_tokenized = label_tokenized.replace(" ซ์","ซ์")
        outfile.write(label_tokenized +'\n')
        return