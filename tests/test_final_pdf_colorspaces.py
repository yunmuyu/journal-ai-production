import importlib.util,sys,tempfile,unittest
from pathlib import Path
from pypdf import PdfWriter
from PIL import ImageCms
from pypdf.generic import NameObject as N,NumberObject as I,ArrayObject as A,DictionaryObject as D,DecodedStreamObject,ByteStringObject
ROOT=Path(__file__).resolve().parents[1]
def stream(data,attrs):
 s=DecodedStreamObject();s.set_data(data)
 for k,v in attrs.items():s[N(k)]=v
 return s
def fixture(path,kind,colored=False):
 w=PdfWriter();page=w.add_blank_page(20,20)
 if kind=='icc':
  profile=stream(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes(),{'/N':I(3),'/Alternate':N('/DeviceRGB')});cs=A([N('/ICCBased'),w._add_object(profile)]);data=bytes([255,0,0]if colored else[30,30,30]);bits=8
 else:
  cs=A([N('/Indexed'),N('/DeviceRGB'),I(1),ByteStringObject(bytes([20,20,20]+([255,0,0]if colored else[60,60,60])))]);data=b'\x80';bits=1
 image=stream(data,{'/Type':N('/XObject'),'/Subtype':N('/Image'),'/Width':I(1),'/Height':I(1),'/BitsPerComponent':I(bits),'/ColorSpace':cs})
 page[N('/Resources')]=D({N('/XObject'):D({N('/Im'):w._add_object(image.flate_encode())})});page[N('/Contents')]=w._add_object(stream(b'q 10 0 0 10 0 0 cm /Im Do Q',{}));w.write(path)
class ColorSpaces(unittest.TestCase):
 def test_icc_and_indexed_are_audited_without_modifying_pdf(self):
  for prefix in ['', 'production-runtime/']:
   spec=importlib.util.spec_from_file_location('audit_spaces',ROOT/(prefix+'scripts/audit_color.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   with tempfile.TemporaryDirectory()as folder:
    p=Path(folder)/'image.pdf'
    for kind in ['icc','indexed']:
     for colored in [False,True]:
      with self.subTest(prefix=prefix,kind=kind,colored=colored):
       fixture(p,kind,colored);before=p.read_bytes();self.assertEqual(m.objects(p,True)['ok'],not colored);self.assertEqual(p.read_bytes(),before)
if __name__=='__main__':unittest.main()
