import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location(
    "release_bundle", Path(__file__).resolve().parents[1] / "scripts/release_bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class ReleaseBundleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.identity = "2026.10.20-r32-test"
        files = {
            "portable-production/localflow/demo.py": b"pass\n",
            "portable-production/config.local.json": b"private",
            "README.md": b"readme",
            "CHANGELOG.md": b"changes",
            "docs/RELEASE-GUIDE.md": b"guide",
            "scripts/release_bundle.py": b"script",
            f"release-notes/{self.identity}.md": b"notes",
        }
        for name, data in files.items():
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        self.release = {"id": self.identity, "portableFiles": [
            {"path": "localflow/demo.py", "bytes": 5,
             "sha256": hashlib.sha256(b"pass\n").hexdigest()}]}
        self.save_release()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True,
                       capture_output=True)

    def save_release(self):
        (self.root / "RELEASE.json").write_text(json.dumps(self.release), encoding="utf-8")

    def test_reproducible_bundle_and_extracted_tamper_detection(self):
        first, second = [Path(self.temp.name) / name for name in ("one.zip", "two.zip")]
        self.assertEqual(bundle.build(self.root, first)["sha256"],
                         bundle.build(self.root, second)["sha256"])
        unpack = Path(self.temp.name) / "unpack"
        with zipfile.ZipFile(first) as archive:
            self.assertFalse(any("config.local" in name for name in archive.namelist()))
            archive.extractall(unpack)
        target = unpack / f"journal-ai-production-{self.identity}"
        self.assertEqual(bundle.verify(target)["verified_files"], 7)
        (target / "portable-production/localflow/demo.py").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            bundle.verify(target)

    def test_changed_sealed_source_is_rejected(self):
        (self.root / "portable-production/localflow/demo.py").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Release hash mismatch"):
            bundle.build(self.root, Path(self.temp.name) / "bad.zip")

    def test_untracked_and_private_manifest_inputs_are_rejected(self):
        for name in ("secret.py", "config.local.json"):
            data = b"private"
            (self.root / "portable-production" / name).write_bytes(data)
            self.release["portableFiles"] = [{
                "path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}]
            self.save_release()
            with self.assertRaisesRegex(ValueError, "Untracked|Private"):
                bundle.build(self.root, Path(self.temp.name) / "bad.zip")
