import importlib.util
from pathlib import Path
import tempfile
import unittest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject,BooleanObject,DecodedStreamObject,DictionaryObject,NameObject,NumberObject
ROOT=Path(__file__).resolve().parents[1]

def stream(data,**attrs):
 obj=DecodedStreamObject();obj.set_data(data)
 for key,value in attrs.items():obj[NameObject('/'+key)]=value
 return obj

class FinalImageMasks(unittest.TestCase):
 def fixture(self,path,kind='SMask',bad=None,rgb=False,colored=False,mask_bits=1,decode=(0,1)):
  writer=PdfWriter();page=writer.add_blank_page(20,20)
  mask=stream(b'\x80\x40'if mask_bits==1 else bytes([0,64,128,192,255,0]),Type=NameObject('/XObject'),Subtype=NameObject('/Image'),Width=NumberObject(3),Height=NumberObject(2),BitsPerComponent=NumberObject(mask_bits),Decode=ArrayObject(map(NumberObject,decode)))
  if kind=='Mask':mask[NameObject('/ImageMask')]=BooleanObject(True)
  else:mask[NameObject('/ColorSpace')]=NameObject('/DeviceGray')
  if bad=='mask-color':mask[NameObject('/ColorSpace')]=NameObject('/DeviceRGB')
  if bad=='mask-length':mask.set_data(b'')
  if bad=='unknown-filter':mask[NameObject('/Filter')]=NameObject('/RunLengthDecode')
  if bad=='nested':mask[NameObject('/SMask')]=ArrayObject()
  image=stream((bytes([255,0,0,30,30,30])if colored else bytes([20,20,20,30,30,30]))if rgb else bytes([20,30]),Type=NameObject('/XObject'),Subtype=NameObject('/Image'),Width=NumberObject(2),Height=NumberObject(1),BitsPerComponent=NumberObject(8),ColorSpace=NameObject('/DeviceRGB'if rgb else'/DeviceGray'))
  image[NameObject('/'+kind)]=writer._add_object(mask.flate_encode())
  if bad=='linked':image[NameObject('/F')]=NameObject('/external')
  if bad=='color-key':image[NameObject('/Mask')]=ArrayObject(map(NumberObject,[0,255]))
  if bad=='decode':image[NameObject('/Decode')]=ArrayObject(map(NumberObject,[0,1,0]))
  ref=writer._add_object(image.flate_encode())
  page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im'):ref,NameObject('/Shared'):ref})})
  page[NameObject('/Contents')]=writer._add_object(stream(b'q 10 0 0 10 0 0 cm /Im Do Q /Shared Do'))
  writer.write(path)
 def modules(self):
  for prefix in ['', 'production-runtime/']:
   spec=importlib.util.spec_from_file_location('audit_masks',ROOT/(prefix+'scripts/audit_color.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);yield prefix,module
 def test_native_binary_soft_and_explicit_masks_are_read_only_and_audited(self):
  with tempfile.TemporaryDirectory()as folder:
   path=Path(folder)/'masked.pdf'
   for prefix,module in self.modules():
    for kind,bits,decode in [('SMask',1,(0,1)),('SMask',8,(1,0)),('Mask',1,(1,0))]:
     with self.subTest(prefix=prefix,kind=kind,bits=bits):
      self.fixture(path,kind,mask_bits=bits,decode=decode);before=path.read_bytes();result=module.objects(path,True)
      self.assertTrue(result['ok']);self.assertEqual(path.read_bytes(),before)
      self.assertEqual(result['images'],1);self.assertEqual(result['imageMasks'],1)
      self.assertEqual(result['imageAudits'][0]['mask']['bitsPerComponent'],bits)
      self.assertEqual(result['imageAudits'][0]['mask']['decode'],list(decode))
      self.assertEqual(result['imageAudits'][0]['mask']['width'],3)
 def test_transparent_rgb_pixels_are_checked_before_composition(self):
  with tempfile.TemporaryDirectory()as folder:
   path=Path(folder)/'masked.pdf'
   for prefix,module in self.modules():
    self.fixture(path,rgb=True,colored=True);self.assertFalse(module.objects(path,True)['ok'])
    self.fixture(path,rgb=True);self.assertTrue(module.objects(path,True)['ok'])
 def test_unknown_linked_or_malformed_transparency_is_rejected(self):
  with tempfile.TemporaryDirectory()as folder:
   path=Path(folder)/'masked.pdf'
   for prefix,module in self.modules():
    for bad in ['mask-color','mask-length','nested','linked','color-key','decode','unknown-filter']:
     with self.subTest(prefix=prefix,bad=bad):
      self.fixture(path,bad=bad)
      with self.assertRaises(ValueError):module.objects(path,True)
if __name__=='__main__':unittest.main()
