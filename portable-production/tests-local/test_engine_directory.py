import tempfile
import unittest
from pathlib import Path

from localflow.core import FlowError, engine_directory


class EngineDirectoryTest(unittest.TestCase):
    def test_source_and_installed_layouts(self):
        for name in ("direct-pdf", "engine"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / name / "journal_pdf"
                package.mkdir(parents=True)
                (package / "__init__.py").write_text("", encoding="utf-8")
                self.assertEqual(engine_directory(root), root / name)

    def test_missing_or_ambiguous_engine_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(FlowError):
                engine_directory(root)
            for name in ("direct-pdf", "engine"):
                package = root / name / "journal_pdf"
                package.mkdir(parents=True)
                (package / "__init__.py").write_text("", encoding="utf-8")
            with self.assertRaises(FlowError):
                engine_directory(root)
