import test from 'node:test';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {pythonRuntime} from '../lib/ingest.mjs';
test('PDF gray preserves true interpolation and rejects unknown paint or unsafe output',()=>{
 execFileSync(pythonRuntime(),['-X','utf8',fileURLToPath(new URL('./pdf_vector_gray_checks.py',import.meta.url))],{stdio:'pipe'});
});
