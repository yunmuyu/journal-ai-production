import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {pythonRuntime} from '../lib/ingest.mjs';

test('final PDF audit uses painted effective stroke width and ignores filled marks',()=>{
 const python=pythonRuntime();
 const script=[
  'import importlib.util,sys,tempfile',
  'from pathlib import Path',
  'from pypdf import PdfWriter',
  'from pypdf.generic import DecodedStreamObject,NameObject,DictionaryObject,ArrayObject,NumberObject,FloatObject',
  'from PIL import Image',
  'import pypdfium2 as pdfium',
  'spec=importlib.util.spec_from_file_location("audit_pdf",sys.argv[1]);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)',
  'def make_pdf(where,commands):',
  ' writer=PdfWriter();page=writer.add_blank_page(width=72,height=72);stream=DecodedStreamObject();stream.set_data(commands.encode());page[NameObject("/Contents")]=writer._add_object(stream)',
  ' with where.open("wb") as handle:writer.write(handle)',
  'def check(directory,name,commands,expected):',
  ' pdf=directory/(name+".pdf");native=directory/(name+".png");preview=directory/(name+"-preview.png");make_pdf(pdf,commands)',
  ' doc=pdfium.PdfDocument(str(pdf));doc[0].render(scale=300/72).to_pil().convert("RGB").save(native);doc.close()',
  ' result=audit.audit(str(pdf),str(native),str(preview),"vector-reletter")',
  ' assert result["strokeAudit"]["ok"] is expected,(name,result["strokeAudit"])',
  ' assert result["ok"] is expected,(name,result)',
  ' return result',
  'with tempfile.TemporaryDirectory() as temporary:',
  ' directory=Path(temporary)',
  ' good=check(directory,"scaled-good","q 2 0 0 2 0 0 cm 0.25 w 10 10 m 30 10 l S Q 10 20 m 30 20 l f",True)',
  ' bad=check(directory,"thick","q 2 0 0 2 0 0 cm 0.5 w 10 10 m 30 10 l S Q",False)',
  ' assert abs(bad["strokeAudit"]["maxWidthPt"]-1)<1e-6',
  ' assert audit.audit(str(directory/"thick.pdf"),str(directory/"thick.png"),str(directory/"default-preview.png"))["ok"] is False',
  ' image_route=audit.audit(str(directory/"thick.pdf"),str(directory/"thick.png"),str(directory/"image-preview.png"),"image")',
  ' assert image_route["ok"] and image_route["strokeAudit"] is None',
  ' directional=check(directory,"nonuniform","q 2 0 0 1 0 0 cm 0.5 w 10 10 m 30 10 l S 10 10 m 10 30 l S Q",False)',
  ' assert directional["strokeAudit"]["minWidthPt"]==0.5 and directional["strokeAudit"]["maxWidthPt"]==1',
  ' curved=check(directory,"nonuniform-curve","q 2 0 0 1 0 0 cm 0.5 w 10 10 m 20 10 20 30 30 30 c S Q",False)',
  ' assert curved["strokeAudit"]["nonUniformCurvesSampled"]==1',
  ' filled=check(directory,"filled-marker","10 10 m 30 10 l 20 30 l h f",True)',
  ' assert filled["strokeAudit"]["strokeSegments"]==0 and filled["strokeAudit"]["filledOnlyPaths"]==1',
  ' assert "filled outlines" in filled["strokeAudit"]["scope"]',
  ' form_pdf=directory/"form.pdf";writer=PdfWriter();page=writer.add_blank_page(width=72,height=72)',
  ' form=DecodedStreamObject();form.set_data(b"10 10 m 30 10 l S");form[NameObject("/Type")]=NameObject("/XObject");form[NameObject("/Subtype")]=NameObject("/Form");form[NameObject("/BBox")]=ArrayObject([NumberObject(0),NumberObject(0),NumberObject(72),NumberObject(72)])',
  ' resources=DictionaryObject({NameObject("/XObject"):DictionaryObject({NameObject("/F1"):writer._add_object(form)}),NameObject("/ExtGState"):DictionaryObject({NameObject("/GS1"):DictionaryObject({NameObject("/LW"):FloatObject(0.25)})})});page[NameObject("/Resources")]=resources',
  ' content=DecodedStreamObject();content.set_data(b"q 2 0 0 2 0 0 cm /GS1 gs /F1 Do Q");page[NameObject("/Contents")]=writer._add_object(content)',
  ' with form_pdf.open("wb") as handle:writer.write(handle)',
  ' form_result=audit.stroke_audit(__import__("pypdf").PdfReader(str(form_pdf)))',
  ' assert form_result["ok"] and form_result["minWidthPt"]==0.5,form_result',
  ' print("effective-stroke-audit-ok")'
 ].join('\n');
 const output=execFileSync(python,['-c',script,fileURLToPath(new URL('../production-runtime/scripts/audit_pdf.py',import.meta.url))],{encoding:'utf8',windowsHide:true});
 assert.equal(output.trim(),'effective-stroke-audit-ok');
});
