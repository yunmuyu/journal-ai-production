import importlib.util
import tempfile
import unittest
from unittest.mock import patch
import json
import sys
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject


SCRIPT = Path(__file__).resolve().parents[1] / 'production-runtime' / 'scripts' / 'audit_color.py'
SPEC = importlib.util.spec_from_file_location('production_audit_color', SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def audit(content):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(content)
    page[NameObject('/Contents')] = writer._add_object(stream)
    with tempfile.TemporaryDirectory() as directory:
        pdf = Path(directory) / 'ink.pdf'
        with pdf.open('wb') as out:
            writer.write(out)
        return AUDIT.editable_text_ink(pdf)


class TextInkTest(unittest.TestCase):
    def test_omitted_route_cannot_skip_editable_text_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / 'request.json'
            request.write_text(json.dumps({'ruleVersion': AUDIT.RULE, 'policy': 'source-color'}))
            with patch.object(sys, 'argv', ['audit_color.py', str(request)]):
                with self.assertRaisesRegex(ValueError, 'route'):
                    AUDIT.main()

    def test_black_text_is_accepted_without_grayscale_switch(self):
        result = audit(b'0 0 0 rg BT (X) Tj ET')
        self.assertTrue(result['ok'])
        self.assertEqual(result['textShows'], 1)

    def test_gray_and_colored_text_are_rejected(self):
        for operator in (b'0.5 g', b'1 0 0 rg', b'0 0 0 0.5 k'):
            with self.subTest(operator=operator):
                result = audit(operator + b' BT (X) Tj ET')
                self.assertFalse(result['ok'])
                self.assertEqual(result['nonBlackTextShows'], 1)

    def test_unsupported_text_color_cannot_pass_silently(self):
        result = audit(b'/Pattern cs /P scn BT (X) Tj ET')
        self.assertFalse(result['ok'])
        self.assertEqual(result['unknownTextShows'], 1)


if __name__ == '__main__':
    unittest.main()
