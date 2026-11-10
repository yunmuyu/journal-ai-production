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

    def test_workbench_and_shared_tools_are_included_and_sealed(self):
        tool = self.root / "workbench/runner.mjs"
        tool.parent.mkdir()
        tool.write_bytes(b"export {};\n")
        subprocess.run(["git", "-C", str(self.root), "add", "workbench"], check=True)
        self.release["publicFiles"] = [{"path": "workbench/runner.mjs", "bytes": 11,
            "sha256": hashlib.sha256(tool.read_bytes()).hexdigest()}]
        self.save_release()
        output = Path(self.temp.name) / "full.zip"
        bundle.build(self.root, output)
        with zipfile.ZipFile(output) as archive:
            self.assertIn(f"journal-ai-production-{self.identity}/workbench/runner.mjs", archive.namelist())
        tool.write_bytes(b"tampered")
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

    def test_compatibility_runtime_is_part_of_the_same_sealed_bundle(self):
        runtime = self.root / 'production-runtime' / 'adapter.jsx'
        runtime.parent.mkdir()
        runtime.write_bytes(b'// adapter\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'production-runtime'], check=True)
        self.release['files'] = [{'path': 'adapter.jsx', 'bytes': runtime.stat().st_size,
            'sha256': hashlib.sha256(runtime.read_bytes()).hexdigest()}]
        self.save_release()
        output = Path(self.temp.name) / 'runtime.zip'
        bundle.build(self.root, output)
        with zipfile.ZipFile(output) as archive:
            self.assertIn(f'journal-ai-production-{self.identity}/production-runtime/adapter.jsx', archive.namelist())

    def candidate_manifest(self):
        candidate = {"schemaVersion": 1, "id": "2026.11.10-r49-draft",
                     "status": "draft-only", "productionEligible": False,
                     "portableFiles": self.release["portableFiles"], "publicFiles": []}
        note = self.root / "release-notes/2026.11.10-r49-draft.md"
        note.write_text("Draft only. Not a release.")
        for name in ("README.md", "CHANGELOG.md", "RELEASE.json",
                     "docs/RELEASE-GUIDE.md", "scripts/release_bundle.py",
                     "release-notes/2026.11.10-r49-draft.md"):
            data = (self.root / name).read_bytes()
            candidate["publicFiles"].append({"path": name, "bytes": len(data),
                                             "sha256": hashlib.sha256(data).hexdigest()})
        self.save_candidate(candidate)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        return candidate

    def save_candidate(self, candidate):
        (self.root / "CANDIDATE.json").write_text(json.dumps(candidate))

    def test_candidate_is_reproducible_explicit_and_not_a_release(self):
        historical = (self.root / "RELEASE.json").read_bytes()
        self.candidate_manifest()
        with self.assertRaisesRegex(ValueError, "cannot build a release"):
            bundle.build(self.root, Path(self.temp.name) / "release.zip")
        first, second = [Path(self.temp.name) / name for name in ("a.zip", "b.zip")]
        self.assertEqual(bundle.build(self.root, first, candidate=True)["sha256"],
                         bundle.build(self.root, second, candidate=True)["sha256"])
        with zipfile.ZipFile(first) as archive:
            archive.extractall(Path(self.temp.name) / "unpack")
        target = Path(self.temp.name) / "unpack/journal-ai-candidate-2026.11.10-r49-draft"
        result = bundle.verify(target)
        self.assertEqual(result["status"], "draft-only")
        self.assertFalse(result["productionEligible"])
        self.assertEqual((target / "RELEASE.json").read_bytes(), historical)
        (target / "CANDIDATE.json").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            bundle.verify(target)

    def test_candidate_rejects_changed_code_and_unsealed_metadata(self):
        candidate = self.candidate_manifest()
        code = self.root / "portable-production/localflow/demo.py"
        code.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            bundle.build(self.root, Path(self.temp.name) / "bad.zip", candidate=True)
        code.write_bytes(b"pass\n")
        candidate["publicFiles"] = []
        self.save_candidate(candidate)
        with self.assertRaisesRegex(ValueError, "Unsealed candidate"):
            bundle.build(self.root, Path(self.temp.name) / "bad.zip", candidate=True)

    def test_candidate_rejects_invalid_identity_status_and_private_inputs(self):
        candidate = self.candidate_manifest()
        for key, value in (("status", "release"), ("productionEligible", True),
                           ("id", self.identity)):
            invalid = dict(candidate, **{key: value})
            self.save_candidate(invalid)
            with self.assertRaisesRegex(ValueError, "draft-only"):
                bundle.build(self.root, Path(self.temp.name) / "bad.zip", candidate=True)
        candidate["portableFiles"] = [{"path": "config.local.json", "bytes": 7,
                                       "sha256": hashlib.sha256(b"private").hexdigest()}]
        self.save_candidate(candidate)
        with self.assertRaisesRegex(ValueError, "Private"):
            bundle.build(self.root, Path(self.temp.name) / "bad.zip", candidate=True)
