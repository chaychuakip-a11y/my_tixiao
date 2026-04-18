#coding=utf-8
import random
import pdb
import os
import io
import sys
import re
from multiprocessing import Pool
import time
import copy

from functools import wraps

# 定义计时装饰器
def timer(func):
    @wraps(func)  # 保留原函数的名称和文档字符串
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()  # 开始时间
        result = func(*args, **kwargs)    # 执行原函数
        end_time = time.perf_counter()    # 结束时间
        # 打印执行时间（函数名 + 时间）
        print(f"函数 {func.__name__} 执行时间：{end_time - start_time:.6f} 秒")
        return result  # 返回原函数的结果
    return wrapper

class net_Arc:
    def __init__(self,endnode,input_output,weight):
        self.endnode = endnode
        self.input_output = input_output
        self.weight = weight
    def arc_info(self):
        return str(self.endnode) + "\t" +  self.input_output + "\t" +  self.input_output + "\t" + str(self.weight)

class net_node:
    def __init__(self,id,node=None,offset = 0,is_start=False,end_node=-1,slot_begin="",slot_end=""):
        self.id = id
        self.arc_list = []
        self.slot_node = {}
        self.symbol = set()
        if node:
            for arc in node.arc_list:
                inputoutput = arc.input_output
                if is_start:
                    inputoutput = slot_begin+inputoutput
                if end_node == arc.endnode:
                    inputoutput = inputoutput+slot_end
                self.arc_list.append(net_Arc(arc.endnode+offset,inputoutput,arc.weight))
                if inputoutput not in self.symbol:
                    self.symbol.add(inputoutput)
                matches = re.findall(r'<.*?>',inputoutput)
                if len(matches) > 0 and inputoutput!= "<s>" and inputoutput!= "</s>":
                    if inputoutput not in self.slot_node.keys():
                        self.slot_node[inputoutput] = set()
                    self.slot_node[inputoutput].add((self.id,arc.endnode+offset))
    def add_arc(self,endnode,input_output,weight):
        self.arc_list.append(net_Arc(endnode,input_output,weight))
        if input_output not in self.symbol:
            self.symbol.add(input_output)
        matches = re.findall(r'<.*?>',input_output)
        if len(matches) > 0 and input_output!= "<s>" and input_output!= "</s>":
            if input_output not in self.slot_node.keys():
                self.slot_node[input_output] = set()
            self.slot_node[input_output].add((self.id,endnode))
    def remove_arc(self,endnode,input_output):
        for i in range(len(self.arc_list)-1, -1, -1):
            if (self.arc_list[i].endnode==endnode and self.arc_list[i].input_output==input_output):  
                del self.arc_list[i]
        matches = re.findall(r'<.*?>',input_output)
        if len(matches) > 0 and input_output!= "<s>" and input_output!= "</s>":
            if input_output not in self.slot_node.keys():
                self.slot_node[input_output] = set()
            self.slot_node[input_output].remove((self.id,endnode))
    def arc_print(self):
        arc_set = list()
        if len(self.arc_list)==0:
            arc_set.append(str(self.id))
            return arc_set
        for arc in self.arc_list:
            arc_set.append(str(self.id) + "\t" + arc.arc_info())
        return arc_set

class regular_net:
    def __init__(self,name,isarc,score):
        self.name = name
        self.isarc = isarc
        self.score = score
        self.brackets = {"[":"]","(":")","{":"}"}
        self.net_arr = []
        self.slot_node = {}
        self.symbol_list = set()
        self.start_node = self.get_new_node()
        self.end_node = self.get_new_node()
    @timer
    def all_symbol_list(self):
        if len(self.symbol_list)==0:
            self.symbol_list.add('-')
            for node in self.net_arr:
                for arc in node.arc_list:
                    if arc.input_output not in self.symbol_list:
                        self.symbol_list.add(arc.input_output)

    def node_num(self):
        return len(self.net_arr)
        
    def is_one_brackets_unit(self,line):
        line = line.strip()
        if line[0] not in self.brackets.keys():
            return False
        stack=list()
        for index ,character in enumerate(line):
            # 左括号
            if character in self.brackets.keys():
                stack.append(character)
            else:
                # 右括号
                if character in self.brackets.values():
                    stack.pop()
                    if len(stack) == 0 :
                        if index == len(character)-1:
                            return True
                # 非括号情况
                else:
                    # 括号外面
                    if len(stack) == 0 :
                        if index != len(character)-1:
                            return False
        if len(stack)!=0:
            return False
        return True
    
    def is_regular(self,line):
        lineset = set(line)
        brackets_set = {"[","]","(",")","{","}","|"}
        if len(lineset.intersection(brackets_set)) !=0 :
            return True
        return False

    def is_optional(self,line):
        if line[0]=="[" and line[-1]=="]":
            return True
        return False

    def add_regular_unit(self,line,begin,end):
        or_flag = False
        valid = True
        if not self.is_regular(line):
            self.net_sent_build(line,begin,end)
            return True
        if self.is_one_brackets_unit(line):
            valid = self.add_regular_unit(line[1:-1],begin,end)
            if not valid:
                return False
            if self.is_optional(line):
                valid = self.add_regular_unit("-",begin,end)
                if not valid:
                    return False
            return True
        
        string_set = list()
        optional_set = list()
        sub_temp = ""
        sub_for_optional = ""
        stack=list()
        
        for character in line:
            # 左括号
            if character in self.brackets.keys():
                if len(stack) == 0 :
                    sub_temp = sub_temp.strip()
                    if sub_temp!= "":
                        string_set.append(sub_temp)
                        sub_temp = ""
                sub_temp = sub_temp + character
                sub_for_optional = sub_for_optional + character
                stack.append(character)
            else:
                # 右括号
                if character in self.brackets.values():
                    sub_temp = sub_temp + character
                    sub_for_optional = sub_for_optional + character
                    stack.pop()
                    if len(stack) == 0:
                        sub_temp = sub_temp.strip()
                        if sub_temp!= "":
                            string_set.append(sub_temp)
                            sub_temp = ""

                # 非括号情况
                else:
                    # 括号外面
                    if len(stack) == 0 :
                        if character=="|":
                            or_flag = True
                            sub_for_optional = sub_for_optional.strip()
                            if sub_for_optional!= "":
                                optional_set.append(sub_for_optional)
                            sub_for_optional = ""
                        else:
                            sub_temp = sub_temp+character
                            sub_for_optional = sub_for_optional + character
                    # 括号里面
                    else:
                        sub_temp = sub_temp + character
                        sub_for_optional = sub_for_optional + character

        sub_temp = sub_temp.strip()
        if sub_temp!= "":
            string_set.append(sub_temp)
            sub_temp = ""
        
        sub_for_optional = sub_for_optional.strip()
        if sub_for_optional!= "":
            optional_set.append(sub_for_optional)

        if or_flag:
            for index,item in enumerate(optional_set):
                valid = self.add_regular_unit(item,begin,end)
                if not valid:
                    return False
        else:
            last_end = begin
            for index,item in enumerate(string_set):
                if index ==0:
                    left = begin
                    if index== len(string_set)-1:
                        right = end
                    else:
                        right = self.get_new_node()
                else:
                    left = last_end
                    if index== len(string_set)-1:
                        right = end
                    else:
                        right = self.get_new_node()
                valid = self.add_regular_unit(item,left,right)
                if not valid:
                    return False
                last_end = right
        return True

    def is_valid(self,line):
        stack=list()
        brackets = {"[":"]","(":")","{":"}","<":">"}
        for character in line:
            # 左括号
            if character in brackets.keys():
                stack.append(character)
            else:
                # 右括号
                if character in brackets.values():
                    if len(stack)==0:
                        return False
                    if character!= brackets[stack[-1]]:
                        return False
                    stack.pop()
        if len(stack)!=0:
            return False
        return True
    
    def net_sent_build(self,line,left,right):
        word_list = [word_item for word_item in line.split(" ") if (word_item!="" and word_item !=" ")]
        last_end = left
        for index,word in enumerate(word_list):
            if index ==0:
                begin = left
                if index== len(word_list)-1:
                    end = right
                else:
                    end = self.get_new_node()
            else:
                begin = last_end
                if index== len(word_list)-1:
                    end = right
                else:
                    end = self.get_new_node()
            
            self.net_arr[begin].add_arc(end,word,self.score)
            if word not in self.symbol_list:
                self.symbol_list.add(word)
            last_end = end

    def get_new_node(self):
        id = len(self.net_arr)
        self.add_node(id)
        return id
    
    def add_node(self,id):
        while id >= len(self.net_arr):
            currentid = len(self.net_arr)
            self.net_arr.append(net_node(currentid))
    @timer
    def get_all_slot_node(self):
        self.slot_node.clear()
        for node in self.net_arr:
            for key,value in node.slot_node.items():
                if key not in self.slot_node.keys():
                    self.slot_node[key] = set(value)
                else:
                    self.slot_node[key].update(value)

    @timer
    def net_expand(self,allslot_net):
        self.get_all_slot_node()
        while len(self.slot_node) > 0:
            temp_slot_node = copy.deepcopy(self.slot_node)


            for slot_item,node_set in temp_slot_node.items():
                slot_begin = ""
                slot_name = ""
                slot_end = ""
                temp_string=""
                flag = False
                for char in slot_item:
                    if char == '<':
                        slot_begin = temp_string
                        temp_string="<"
                    elif char == '>':
                        temp_string=temp_string+char
                        slot_name = temp_string
                        temp_string=""
                    else:
                        temp_string=temp_string+char

                slot_end = temp_string
                # print(len(slot_begin))
                # print(len(slot_name))
                # print(len(slot_end))
                # exit()
                for pair in node_set:
                    offset = len(self.net_arr)
                    if slot_name in allslot_net.keys():
                        subnet_start_node = allslot_net[slot_name].start_node
                        subnet_end_node = allslot_net[slot_name].end_node
                        for index,node in enumerate(allslot_net[slot_name].net_arr):
                            isbegin_node = False
                            if index == subnet_start_node:
                                isbegin_node = True
                            self.net_arr.append(net_node(index+offset,node,offset,isbegin_node,subnet_end_node,slot_begin,slot_end))
                            self.symbol_list.update(self.net_arr[index+offset].symbol)
                            for key,value in self.net_arr[index+offset].slot_node.items():
                                if key not in self.slot_node.keys():
                                    self.slot_node[key] = set(value)
                                else:
                                    self.slot_node[key].update(value)

                        left_node =pair[0]
                        right_node = pair[1]
                        self.net_arr[left_node].remove_arc(right_node,slot_item)
                        self.slot_node[slot_item].remove(pair)
                        self.net_arr[left_node].add_arc(subnet_start_node+offset,"-",0)
                        self.net_arr[subnet_end_node+offset].add_arc(right_node,"-",0)
                        if "-" not in self.symbol_list:
                            self.symbol_list.add("-")
                        if len(self.slot_node[slot_item])==0:
                            del self.slot_node[slot_item]
    
    @timer
    def write_net(self,path):
        outbuffer = list()
        outfile = open(path, mode='w',encoding='utf-8')
        for node in self.net_arr:
            outbuffer.extend(node.arc_print())
            if len(outbuffer)>100000:
                outfile.write("\n".join(outbuffer) + "\n")
                outbuffer.clear()
        outfile.write("\n".join(outbuffer) + "\n")
        outbuffer.clear()
        outfile.close()
    
    @timer
    def reload_net(self,path):
        self.net_arr.clear()
        self.symbol_list.clear()
        infile = open(path, mode='r',encoding='utf-8')
        while True:
            inline = infile.readline()
            if not inline:
                break
            arc_info = [item.strip() for item in inline.strip().split("\t") if item.strip()]
            if len(arc_info) == 0:
                continue
            elif (len(arc_info))==1:
                end = int(arc_info[0])
                self.add_node(end)
            elif (len(arc_info))==2:
                begin = int(arc_info[0])
                end = int(arc_info[1])
                self.add_node(begin)
                self.add_node(end)
                self.net_arr[begin].add_arc(end,"-",0)
                if "-" not in self.symbol_list:
                    self.symbol_list.add("-")
            elif (len(arc_info))==3:
                print("Error",inline)
            elif (len(arc_info))==4:
                begin = int(arc_info[0])
                end = int(arc_info[1])
                input = arc_info[2]
                output = arc_info[3]
                self.add_node(begin)
                self.add_node(end)
                self.net_arr[begin].add_arc(end,input,0)
                if input not in self.symbol_list:
                    self.symbol_list.add(input)
            elif (len(arc_info))==5:
                begin = int(arc_info[0])
                end = int(arc_info[1])
                input = arc_info[2]
                output = arc_info[3]
                weight = float(arc_info[4])
                self.add_node(begin)
                self.add_node(end)
                self.net_arr[begin].add_arc(end,input,weight)
                if input not in self.symbol_list:
                    self.symbol_list.add(input)
        infile.close()

    @timer
    def det_min_net(self):
        self.all_symbol_list()
        usedir = self.name+"net_det_min"
        if os.path.exists(usedir):
            os.system("/bin/rm -rf %s"%usedir)
        os.makedirs(usedir)
        
        word_syms_file = open(os.path.join(usedir,"words.syms"), mode='w',encoding='utf-8')
        for index,symbol in enumerate(self.symbol_list):
            word_syms_file.write(symbol+"\t"+str(index)+"\n")
        word_syms_file.close()
        self.write_net(os.path.join(usedir,"G_base"))

        os.environ['LD_LIBRARY_PATH'] =os.path.abspath('fst_lib/')
        os.system('echo $LD_LIBRARY_PATH')
        os.system('./fst_bin/fstcompile --isymbols=%s --osymbols=%s %s %s'%(os.path.join(usedir,"words.syms"),os.path.join(usedir,"words.syms"),os.path.join(usedir,"G_base"),os.path.join(usedir,"G.comple")))
        # os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G.comple"),os.path.join(output_path,"G.comple_debug")))
        os.system('./fst_bin/fstdeterminize %s %s'%(os.path.join(usedir,"G.comple"),os.path.join(usedir,"G.det")))
        # os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G.det"),os.path.join(output_path,"G.det_debug")))
        os.system('./fst_bin/fstminimize %s %s'%(os.path.join(usedir,"G.det"),os.path.join(usedir,"G.det.min")))
        # os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(output_path,"words.syms"),os.path.join(output_path,"words.syms"),os.path.join(output_path,"G.det.min"),os.path.join(output_path,"G.det.min_debug")))
        os.system('./fst_bin/fstprint --isymbols=%s --osymbols=%s %s %s'%(os.path.join(usedir,"words.syms"),os.path.join(usedir,"words.syms"),os.path.join(usedir,"G.det.min"),os.path.join(usedir,"G")))

        self.reload_net(os.path.join(usedir,"G")) 


class slot_net(regular_net):
    def __init__(self,name,content,isarc,score,allslot):
        regular_net.__init__(self,name,isarc,score)
        self.name = "<"+self.name+">"
        if not isarc:
            self.score = 0

        self.oov_G_buffer = list()
        for item in content:

            if not item:
                continue
            if not self.is_valid(item):
                self.oov_G_buffer.append("%s\n"%item)
                continue

            if allslot is not None:
                pattern = r'<(.*?)>'
                matches = set(re.findall(pattern,item))
                got_none_slot = False
                for slot in matches:
                    if (slot not in allslot.keys()) or len(allslot[slot])==0:
                        got_none_slot = True
                        break
                if got_none_slot :
                    self.oov_G_buffer.append("%s\n"%item)
                    continue
            
            valid = self.add_regular_unit(item, self.start_node,self.end_node)
            if not valid:
                self.oov_G_buffer.append("%s\n"%item)




class main_net(regular_net):
    def __init__(self,name,isarc,score):
        regular_net.__init__(self,name,isarc,score)
        self.netbegin = 0
        self.netend = 0
        self.build_net_head_end()

    def build_net_head_end(self):
        # self.G_buffer.append("0 0 - -\n")
        # self.G_buffer.append("0 1 <s> <s>\n")
        self.net_arr[self.start_node].add_arc( self.start_node,"-",0)

        end_node = self.get_new_node()
        self.net_arr[self.start_node].add_arc(end_node,"<s>",0)
        if self.isarc:
            # self.G_buffer.append("1 2 - - %s\n"%(str(score)))
           
            last_end = end_node
            next_end = self.get_new_node()
            self.net_arr[last_end].add_arc(next_end,"-",self.score)

            self.netbegin = last_end
            self.netend = next_end
             # self.G_buffer.append("2 3 </s> </s>\n")
            last_end = next_end
            next_end = self.end_node

            self.net_arr[last_end].add_arc(next_end,"</s>",0)
        else:
            # self.G_buffer.append("1 2 - - %s\n"%(str(score)))
            last_end = end_node
            next_end = self.get_new_node()
            self.net_arr[last_end].add_arc(next_end,"-",self.score)
            # self.G_buffer.append("2 3 - - \n")

            last_end = next_end
            next_end = self.get_new_node()
            self.net_arr[last_end].add_arc(next_end,"-",0)
            
            self.netbegin = last_end
            self.netend = next_end

            # self.G_buffer.append("3 4 </s> </s>\n")
            last_end = next_end
            next_end = self.end_node
            self.net_arr[last_end].add_arc(next_end,"</s>",0)

            self.score = 0
        
        if "-" not in self.symbol_list:
            self.symbol_list.add("-")
        if "<s>" not in self.symbol_list:
            self.symbol_list.add("<s>")
        if "</s>" not in self.symbol_list:
            self.symbol_list.add("</s>")
    
    def make_net_for_line(self,line):
        if not self.is_valid(line):
            return False
       
        valid = self.add_regular_unit(line, self.netbegin,self.netend)
        return valid


class G_net_maker:
    def __init__(self, G_file,oov_G_file,allslot,isarc,score,slot_argument):
        self.G_file = G_file
        self.oov_G_file = oov_G_file
        self.oov_G_buffer = list()  
        self.allslot = allslot
        self.isarc = isarc
        self.score = score

        self.slot_argument = slot_argument
        self.allslot_net = {}
        self.net = main_net("main_net",self.isarc,self.score)

        if(self.check_slot_circle()):
            exit()
    @timer
    def build_slot_single_thread(self):
        for key,value in self.allslot.items():
            slot_sample = [one_slot for one_slot in (random.sample(value, min(self.slot_argument[key],len(value))) if key in self.slot_argument.keys() else value)]
            self.allslot_net["<"+key+">"] = slot_net(key,slot_sample,self.isarc,self.score,self.allslot)
    
    def build_slot_mutil_thread(self):
        p = Pool(10)
        for key,value in self.allslot.items():
            p.apply_async(self.mutil_thread_build_slot, args=(key,value))
        p.close()
        p.join()
    
    def mutil_thread_build_slot(self,slot_name,slot_content):
        self.allslot_net[slot_name] = slot_net(slot_name,slot_content,self.isarc,self.score,self.allslot)
    
    def mutil_thread_dump_slot(self,slot_name,slot_net):
        slot_net.write_net(os.path.join("slot_dump",slot_name))
    
    def dump_slot(self):
        if os.path.exists("slot_dump"):
            os.system("/bin/rm -rf slot_dump")
        os.makedirs("slot_dump")
        # for key,value in self.allslot_net.items():
        #     value.write_net(os.path.join("slot_dump",key))

        p = Pool(10)
        for key,value in self.allslot_net.items():
            p.apply_async(self.mutil_thread_dump_slot, args=(key,value))
        p.close()
        p.join()

    def optimial_main_net(self):
        self.net.det_min_net()

    def check_slot_circle(self):
        content_net = {}
        for key,value in self.allslot.items():
            content_net[key] = set()
            for line in value:
                matches = re.findall(r'<.*?>',line)
                if len(matches) > 0:
                    for slot in re.findall(r'<(.*?)>',line):
                        print(slot)
                        content_net[key].add(slot)
        input_num = {key:0 for key in content_net.keys()}
        for node,arc_set in content_net.items():
            for node_end in arc_set:
                input_num[node_end] = input_num[node_end]+1


        queue = []
        for slot,num in input_num.items():
            if num==0:
                queue.append(slot)

        node_count = 0
        while len(queue) !=0:
            one_slot = queue.pop(0)
            for node_end in content_net[one_slot]:
                input_num[node_end] = input_num[node_end] -1 
                if input_num[node_end]==0:
                    queue.append(node_end)
            node_count = node_count+1


        if node_count == len(input_num):
            return False
        
        print("got circle ")
        for slot,num in input_num.items():
            if num !=0:
                print("slot :" + slot)
        return True

    def write_one_regular_line(self,line):

        if not line:
            return
        
        if self.allslot is not None:
            pattern = r'<(.*?)>'
            matches = set(re.findall(pattern,line))
            got_none_slot = False
            for slot in matches:
                if (slot not in self.allslot.keys()) or len(self.allslot[slot])==0:
                    got_none_slot = True
                    break
            if got_none_slot :
                self.oov_G_buffer.append("%s\n"%line)
                return


        valid = self.net.make_net_for_line(line)
        if not valid:
            self.oov_G_buffer.append("%s\n"%line)
    
    def expand_with_slot(self):
        self.net.net_expand(self.allslot_net)
    
    def write_oov(self):
        outfile = open(self.oov_G_file, mode='w',encoding='utf-8')
        outfile.write("".join(self.oov_G_buffer) + "\n")

        for key,subnet in self.allslot_net.items():
            outfile.write("".join(subnet.oov_G_buffer) + "\n")

        outfile.close()
    
    def flush(self):
        # self.optimial_main_net()


        self.build_slot_single_thread()


        self.expand_with_slot()

        self.net.write_net(self.G_file)
    
        self.write_oov()

        # self.optimial_main_net()

    
   
if __name__ == "__main__":
    allslot={}

    for root ,dirs,files in os.walk("/raw7/asrdictt/kezhao/asrmlg_edgen_hw/english_test/custom_corpus_process/slot_final_train"):
        for file in files:
            encoding='utf-8'
            # print(file)
            if ".sh" in file:
                continue
            
            f = open(os.path.join(root,file), mode='r',encoding=encoding)
            allslot[file] = set(f.read().splitlines())
            if " " in allslot[file]:
                allslot[file].remove(" ")
            if "" in allslot[file]:
                allslot[file].remove("")
            f.close()
    # exit()

    file = "/raw7/asrdictt/kezhao/asrmlg_edgen_hw/english_test/custom_final_train_corpus.txt_noset"
    outfile = open(file, mode='r',encoding='utf-8') #dict from for_train
    test_sent = outfile.read().splitlines()
    outfile.close()
    slot_path = "slot_test"

    print(len(test_sent))
    Gnet = G_net_maker(os.path.join("G_base"),os.path.join("oov_G_base"),allslot,False,6,None)
    for line in test_sent:
        Gnet.write_one_regular_line(line.strip())
    Gnet.flush()
        # # print(test_set)
        # # print(valid)
        # # print(len(test_set))
        # # for line in test_set:
        # #     print(line)
        # exit()
    # Gnet.write_last_line()
    # Gnet.flush()

# temp_string_set = set()
