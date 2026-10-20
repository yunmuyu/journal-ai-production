import os
from pathlib import Path

import pymupdf as fitz
import pytest

from journal_pdf.fonts import FontRegistry
from journal_pdf.pdf_fonts import normalize_type0_font_names


def _type0_names(doc):
    return {row[3] for page in doc for row in page.get_fonts(full=True) if row[2]=='Type0'}


def _descendant_names(doc):
    names=set()
    for page in doc:
        for row in page.get_fonts(full=True):
            if row[2]!='Type0':continue
            _,value=doc.xref_get_key(row[0],'DescendantFonts')
            xref=int(value.replace('[',' ').split()[0])
            names.add(doc.xref_get_key(xref,'BaseFont')[1])
    return names


def test_normalize_type0_names_to_installed_postscript_names():
    regular = Path(os.environ.get("JFW_TEST_TNR_REGULAR", "C:/Windows/Fonts/times.ttf"))
    italic = Path(os.environ.get("JFW_TEST_TNR_ITALIC", "C:/Windows/Fonts/timesi.ttf"))
    if not regular.is_file() or not italic.is_file():
        pytest.skip("set JFW_TEST_TNR_REGULAR and JFW_TEST_TNR_ITALIC to installed test fonts")
    doc=fitz.open();page=doc.new_page()
    page.insert_font(fontname='regular',fontfile=str(regular))
    page.insert_font(fontname='italic',fontfile=str(italic))
    page.insert_text((20,40),'Regular',fontname='regular')
    page.insert_text((20,60),'Italic',fontname='italic')
    assert _type0_names(doc)=={'Times New Roman Regular','Times New Roman Italic'}

    normalize_type0_font_names(doc)

    assert _type0_names(doc)=={'TimesNewRomanPSMT','TimesNewRomanPS-ItalicMT'}
    doc.close()


def test_normalize_null_descendant_name_from_configured_role():
    profile = os.environ.get("JFW_TEST_FONT_PROFILE")
    if not profile or not Path(profile).is_file():
        pytest.skip("set JFW_TEST_FONT_PROFILE to an external production-like font profile")
    registry=FontRegistry(profile)
    measured=registry.measure('，')
    registry.prepare_document_fonts([{'measurement':measured}])
    doc=fitz.open();page=doc.new_page()
    page.insert_font(fontname='JFW_punct',fontbuffer=registry.document_fonts['punct'])
    page.insert_text((20,40),'，',fontname='JFW_punct')
    font_xref=next(row[0] for row in page.get_fonts(full=True) if row[2]=='Type0')
    descendant=int(doc.xref_get_key(font_xref,'DescendantFonts')[1].replace('[',' ').split()[0])
    doc.xref_set_key(font_xref,'BaseFont','null')
    doc.xref_set_key(descendant,'BaseFont','null')
    assert doc.xref_get_key(descendant,'BaseFont')[0]=='null'

    normalize_type0_font_names(doc,registry.postscript_names)

    assert _type0_names(doc)=={'HYa3gj'}
    assert _descendant_names(doc)=={'/HYa3gj'}
    doc.close()
    registry.close()
