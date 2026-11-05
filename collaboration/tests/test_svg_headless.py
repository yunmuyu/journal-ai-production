import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'batch' / 'svg_headless.py'
sys.path.insert(0, str(MODULE.parent))
spec = importlib.util.spec_from_file_location('svg_headless', MODULE)
svg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = svg
spec.loader.exec_module(svg)
SIMPLE = b'<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="40mm" viewBox="0 0 80 40"><!-- credit retained --><path id="data" d="M0 0L20 30" stroke="red"/><text font-family="Arial" font-size="8" x="2" y="4">Voltage</text></svg>'

class HeadlessTests(unittest.TestCase):
    def test_family_only_preserves_path_size_and_comment(self):
        output, report = svg.transform(SIMPLE, {'Arial': 'Times New Roman'})
        self.assertIn(b'Times New Roman', output)
        for content in [b'M0 0L20 30', b'font-size="8"', b'credit retained', b'stroke="red"']:
            self.assertIn(content, output)
        self.assertTrue(report['requiresInkRemeasurement'])
        self.assertFalse(report['fontSizeChanged'])

    def test_inline_style_family(self):
        source = SIMPLE.replace(b'font-family="Arial"', b'style="font-family:Arial;fill:#123456"')
        output, _ = svg.transform(source, {'Arial': 'Test Font'})
        self.assertIn(b'font-family:Test Font', output)
        self.assertIn(b'fill:#123456', output)

    def test_unknown_family_is_not_inferred(self):
        output, report = svg.transform(SIMPLE, {'Helvetica': 'Test Font'})
        self.assertIn(b'Arial', output)
        self.assertEqual(report['changedFamilies'], 0)

    def test_complex_or_unsafe_inputs_rejected(self):
        for extra in [b'<style>text {font: 8px Arial}</style>', b'<script/>', b'<foreignObject/>', b'<image href="external.png"/>',
                      b'<text><tspan>x</tspan></text>', b'<use href="https://example.invalid/a.svg#x"/>',
                      b'<rect onload="alert(1)"/>', b'<path id="data" d="M0 0"/>']:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                svg.transform(SIMPLE.replace(b'</svg>', extra + b'</svg>'), {'Arial': 'Test'})

    def test_doctype_and_stylesheet_rejected(self):
        for prefix in [b'<!DOCTYPE svg>', b'<!ENTITY e SYSTEM "secret">', b'<?xml-stylesheet href="remote.css"?>']:
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                svg.transform(prefix + SIMPLE, {'Arial': 'Test'})

    def test_complex_text_attribute_rejected(self):
        with self.assertRaises(ValueError):
            svg.transform(SIMPLE.replace(b'font-size="8"', b'font-size="8" textLength="10"'), {'Arial': 'Test'})

    def test_font_css_injection_rejected(self):
        with self.assertRaises(ValueError):
            svg.transform(SIMPLE, {'Arial': 'Test;fill:red'})

    def test_no_editable_text_redirects_to_existing_adapter(self):
        with self.assertRaisesRegex(ValueError, 'outlined-source adapter'):
            svg.transform(b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg>', {'Arial': 'Test'})

    def job(self, directory, name='a'):
        path = directory / f'{name}.svg'
        path.write_bytes(SIMPLE)
        return {'id': name, 'source': str(path), 'sourceHash': svg.sha(SIMPLE), 'fontFamilyMap': {'Arial': 'Test'}}

    def test_preserves_original_and_reuses_only_verified_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); job = self.job(root)
            first = svg.prepare(job, str(root / 'cache'))
            second = svg.prepare(job, str(root / 'cache'))
            self.assertFalse(first['cached']); self.assertTrue(second['cached'])
            self.assertEqual(Path(job['source']).read_bytes(), SIMPLE)
            self.assertFalse(second['productionAccepted'])

    def test_output_and_manifest_tampering_cannot_self_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); job = self.job(root)
            first = svg.prepare(job, str(root / 'cache')); output = Path(first['output'])
            output.write_bytes(b'tampered')
            report_file = output.with_name('prepared.json'); report = json.loads(report_file.read_text())
            report['outputHash'] = svg.sha(b'tampered'); report_file.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'Cached SVG changed'):
                svg.prepare(job, str(root / 'cache'))
            self.assertEqual(output.read_bytes(), b'tampered')

    def test_hash_mismatch_is_isolated_in_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); good = self.job(root, 'good'); bad = self.job(root, 'bad'); bad['sourceHash'] = '0' * 64
            result = svg.prepare_batch([bad, good], str(root / 'cache'), workers=1)
            self.assertEqual([r['status'] for r in result], ['blocked', 'prepared-for-native-review'])

    def test_real_process_pool_isolates_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jobs = [self.job(root, str(i)) for i in range(3)]; jobs[1]['sourceHash'] = '0' * 64
            result = svg.prepare_batch(jobs, str(root / 'cache'), workers=2)
            self.assertEqual([r['status'] for r in result], ['prepared-for-native-review', 'blocked', 'prepared-for-native-review'])
            self.assertEqual([r['id'] for r in result], ['0', '1', '2'])

    def test_concurrency_and_duplicate_ids_validated(self):
        for workers in [0, 9, 1.5, True]:
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                svg.prepare_batch([], 'unused', workers)
        with self.assertRaises(ValueError):
            svg.prepare_batch([{'id': 'a'}, {'id': 'a'}], 'unused', 1)

if __name__ == '__main__':
    unittest.main()
