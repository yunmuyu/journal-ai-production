import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {pythonRuntime} from '../lib/ingest.mjs';
const script=new URL('../scripts/prepare_matplotlib_svg.py',import.meta.url);
test('outlined SVG labels decode without changing real curve paths',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-svg-'));
 try{
  const source=dir+'/source.svg';
  fs.writeFileSync(source,`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="120pt" height="100pt" viewBox="0 0 120 100"><g id="figure_1"><g id="axes_1"><g id="patch_2"><path d="M 20 80 L 110 80 L 110 10 L 20 10 z"/></g><g id="matplotlib.axis_1"><g id="xtick_1"><g><use xlink:href="#m1" x="30" y="80"/></g><g id="text_1"><g transform="translate(28 90) scale(0.1 -0.1)"><use xlink:href="#DejaVuSans-2212"/><use xlink:href="#DejaVuSans-32"/></g></g></g></g><g id="line2d_9"><path d="M 25 60 L 75 40 L 105 20" style="fill:none;stroke:#000"/></g></g></g></svg>`);
  execFileSync(pythonRuntime(),['-X','utf8',script.pathname.replace(/^\//,''),source,dir]);
  const report=JSON.parse(fs.readFileSync(dir+'/prepared.json'));
  assert.equal(report.panels.length,1);
  assert.equal(report.panels[0].labels[0].text,'-2');
  assert.equal(report.panels[0].labels[0].role,'x-tick');
  assert.equal(report.panels[0].plotWidthMm,62);
  assert.match(fs.readFileSync(report.panels[0].svg,'utf8'),/M 25 60 L 75 40 L 105 20/);
  assert.equal(report.curveGeometryPreserved,true);
 }finally{fs.rmSync(dir,{recursive:true});}
});
