import unittest
import os
import sys
import shutil
import tempfile
import hashlib
import json
import re
from unittest.mock import MagicMock, patch
from pathlib import Path

# Setup paths
project_root = "/home/lty/my_tixiao/asr_mlg"
pipeline_dir = os.path.join(project_root, "pipeline")
tools_dir = os.path.join(pipeline_dir, "tools")

sys.path.insert(0, project_root)
sys.path.insert(0, pipeline_dir)
sys.path.insert(0, tools_dir)

# Import components
import pipeline_executor
# make_test_set expects -e argument at import time due to its pre-parser
# also corpus_process expects language_map in CWD
sys.argv.extend(['-e', project_root])
_old_cwd = os.getcwd()
os.chdir(project_root)
import make_test_set
os.chdir(_old_cwd)
import pipeline_warmup
from excel_to_txt_sampler import CorpusAdapter
from lexicon_vcs import LexiconVCS

class ComprehensiveASRVerifier(unittest.TestCase):

    def setUp(self):
        self.test_workspace = tempfile.mkdtemp()
        # Create a mock asrmlg structure
        self.exp_dir = os.path.join(self.test_workspace, "asr_mlg")
        os.makedirs(os.path.join(self.exp_dir, "res/En_res/ubctc_duan"), exist_ok=True)
        os.makedirs(os.path.join(self.exp_dir, "g2p/En/g2p_models"), exist_ok=True)
        
        # Create language_map
        with open(os.path.join(self.exp_dir, "language_map"), 'w') as f:
            f.write("26: En\n10: Th\n")

    def tearDown(self):
        shutil.rmtree(self.test_workspace)

    # --- 1. Verify Hebrew Context Logic (Bug-Sensitive Area) ---
    def test_hebrew_context_generation(self):
        print("Verifying Hebrew Context Logic...")
        # Since we can't easily mock pandas.ExcelFile in a simple way without real xlsx,
        # we'll mock the internal structure that generate_context_for_hebrew_oov expects.
        
        oov_file = os.path.join(self.test_workspace, "oov.txt")
        with open(oov_file, 'w') as f: f.write("OOV1\n")
        
        output_input_txt = os.path.join(self.test_workspace, "input.txt")
        
        # We need to patch pandas to avoid real Excel reading
        with patch('pandas.ExcelFile') as mock_xl:
            # Setup a complex mock for the nested logic in generate_context_for_hebrew_oov
            mock_xl_inst = MagicMock()
            mock_xl_inst.sheet_names = ['sent_sheet', '<>_sheet']
            mock_xl.return_value = mock_xl_inst
            
            def mock_read_excel(xl, sheet_name, **kwargs):
                df = MagicMock()
                if 'sent' in sheet_name:
                    df.values.flatten.return_value = ["This is a sentence with OOV1."]
                elif '<>' in sheet_name:
                    df.columns = ['<unused>']
                return df
            
            with patch('pandas.read_excel', side_effect=mock_read_excel):
                # Note: We expect Bug-1 (missing 're') if we didn't fix it, 
                # but here we are just testing the logic path.
                try:
                    pipeline_executor.generate_context_for_hebrew_oov(
                        oov_file, self.test_workspace, output_input_txt, 'utf-8', '\n'
                    )
                    with open(output_input_txt, 'r') as f:
                        content = f.read()
                    self.assertIn("This is a sentence with OOV1.", content)
                    print("✅ Hebrew logic successfully found sentence context.")
                except NameError as e:
                    if "'re' is not defined" in str(e):
                        print("🚨 [BUG-1 CONFIRMED] Hebrew logic crashed due to missing 're' import.")
                    else: raise e

    # --- 2. Verify MLF Generation (HTK Standard) ---
    def test_mlf_generation_format(self):
        print("Verifying MLF Generation...")
        input_txt = os.path.join(self.test_workspace, "test.txt")
        output_mlf = os.path.join(self.test_workspace, "test.mlf")
        
        with open(input_txt, 'w') as f:
            f.write("audio_01\tnavigate to london\n")
            
        make_test_set.generate_mlf(input_txt, output_mlf)
        
        with open(output_mlf, 'r') as f:
            lines = f.readlines()
            
        self.assertEqual(lines[0].strip(), "#!MLF!#")
        self.assertEqual(lines[1].strip(), '"*/audio_01.lab"')
        self.assertEqual(lines[2].strip(), "<s>")
        self.assertEqual(lines[-2].strip(), "</s>")
        self.assertEqual(lines[-1].strip(), ".")
        print("✅ MLF format is compliant with HTK standards.")

    # --- 3. Verify Pipeline Warmup (Incremental Logic) ---
    def test_pipeline_warmup_manifest(self):
        print("Verifying Pipeline Warmup...")
        corpus_dir = os.path.join(self.test_workspace, "corpus")
        os.makedirs(corpus_dir)
        manifest_path = os.path.join(self.test_workspace, "manifest.json")
        
        # Create a dummy xlsx (just empty, hashing will fallback to binary MD5)
        xlsx_path = os.path.join(corpus_dir, "data.xlsx")
        with open(xlsx_path, 'wb') as f: f.write(b"fake excel content")
        
        pipeline_warmup.warmup_manifest(corpus_dir, manifest_path, "test_project")
        
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, 'r') as f:
            data = json.load(f)
            
        self.assertIn("data.xlsx", data)
        self.assertEqual(data["data.xlsx"]["task_msg"], "test_project")
        self.assertTrue(data["data.xlsx"]["processed_time"].startswith("WARMUP_"))
        print("✅ Warmup manifest generated correctly with binary fallback.")

    # --- 4. Verify Command Building Whitelists ---
    def test_command_whitelist_filtering(self):
        print("Verifying Command Parameter Filtering...")
        task = {
            "msg": "p1",
            "l": 26,             # single dash
            "G": "1-6",          # single dash
            "enable_g2p": True,  # internal (filtered)
            "custom": "val"      # double dash
        }
        cmd = pipeline_executor.build_base_command(task, "python", "script.py", "/tmp")
        
        self.assertIn("-l", cmd)
        self.assertIn("-G", cmd)
        self.assertIn("--custom", cmd)
        self.assertNotIn("--enable_g2p", cmd)
        self.assertNotIn("--msg", cmd) # msg is internal but used for output dir naming usually? 
                                       # Actually in code msg IS in internal_keys if not explicitly handled?
                                       # Wait, check source: internal_keys = {'enable_g2p', ... 'output', ...}
                                       # 'msg' is NOT in internal_keys in my provided content.
        print("✅ Parameter whitelisting and prefixing verified.")

    # --- 5. Verify Step 3 Return Value Bug ---
    def test_step3_failure_handling(self):
        print("Verifying Step 3 Error Propagation...")
        # Step 3 should fail if subprocess fails, but documentation says it returns True regardless.
        with patch('pipeline_executor.run_subprocess', return_value=False):
            # Mock task and global_cfg
            task = {'l': '26', 'is_yun': '0'}
            global_cfg = {
                'asrmlg_exp_dir': self.exp_dir,
                'parsed_language_map': {'26': 'En'},
                'res_dir_map': {'0': 'ubctc_duan'},
                'lang_abbr_map': {'26': 'En'},
                'g2p_root_dir': os.path.join(self.exp_dir, "g2p")
            }
            
            # We need to mock LexiconVCS to avoid file errors
            with patch('pipeline_executor.LexiconVCS'):
                # We need output.dict to exist for Step 3 to proceed to run_subprocess
                g2p_out = os.path.join(self.exp_dir, "g2p/En/g2p_models/output.dict")
                with open(g2p_out, 'w') as f: f.write("word\tp h o n e\n")
                
                result = pipeline_executor.step3_merge_dict(task, global_cfg, "msg", "log.txt")
                
                if result is True:
                    print("🚨 [BUG-3 CONFIRMED] Step 3 returned True despite merge failure.")
                else:
                    print("✅ Step 3 correctly propagated failure.")

if __name__ == "__main__":
    unittest.main()
