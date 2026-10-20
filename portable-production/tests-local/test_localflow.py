from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from localflow.catalog import catalog
from localflow.core import Config, FlowError, hash_file, write_json
from localflow.probing import check_snapshot, probe
from localflow.publishing import accept, publish, review
from localflow.pdf_compat import audit_delivery_pdfs, audit_pdf_compatibility
from localflow.rendering import check_candidate, check_constraints, render


RELEASE = Path(__file__).resolve().parents[1]


class LocalFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.delivery = root / "delivery"
        self.author = self.delivery / "编辑" / "作者"
        self.author.mkdir(parents=True)
        self.source = self.author / "原稿.txt"
        self.source.write_text("N1 -> N2", encoding="utf-8")
        self.config = Config(self.delivery, root / "state", RELEASE / "fonts.local.json", root / "cache")
        self.manifest = root / "manifest.json"
        write_json(self.manifest, {"source_root": str(self.author),
            "files": [{"id": "source-1", "path": self.source.name}]})
        self.spec = root / "spec.json"
        template = json.loads((RELEASE / "engine" / "examples" / "specs" / "demo-network.json").read_text(encoding="utf-8"))
        template.update({"synthetic": False, "author": "作者", "author_rel": "编辑/作者",
            "figure_number": "1", "processing_method": "rebuild",
            "sources": [{"path": self.source.name, "sha256": hash_file(self.source), "role": "source"}]})
        write_json(self.spec, template)
        self.constraints = root / "constraints.json"
        write_json(self.constraints, {"confirmed": {"split": "single", "processing_method": "rebuild",
            "backend": "direct-pdf", "column": "single",
            "expected_outputs": [{"author_rel": "编辑/作者", "figure_number": "1"}]},
            "suggested": {"column": None}})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_catalog_when_attachment_has_figure_name(self) -> None:
        attachment = self.author / "图片及说明"
        attachment.mkdir()
        (attachment / "作者-图2.pdf").write_bytes(b"attachment")
        (self.author / "作者-图1.pdf").write_bytes(b"existing")
        result = catalog(self.config)
        self.assertEqual(result["files"], 3)
        self.assertEqual(result["existing_deliveries"], 1)
        self.assertEqual(catalog(self.config)["hashed_files"], 0)

    def test_probe_when_identity_changes(self) -> None:
        first = probe(self.config, self.manifest)
        self.assertFalse(first["cached"])
        self.assertTrue(probe(self.config, self.manifest)["cached"])
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["files"][0]["id"] = "another-id"
        write_json(self.manifest, data)
        self.assertNotEqual(first["probe_id"], probe(self.config, self.manifest)["probe_id"])

    def test_probe_when_evidence_changes(self) -> None:
        result = probe(self.config, self.manifest)
        report = self.config.state_root / "probes" / result["probe_id"] / "evidence" / "probe.json"
        report.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(FlowError, "证据"):
            check_snapshot(self.config, result["probe_id"])

    def test_constraints_when_explicit_suggestion_conflicts(self) -> None:
        spec = json.loads(self.spec.read_text(encoding="utf-8"))
        constraints = json.loads(self.constraints.read_text(encoding="utf-8"))
        constraints["suggested"]["column"] = "double"
        with self.assertRaisesRegex(FlowError, "冲突"):
            check_constraints(spec, constraints)

    def test_constraints_when_figure_number_is_unconfirmed(self) -> None:
        spec = json.loads(self.spec.read_text(encoding="utf-8"))
        constraints = json.loads(self.constraints.read_text(encoding="utf-8"))
        spec["figure_number"] = "2.1"
        with self.assertRaisesRegex(FlowError, "交付目标"):
            check_constraints(spec, constraints)

    def test_render_when_source_changes_after_probe(self) -> None:
        probed = probe(self.config, self.manifest)
        self.source.write_text("N2 -> N1", encoding="utf-8")
        with self.assertRaisesRegex(FlowError, "源文件"):
            render(self.config, self.spec, self.constraints, probed["probe_id"])

    def test_render_when_font_profile_is_preview(self) -> None:
        profile = json.loads(self.config.font_profile.read_text(encoding="utf-8"))
        profile["purpose"] = "preview"
        preview = Path(self.temp.name) / "preview-fonts.json"
        write_json(preview, profile)
        config = Config(self.delivery, self.config.state_root, preview, self.config.cache_root)
        probed = probe(config, self.manifest)
        with self.assertRaisesRegex(FlowError, "预览字体"):
            render(config, self.spec, self.constraints, probed["probe_id"])

    def test_candidate_when_original_constraints_change(self) -> None:
        probed = probe(self.config, self.manifest)
        candidate = render(self.config, self.spec, self.constraints, probed["probe_id"])
        constraints = json.loads(self.constraints.read_text(encoding="utf-8"))
        constraints["confirmed"]["column"] = "double"
        write_json(self.constraints, constraints)
        with self.assertRaisesRegex(FlowError, "原始已确认约束"):
            check_candidate(self.config, candidate["candidate_id"])

    def test_real_chain_when_target_changes(self) -> None:
        probed = probe(self.config, self.manifest)
        candidate = render(self.config, self.spec, self.constraints, probed["probe_id"])
        cid = candidate["candidate_id"]
        review_file = Path(self.temp.name) / "review.json"
        write_json(review_file, {"candidate_id": cid, "output_sha256": candidate["sha256"],
            "constraints_sha256": json.loads((self.config.state_root / "candidates" / cid / "candidate.json").read_text(encoding="utf-8"))["constraints_sha256"],
            "source_hashes": {self.source.name: hash_file(self.source)},
            "author_rel": "编辑/作者", "figure_number": "1", "reviewer": "测试审阅者",
            "content": {"conclusion": "approved", "evidence": ["对照原稿文字核对 N1 与 N2 连线顺序"]},
            "visual": {"conclusion": "approved", "evidence": ["按实际尺寸观察单栏图幅、线条和字形"]}})
        review(self.config, cid, review_file)
        first = publish(self.config, cid, "编辑/作者", "1")
        self.assertEqual(first["status"], "published-candidate")
        self.assertIsInstance(candidate["warning_count"], int)
        self.assertTrue(Path(candidate["render_log"]).is_file())
        self.assertEqual(publish(self.config, cid, "编辑/作者", "1")["status"], "already-published")
        target = self.author / "作者-图1.pdf"
        target.write_bytes(b"manual edit")
        with self.assertRaisesRegex(FlowError, "不同内容"):
            publish(self.config, cid, "编辑/作者", "1")
        old = hash_file(target)
        replaced = publish(self.config, cid, "编辑/作者", "1", old)
        self.assertEqual(replaced["status"], "published-candidate")
        archive = self.config.state_root / "archive" / "编辑" / "作者" / target.name / f"{old}.pdf"
        self.assertEqual(hash_file(archive), old)
        accept(self.config, "编辑/作者", "1", candidate["sha256"], "人工审阅者", "实际尺寸、原稿语义及排版稿终检完成")
        target.write_bytes(b"after acceptance")
        with self.assertRaisesRegex(FlowError, "人工终检"):
            publish(self.config, cid, "编辑/作者", "1", hash_file(target))

    def test_publish_when_jpg_same_number_exists(self) -> None:
        probed = probe(self.config, self.manifest)
        candidate = render(self.config, self.spec, self.constraints, probed["probe_id"])
        cid = candidate["candidate_id"]
        record = Path(self.temp.name) / "review.json"
        saved = json.loads((self.config.state_root / "candidates" / cid / "candidate.json").read_text(encoding="utf-8"))
        write_json(record, {"candidate_id": cid, "output_sha256": candidate["sha256"],
            "constraints_sha256": saved["constraints_sha256"],
            "source_hashes": {self.source.name: hash_file(self.source)},
            "author_rel": "编辑/作者", "figure_number": "1", "reviewer": "测试审阅者",
            "content": {"conclusion": "approved", "evidence": ["对照原稿文字核对 N1 与 N2 连线顺序"]},
            "visual": {"conclusion": "approved", "evidence": ["按实际尺寸观察单栏图幅、线条和字形"]}})
        review(self.config, cid, record)
        (self.author / "作者-图1.jpg").write_bytes(b"existing JPEG")
        with self.assertRaisesRegex(FlowError, "JPG/JPEG"):
            publish(self.config, cid, "编辑/作者", "1")

    def test_accept_rejects_pdf_missing_cap_height(self) -> None:
        import pymupdf as fitz

        probed = probe(self.config, self.manifest)
        candidate = render(self.config, self.spec, self.constraints, probed["probe_id"])
        target = self.author / "作者-图1.pdf"
        source = Path(candidate["pdf"])
        broken = Path(self.temp.name) / "missing-cap-height.pdf"
        with fitz.open(source) as doc:
            descriptor = next(
                xref for xref in range(1, doc.xref_length())
                if doc.xref_get_key(xref, "Type") == ("name", "/FontDescriptor")
            )
            doc.xref_set_key(descriptor, "CapHeight", "null")
            doc.save(broken)
        target.write_bytes(broken.read_bytes())
        with self.assertRaisesRegex(FlowError, "/CapHeight"):
            audit_pdf_compatibility(target)
        with self.assertRaisesRegex(FlowError, "/CapHeight"):
            accept(
                self.config,
                "编辑/作者",
                "1",
                hash_file(target),
                "人工审阅者",
                "实际尺寸、原稿语义及排版稿终检完成",
            )
        result = audit_delivery_pdfs(self.delivery)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["issue_count"], 1)
        self.assertEqual(result["issues"][0]["path"], "编辑\\作者\\作者-图1.pdf")

    def test_image_only_page_ignores_unused_standard_font_resource(self) -> None:
        import pymupdf as fitz

        target = self.author / "作者-图2.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_font(fontname="helv")
            doc.save(target)
        with fitz.open(target) as doc:
            self.assertEqual(doc[0].get_texttrace(), [])
            self.assertEqual(doc[0].get_fonts(full=True)[0][2], "Type1")
        report = audit_pdf_compatibility(target)
        self.assertTrue(report["passed"])
        self.assertEqual(report["font_descriptors"], [])


if __name__ == "__main__":
    unittest.main()
