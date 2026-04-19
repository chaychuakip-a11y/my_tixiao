import unittest
import os
import sys
import shutil
import tempfile
import hashlib
import json
import re
from pathlib import Path

# Add paths for project modules
project_root = "/home/lty/my_tixiao/asr_mlg"
pipeline_dir = os.path.join(project_root, "pipeline")
tools_dir = os.path.join(pipeline_dir, "tools")

sys.path.insert(0, project_root)
sys.path.insert(0, pipeline_dir)
sys.path.insert(0, tools_dir)

from pipeline_executor import get_file_md5_suffix, build_base_command, resolve_and_bind_paths
from merge_dict import merge_dictionaries, load_valid_phones
from lexicon_vcs import LexiconVCS
from excel_to_txt_sampler import CorpusAdapter

class TestASRPipeline(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir)

    # --- pipeline_executor.py Tests ---

    def test_get_file_md5_suffix(self):
        test_file = os.path.join(self.test_dir, "test.bin")
        content = b"hello world"
        with open(test_file, 'wb') as f:
            f.write(content)
        
        expected_md5 = hashlib.md5(content).hexdigest()
        suffix = get_file_md5_suffix(test_file, suffix_len=4)
        self.assertEqual(suffix, expected_md5[-4:])

    def test_build_base_command(self):
        task = {
            "msg": "test_task",
            "l": 26,
            "cp": "corpus.xlsx",      # Should resolve to absolute
            "enable_g2p": True,       # Internal key, should be skipped
            "custom_flag": True,      # Boolean flag
            "excel_corpus_path": "res/en_nav.xlsx" # Should resolve to absolute
        }
        python_exec = "/usr/bin/python3"
        train_script = "train.py"
        exp_dir = "/data/asr"
        
        cmd = build_base_command(task, python_exec, train_script, exp_dir)
        
        # Verify headers
        self.assertEqual(cmd[0], python_exec)
        self.assertEqual(cmd[1], train_script)
        
        # Verify single dash whitelist (-l, -cp)
        self.assertIn("-l", cmd)
        self.assertIn("-cp", cmd)
        
        # Verify internal keys skipped
        self.assertNotIn("--enable_g2p", cmd)
        
        # Verify boolean flags
        self.assertIn("--custom_flag", cmd)
        
        # Verify path resolution for cp
        idx_cp = cmd.index("-cp")
        self.assertEqual(cmd[idx_cp+1], os.path.join(exp_dir, "corpus.xlsx"))
        
        # Verify path resolution for excel_corpus_path
        idx_ecp = cmd.index("--excel_corpus_path")
        self.assertEqual(cmd[idx_ecp+1], os.path.join(exp_dir, "res/en_nav.xlsx"))

    def test_resolve_and_bind_paths_defaults(self):
        global_cfg = {}
        base_path = "/home/lty/my_tixiao/asr_mlg/pipeline"
        
        resolved = resolve_and_bind_paths(global_cfg, base_path)
        
        # Check asrmlg_exp_dir derivation
        self.assertEqual(resolved['asrmlg_exp_dir'], os.path.abspath(os.path.join(base_path, "..")))
        # Check defaults
        self.assertTrue(resolved['output_dir'].endswith("output"))
        self.assertTrue(resolved['tools_dir'].endswith("tools"))

    # --- tools/merge_dict.py Tests ---

    def test_merge_dictionaries(self):
        base_dict = os.path.join(self.test_dir, "base.dict")
        new_dict = os.path.join(self.test_dir, "new.dict")
        syms_file = os.path.join(self.test_dir, "phones.syms")
        
        with open(base_dict, 'w') as f:
            f.write("hello\th e l l o\n")
            
        with open(new_dict, 'w') as f:
            f.write("world\tw o r l d\n")      # Valid
            f.write("hello\th e l l o\n")      # Duplicate
            f.write("badword\tx y z\n")        # Illegal phones
            f.write("invalid_format\n")        # Format error
            
        with open(syms_file, 'w') as f:
            for p in "h e l l o w o r l d".split():
                f.write(f"{p}\t1\n")

        merge_dictionaries(base_dict, new_dict, syms_file)
        
        with open(base_dict, 'r') as f:
            lines = f.readlines()
            
        self.assertEqual(len(lines), 2) # hello and world
        self.assertIn("world\tw o r l d\n", lines)
        self.assertNotIn("badword\tx y z\n", lines)

    # --- tools/lexicon_vcs.py Tests ---

    def test_lexicon_vcs_rollback(self):
        dict_path = os.path.join(self.test_dir, "new_dict")
        with open(dict_path, 'w') as f: f.write("v1 content\n")
        
        vcs = LexiconVCS(dict_path, max_versions=5)
        
        # Snapshot v1
        vcs.pre_merge()
        v1_hash = vcs._get_md5(dict_path)
        
        # Modify to v2
        with open(dict_path, 'w') as f: f.write("v2 content\n")
        vcs.post_merge("task2", "26")
        
        # Rollback to v1
        vcs.rollback(v1_hash)
        
        with open(dict_path, 'r') as f:
            self.assertEqual(f.read(), "v1 content\n")

    # --- tools/excel_to_txt_sampler.py Tests ---

    def test_template_expansion(self):
        adapter = CorpusAdapter("dummy.xlsx")
        adapter.slot_dict = {
            "<city>": ["London", "Paris"],
            "<action>": ["go to", "visit"]
        }
        
        template = "[Please] <action> <city>"
        expanded = adapter._expand_template(template)
        
        # Check if placeholders are gone
        self.assertNotIn("<city>", expanded)
        self.assertNotIn("<action>", expanded)
        # Check if one of the values is present
        self.assertTrue("London" in expanded or "Paris" in expanded)
        self.assertTrue("go to" in expanded or "visit" in expanded)

    # --- Bug Verification Tests ---

    def test_bug_1_re_import(self):
        """Verify if 're' is imported in pipeline_executor.py (Bug-1)"""
        with open(os.path.join(pipeline_dir, "pipeline_executor.py"), 'r') as f:
            content = f.read()
            # If re.sub is used but 'import re' is missing at top level
            if "re.sub" in content and not re.search(r"^import re", content, re.M):
                print("\n[CONFIRMED] Bug-1: 'import re' is missing in pipeline_executor.py")

    def test_bug_3_step3_return_value(self):
        """Verify if step3_merge_dict always returns True (Bug-3)"""
        with open(os.path.join(pipeline_dir, "pipeline_executor.py"), 'r') as f:
            content = f.read()
            # Find the end of step3_merge_dict
            match = re.search(r"def step3_merge_dict.*?return True", content, re.S)
            if match:
                # Check if it ignores merge_success
                if "return merge_success" not in match.group(0):
                     print("\n[CONFIRMED] Bug-3: step3_merge_dict ignores merge_success and returns True")

if __name__ == "__main__":
    unittest.main()
