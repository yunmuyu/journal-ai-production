import importlib.util,io,unittest
from pathlib import Path
from PIL import Image,ImageCms
class IccNormalization(unittest.TestCase):
 def test_profile_conversion_preserves_alpha_and_source_mode(self):
  for root in ['', 'production-runtime/']:
   f=Path(__file__).resolve().parents[1]/(root+'scripts/normalize_svg_color.py')
   spec=importlib.util.spec_from_file_location('normalizer',f);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   im=Image.new('RGBA',(3,2),(255,0,0,128));b=io.BytesIO();im.save(b,'PNG',icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
   out,meta=m.image_rgb(b.getvalue(),True);result=Image.open(io.BytesIO(out))
   self.assertEqual(result.size,(3,2));self.assertEqual(meta['sourceMode'],'RGBA');self.assertTrue(meta['alphaFlattenedWhite']);self.assertEqual(meta['iccConversion']['targetProfile'],'sRGB')
   self.assertEqual(result.getpixel((0,0)),(165,165,165))
   bad=io.BytesIO();im.save(bad,'PNG',icc_profile=b'not an ICC profile')
   with self.assertRaises(Exception):m.image_rgb(bad.getvalue(),True)
if __name__=='__main__':unittest.main()
