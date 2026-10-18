import importlib.util,unittest,tempfile
from pathlib import Path
from pypdf import PdfWriter,PdfReader
from pypdf.generic import DecodedStreamObject,NameObject as N,NumberObject as I,FloatObject as F,ArrayObject as A,DictionaryObject as D
ROOT=Path(__file__).resolve().parents[1]
class EffectiveDashes(unittest.TestCase):
 def test_extgstate_dash_uses_the_same_validation_as_content_operator(self):
  for prefix in ['', 'production-runtime/']:
   spec=importlib.util.spec_from_file_location('pdf_dash',ROOT/(prefix+'scripts/audit_pdf.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   for pattern,phase in [([-3,2],0),([0,0],0),([3,2],-1)]:
    with tempfile.TemporaryDirectory()as folder:
     path=Path(folder)/'bad-dash.pdf';w=PdfWriter();p=w.add_blank_page(72,72)
     state=D({N('/D'):A([A(map(I,pattern)),I(phase)])})
     p[N('/Resources')]=D({N('/ExtGState'):D({N('/G'):state})})
     content=DecodedStreamObject();content.set_data(b'0.5 w /G gs 0 0 m 10 0 l S');p[N('/Contents')]=w._add_object(content);w.write(path)
     with self.assertRaises(ValueError):m.stroke_audit(PdfReader(path))
 def test_nested_form_and_page_matrices_report_final_pt(self):
  for prefix in ['', 'production-runtime/']:
   spec=importlib.util.spec_from_file_location('pdf_dash',ROOT/(prefix+'scripts/audit_pdf.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   with tempfile.TemporaryDirectory()as folder:
    path=Path(folder)/'dashed.pdf';w=PdfWriter();p=w.add_blank_page(72,72);form=DecodedStreamObject();form.set_data(b'5 w [30 20] 0 d 0 0 m 100 0 l S');form[N('/Subtype')]=N('/Form');form[N('/BBox')]=A([I(0),I(0),I(100),I(100)]);form[N('/Matrix')]=A(map(F,[.2,0,0,.2,0,0]));p[N('/Resources')]=D({N('/XObject'):D({N('/F'):w._add_object(form)})});content=DecodedStreamObject();content.set_data(b'q .5 0 0 .5 0 0 cm /F Do Q');p[N('/Contents')]=w._add_object(content);w.write(path)
    result=m.stroke_audit(PdfReader(path));self.assertTrue(result['ok']);self.assertEqual(result['dashPatterns'][0]['lengthsPt'],[3,2])
if __name__=='__main__':unittest.main()
