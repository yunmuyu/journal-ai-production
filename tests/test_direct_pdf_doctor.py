import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DirectPdfDoctor(unittest.TestCase):
    def test_doctor_reports_missing_core_dependencies_before_loading_renderers(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'doctor.json'
            script = '''
import importlib.abc,runpy,sys
class MissingCore(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('pymupdf','fontTools'):
            raise ModuleNotFoundError('Simulated missing core dependency: '+fullname)
sys.meta_path.insert(0,MissingCore())
sys.argv=['journal_pdf','doctor','--output',sys.argv[1]]
runpy.run_module('journal_pdf',run_name='__main__')
'''
            result = subprocess.run([sys.executable, '-B', '-c', script, str(report)],
                                    cwd=ROOT / 'portable-production/direct-pdf', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(report.read_text(encoding='utf-8'))
            missing = {row['module'] for row in data['modules'] if not row['available']}
            self.assertTrue({'pymupdf', 'fontTools'} <= missing)
            self.assertFalse(data['all_dependencies_available'])
            self.assertFalse(data['system_mutations'])


if __name__ == '__main__':
    unittest.main()
