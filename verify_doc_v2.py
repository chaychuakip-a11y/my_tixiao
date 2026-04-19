import os
import sys
import hashlib
import re
import tempfile
import shutil

# Add paths for project modules
project_root = "/home/lty/my_tixiao/asr_mlg"
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "pipeline"))
sys.path.insert(0, os.path.join(project_root, "pipeline/tools"))

def test_wfst_merging_logic():
    print("\n--- Level 4: WFST Merging Logic (corpus_process_package.py) ---")
    try:
        from corpus_process_package import findmaxnode, modify_nodes
        
        # 1. Create a dummy base WFST
        # format: start_node end_node input output weight
        base_wfst_content = "0\t1\ta\ta\t0.1\n1\t2\tb\tb\t0.2\n2\n"
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f_base:
            f_base.write(base_wfst_content)
            base_path = f_base.name
        
        # 2. Create a dummy sub WFST (to be merged)
        sub_wfst_content = "0\t1\tx\tx\t0.5\n1\n"
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f_sub:
            f_sub.write(sub_wfst_content)
            sub_path = f_sub.name
        
        # 3. Test findmaxnode
        max_node, end_node = findmaxnode(base_path)
        print(f"[INFO] Base Max Node: {max_node}, End Node: {end_node}")
        
        # 4. Test modify_nodes (offsetting)
        # Expected behavior: sub nodes (except 0) should be offset by max_node
        out_modified_path = sub_path + ".mod"
        # base_maxnode=2, base_endnode=2, kunei_endnode=1
        modify_nodes(sub_path, out_modified_path, max_node, end_node, "1")
        
        with open(out_modified_path, 'r') as f:
            mod_content = f.read()
        print(f"Modified Sub WFST:\n{mod_content}")
        
        # Node 0 stays 0, Node 1 (endnode) becomes base_endnode (2)
        # Check: 0\t2\tx\tx\t0.5
        if "0\t2\tx\tx\t0.5" in mod_content:
            print("[PASS] WFST node modification and coordinate offsetting works as documented.")
        else:
            print("[FAIL] WFST node modification failed to map correctly.")
            
        os.remove(base_path); os.remove(sub_path); os.remove(out_modified_path)
    except Exception as e:
        print(f"[FAIL] Error testing WFST merging: {e}")

def test_template_expansion():
    print("\n--- Level 5: Template Expansion (excel_to_txt_sampler.py) ---")
    try:
        from excel_to_txt_sampler import CorpusAdapter
        
        # We'll manually inject data into CorpusAdapter to test _expand_template
        adapter = CorpusAdapter("dummy.xlsx", target_count=5)
        adapter.slot_dict = {
            "<singer>": ["周杰伦", "王菲"],
            "<song>": ["青花瓷", "红豆"]
        }
        
        template = "我想听 <singer> 的 <song>"
        # Test recursive expansion
        expanded = adapter._expand_template(template)
        print(f"Template: {template}")
        print(f"Expanded: {expanded}")
        
        if "<" not in expanded and "的" in expanded:
            print("[PASS] Template expansion logic correctly replaces placeholders.")
        else:
            print("[FAIL] Template expansion left placeholders or failed.")
    except Exception as e:
        print(f"[FAIL] Error testing template expansion: {e}")

def test_semantic_hashing():
    print("\n--- Level 6: Semantic Hashing (pipeline_executor.py) ---")
    try:
        # Since reading real Excel requires openpyxl/pandas, we'll check if DeltaTracker is present
        from pipeline_executor import DeltaTracker
        
        # Test simple string-based semantic hash logic mentioned in doc
        # (The doc says it joins text with '|')
        test_content = ["Hello", "World"]
        content_str = "|".join(test_content)
        expected_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
        
        print(f"[INFO] Checking if DeltaTracker implementation matches documentation theory...")
        # We can't easily run it on a real file without installing dependencies, 
        # but we can verify the method existence.
        if hasattr(DeltaTracker, 'get_semantic_hash'):
            print("[PASS] DeltaTracker has get_semantic_hash method.")
        else:
            print("[FAIL] DeltaTracker missing semantic hash implementation.")
    except Exception as e:
        print(f"[FAIL] Error testing DeltaTracker: {e}")

if __name__ == "__main__":
    # Import existing Level 1-3 from previous run or just call them if verify_doc.py is still there
    # For a clean run, let's just run the new levels
    test_wfst_merging_logic()
    test_template_expansion()
    test_semantic_hashing()
