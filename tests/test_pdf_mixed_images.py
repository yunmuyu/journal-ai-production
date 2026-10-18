import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageCms
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, ContentStream, DecodedStreamObject, EncodedStreamObject,
                           BooleanObject, DictionaryObject, FloatObject, NameObject, NumberObject)

spec = importlib.util.spec_from_file_location('normalizer', Path(__file__).resolve().parents[1] / 'scripts/normalize_svg_color.py')
normalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalizer)


def stream(data, **entries):
    obj = DecodedStreamObject()
    obj.set_data(data)
    for key, value in entries.items():
        obj[NameObject('/' + key)] = value
    return obj


class MixedPdfImages(unittest.TestCase):
    def fixture(self, filename, color_space='/DeviceRGB', icc=False, invalid=None):
        writer = PdfWriter()
        page = writer.add_blank_page(200, 180)
        colors = NameObject(color_space)
        if icc:
            profile = stream(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes(), N=NumberObject(3))
            colors = ArrayObject([NameObject('/ICCBased'), writer._add_object(profile)])
        image = stream(bytes([255, 0, 0, 0, 0, 255]) if color_space != '/DeviceGray' else bytes([20, 220]),
                       Type=NameObject('/XObject'), Subtype=NameObject('/Image'),
                       Width=NumberObject(2), Height=NumberObject(1),
                       ColorSpace=colors, BitsPerComponent=NumberObject(8))
        if invalid:
            image[NameObject(invalid)] = ArrayObject([NumberObject(1), NumberObject(0)])
        ref = writer._add_object(image)
        form = stream(b'q 0 1 -1 0 30 10 cm /Im Do Q',
                      Type=NameObject('/XObject'), Subtype=NameObject('/Form'),
                      BBox=ArrayObject(map(NumberObject, [0, 0, 40, 40])),
                      Resources=DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Im'): ref})}))
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject({
            NameObject('/Im'): ref, NameObject('/Fm'): writer._add_object(form)}),
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        page[NameObject('/Contents')] = writer._add_object(stream(
            b'0.7 0.2 0.1 rg 5 6 20 15 re f BT /F1 8 Tf 20 150 Td (Editable label) Tj ET q 10 10 60 50 re W n 40 0 0 30 20 25 cm /Im Do Q /Fm Do q 20 0 0 10 70 50 cm /Im Do Q'))
        writer.write(filename)

    def test_rgb_clipping_transform_form_and_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            self.fixture(source)
            before = source.read_bytes()
            evidence = normalizer.inspect_pdf(source, dest, True)
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(evidence['geometryPreserved'])
            self.assertEqual(evidence['geometryHashBefore'], evidence['geometryHashAfter'])
            self.assertEqual(evidence['embeddedImages'], 1)
            self.assertEqual(len(evidence['imageConversions']), 1)
            reader = PdfReader(dest)
            page = reader.pages[0]
            image = page['/Resources']['/XObject']['/Im'].get_object()
            self.assertEqual(image['/ColorSpace'], '/DeviceGray')
            self.assertEqual(image.get_data(), bytes([76, 29]))
            self.assertEqual((image['/Width'], image['/Height']), (2, 1))
            nested = page['/Resources']['/XObject']['/Fm']['/Resources']['/XObject']['/Im']
            self.assertEqual(nested.indirect_reference, image.indirect_reference)
            original = PdfReader(source)
            def geometry(p, r):
                return [(a, op) for a, op in ContentStream(p.get_contents(), r).operations if op not in [b'rg', b'RG', b'k', b'K']]
            self.assertEqual(geometry(original.pages[0], original), geometry(page, reader))

    def masked_fixture(self, filename, decode=(1, 0)):
        self.fixture(filename)
        writer = PdfWriter(clone_from=filename)
        page = writer.pages[0]
        mask = stream(b'\xa0\x40', Type=NameObject('/XObject'), Subtype=NameObject('/Image'),
                      Width=NumberObject(3), Height=NumberObject(2),
                      ImageMask=BooleanObject(True), BitsPerComponent=NumberObject(1),
                      Decode=ArrayObject(map(NumberObject, decode)))
        mask_ref = writer._add_object(mask.flate_encode())
        page['/Resources']['/XObject']['/Im'][NameObject('/Mask')] = mask_ref
        page['/Resources']['/XObject'][NameObject('/Stencil')] = mask_ref
        page[NameObject('/Contents')] = writer._add_object(stream(
            page.get_contents().get_data() + b' q 12 0 0 8 90 90 cm /Stencil Do Q'))
        writer.write(filename)

    def test_explicit_binary_mask_preserves_pixels_decode_sharing_and_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            for decode in [(0, 1), (1, 0)]:
                with self.subTest(decode=decode):
                    self.masked_fixture(source, decode)
                    original = source.read_bytes()
                    evidence = normalizer.inspect_pdf(source, dest, True)
                    self.assertEqual(source.read_bytes(), original)
                    page = PdfReader(dest).pages[0]
                    image = page['/Resources']['/XObject']['/Im']
                    mask = image['/Mask']
                    self.assertEqual(image.get_data(), bytes([76, 29]))
                    self.assertEqual(image['/ColorSpace'], '/DeviceGray')
                    self.assertEqual(mask.get_data(), b'\xa0\x40')
                    self.assertEqual(mask['/Decode'], list(decode))
                    self.assertEqual((mask['/Width'], mask['/Height']), (3, 2))
                    self.assertTrue(mask['/ImageMask'].value)
                    self.assertNotIn('/ColorSpace', mask)
                    self.assertEqual(mask.indirect_reference,
                                     page['/Resources']['/XObject']['/Stencil'].indirect_reference)
                    self.assertEqual(image.indirect_reference,
                                     page['/Resources']['/XObject']['/Fm']['/Resources']['/XObject']['/Im'].indirect_reference)
                    self.assertEqual(evidence['geometryHashBefore'], evidence['geometryHashAfter'])

    def test_invalid_binary_mask_must_not_silently_become_opaque(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            for key, value in [('/Decode', ArrayObject(map(NumberObject, [0, 0]))),
                               ('/BitsPerComponent', NumberObject(8)),
                               ('/ImageMask', BooleanObject(False)),
                               ('/ImageMask', NumberObject(1)),
                               ('/ColorSpace', NameObject('/DeviceGray')),
                               ('/Width', NumberObject(0)),
                               ('/Width', FloatObject(3.5))]:
                with self.subTest(key=key):
                    self.masked_fixture(source)
                    writer = PdfWriter(clone_from=source)
                    writer.pages[0]['/Resources']['/XObject']['/Im']['/Mask'][NameObject(key)] = value
                    writer.write(source)
                    with self.assertRaisesRegex(ValueError, 'mask|Mask'):
                        normalizer.inspect_pdf(source, dest, True)

    def test_binary_mask_default_decode_and_omitted_bit_depth_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest, second = [Path(d) / name for name in ['input.pdf', 'output.pdf', 'second.pdf']]
            self.masked_fixture(source)
            writer = PdfWriter(clone_from=source)
            mask = writer.pages[0]['/Resources']['/XObject']['/Im']['/Mask']
            del mask['/BitsPerComponent']
            del mask['/Decode']
            writer.write(source)
            normalizer.inspect_pdf(source, dest, False)
            normalizer.inspect_pdf(dest, second, True)
            image = PdfReader(second).pages[0]['/Resources']['/XObject']['/Im']
            self.assertEqual(image.get_data(), bytes([76, 29]))
            self.assertEqual(image['/Mask'].get_data(), b'\xa0\x40')
            self.assertNotIn('/Decode', image['/Mask'])
            self.assertNotIn('/BitsPerComponent', image['/Mask'])

    def test_device_aliases_q_restore_and_form_local_scope(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            self.fixture(source)
            writer = PdfWriter(clone_from=source)
            page = writer.pages[0]
            page['/Resources'][NameObject('/ColorSpace')] = DictionaryObject({NameObject('/Alias'): NameObject('/DeviceRGB')})
            form = page['/Resources']['/XObject']['/Fm']
            form['/Resources'][NameObject('/ColorSpace')] = DictionaryObject({NameObject('/Alias'): NameObject('/DeviceGray')})
            form.set_data(b'/Alias cs 0.5 scn 1 2 3 4 re f')
            page[NameObject('/Contents')] = writer._add_object(stream(
                b'/Alias cs 1 0 0 scn 0 0 1 1 re f q /DeviceGray cs 0.5 sc 1 1 1 1 re f Q 0 0 1 scn 2 2 1 1 re f /Fm Do 0 1 0 scn 3 3 1 1 re f '
                b'/Alias CS 0 0 1 SCN q /DeviceGray CS 0.25 SC Q 1 0 0 SC 4 4 1 1 re S'))
            writer.write(source)
            normalizer.inspect_pdf(source, dest, True)
            reader = PdfReader(dest)
            page = reader.pages[0]
            colors = [float(a[0]) for a, op in ContentStream(page.get_contents(), reader).operations if op == b'rg' and len(a) == 3]
            self.assertEqual([round(x * 255) for x in colors], [0, 76, 0, 128, 29, 150])
            strokes = [float(a[0]) for a, op in ContentStream(page.get_contents(), reader).operations if op == b'RG']
            self.assertEqual([round(x * 255) for x in strokes], [0, 29, 0, 64, 76])
            form = page['/Resources']['/XObject']['/Fm']
            form_colors = [float(a[0]) for a, op in ContentStream(form, reader).operations if op == b'rg']
            self.assertEqual([round(x * 255) for x in form_colors], [0, 128])

    def test_bad_alias_component_counts_and_pattern_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            for space, operands in [(NameObject('/DeviceRGB'), b'1 0 scn'),
                                    (NameObject('/DeviceGray'), b'1 0 0 scn'),
                                    (ArrayObject([NameObject('/Pattern')]), b'/P1 scn')]:
                self.fixture(source)
                writer = PdfWriter(clone_from=source)
                page = writer.pages[0]
                page['/Resources'][NameObject('/ColorSpace')] = DictionaryObject({NameObject('/Alias'): space})
                if isinstance(space, ArrayObject):
                    pattern = stream(b'1 0 0 rg 0 0 1 1 re f', Type=NameObject('/Pattern'),
                                     PatternType=NumberObject(1), PaintType=NumberObject(1), TilingType=NumberObject(1),
                                     BBox=ArrayObject(map(NumberObject, [0, 0, 1, 1])),
                                     XStep=NumberObject(1), YStep=NumberObject(1), Resources=DictionaryObject())
                    page['/Resources'][NameObject('/Pattern')] = DictionaryObject({NameObject('/P1'): writer._add_object(pattern)})
                page[NameObject('/Contents')] = writer._add_object(stream(b'/Alias cs ' + operands + b' 1 2 3 4 re f'))
                writer.write(source)
                with self.assertRaisesRegex(ValueError, 'color|component|[Pp]attern'):
                    normalizer.inspect_pdf(source, dest, True)

    def test_gray_and_icc(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            self.fixture(source, color_space='/DeviceGray')
            normalizer.inspect_pdf(source, dest, True)
            self.assertEqual(PdfReader(dest).pages[0]['/Resources']['/XObject']['/Im'].get_data(), bytes([20, 220]))
            self.fixture(source, icc=True)
            evidence = normalizer.inspect_pdf(source, dest, True)
            self.assertEqual(evidence['imageConversions'][0]['iccConversion']['targetProfile'], 'sRGB')

    def test_flate_and_jpeg(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            for encoding in ['flate', 'jpeg']:
                self.fixture(source)
                reader = PdfReader(source)
                image = reader.pages[0]['/Resources']['/XObject']['/Im']
                if encoding == 'flate':
                    replacement = image.flate_encode()
                else:
                    buffer = io.BytesIO()
                    Image.new('RGB', (2, 1), (255, 0, 0)).save(buffer, 'JPEG')
                    replacement = EncodedStreamObject()
                    replacement.update(image)
                    replacement._data = buffer.getvalue()
                    replacement[NameObject('/Filter')] = NameObject('/DCTDecode')
                reader.pages[0]['/Resources']['/XObject'][NameObject('/Im')] = replacement
                writer = PdfWriter()
                writer.add_page(reader.pages[0])
                with source.open('wb') as output:
                    writer.write(output)
                normalizer.inspect_pdf(source, dest, True)
                self.assertEqual(PdfReader(dest).pages[0]['/Resources']['/XObject']['/Im']['/ColorSpace'], '/DeviceGray')

    def test_source_color_and_second_pass(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest, second = [Path(d) / name for name in ['input.pdf', 'output.pdf', 'second.pdf']]
            self.fixture(source)
            normalizer.inspect_pdf(source, dest, False)
            self.assertEqual(PdfReader(dest).pages[0]['/Resources']['/XObject']['/Im'].get_data(), bytes([255, 0, 0, 0, 0, 255]))
            evidence = normalizer.inspect_pdf(dest, second, True)
            self.assertEqual(evidence['embeddedImages'], 1)

    def test_bad_icc_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            self.fixture(source, icc=True)
            reader = PdfReader(source)
            reader.pages[0]['/Resources']['/XObject']['/Im']['/ColorSpace'][1].get_object().set_data(b'bad ICC')
            writer = PdfWriter()
            writer.add_page(reader.pages[0])
            writer.write(source)
            with self.assertRaises(Exception):
                normalizer.inspect_pdf(source, dest, True)

    def test_multiple_pages_reuse_same_image(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            self.fixture(source)
            reader = PdfReader(source)
            writer = PdfWriter()
            writer.add_page(reader.pages[0])
            writer.add_page(reader.pages[0])
            writer.write(source)
            evidence = normalizer.inspect_pdf(source, dest, True)
            result = PdfReader(dest)
            self.assertEqual(len(result.pages), 2)
            self.assertEqual(evidence['embeddedImages'], 1)
            first = result.pages[0]['/Resources']['/XObject']['/Im']
            second = result.pages[1]['/Resources']['/XObject']['/Im']
            self.assertEqual(first.indirect_reference, second.indirect_reference)

    def test_special_pixel_formats_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            for key, value, message in [('/BitsPerComponent', NumberObject(16), '8 bits'), ('/ColorSpace', NameObject('/DeviceCMYK'), 'color space unsupported')]:
                self.fixture(source)
                reader = PdfReader(source)
                reader.pages[0]['/Resources']['/XObject']['/Im'][NameObject(key)] = value
                writer = PdfWriter()
                writer.add_page(reader.pages[0])
                writer.write(source)
                with self.assertRaisesRegex(ValueError, message):
                    normalizer.inspect_pdf(source, dest, True)

    def test_unverified_decode_and_masks_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / 'input.pdf', Path(d) / 'output.pdf'
            for key in ['/Decode', '/SMask', '/Mask']:
                self.fixture(source, invalid=key)
                with self.assertRaisesRegex(ValueError, 'Decode|mask|transparency'):
                    normalizer.inspect_pdf(source, dest, True)


if __name__ == '__main__':
    unittest.main()
