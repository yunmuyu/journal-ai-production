// Optional snapshot packaging of an existing current-delivery manifest.
// Never discovers latest files by mtime and never changes production/review state.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const hash=data=>createHash('sha256').update(data).digest('hex');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const safe=value=>String(value).replace(/[<>:"|?*/\\]/g,'_').replace(/[. ]+$/,'');
export function planCurrentPackage({manifestPath,articleId,numbers}){
 const manifestBytes=fs.readFileSync(manifestPath),manifest=JSON.parse(manifestBytes.toString('utf8').replace(/^\uFEFF/,'')),root=fs.realpathSync(path.dirname(manifestPath));
 if(path.basename(root)!=='当前'||path.basename(manifestPath)!=='manifest.json'||Object.hasOwn(manifest,'archiveMode')||Object.hasOwn(manifest,'retainedInCurrent'))throw Error('authoritative_current_manifest_required');
 if(manifest.schema!=='jfw-current-delivery-v1'||!Array.isArray(manifest.items)||!manifest.items.length)throw Error('current_delivery_manifest_required');
 if(!articleId||typeof articleId!=='string')throw Error('explicit_article_id_required');
 if(!Array.isArray(manifest.issues)||manifest.issues.length)throw Error('unresolved_delivery_manifest_issues');
 let items=manifest.items.filter(item=>item.articleId===articleId);
 if(!items.length)throw Error('article_not_in_current_delivery');
 const authors=new Set(items.map(item=>item.author));
 if(authors.size!==1||[...authors].some(a=>typeof a!=='string'||!a.trim()||/待确认|未知|unnamed/i.test(a)))throw Error('confirmed_author_identity_required');
 if(items.some(x=>typeof x.number!=='string'||!/^\d+(?:[.-]\d+)*[a-z]?$/.test(x.number)))throw Error('invalid_current_figure_number');
 if(new Set(items.map(x=>x.number)).size!==items.length)throw Error('duplicate_current_figure_number');
 if(numbers!==undefined){
  if(!Array.isArray(numbers)||!numbers.length||numbers.some(n=>typeof n!=='string'||!n)||new Set(numbers).size!==numbers.length)throw Error('explicit_figure_numbers_invalid');
  if(numbers.some(n=>!items.some(i=>i.number===n)))throw Error('requested_current_figure_missing');
  items=items.filter(i=>numbers.includes(i.number));
 }
 const names=new Set();
 const files=items.map(item=>{
  if(!['review','approved'].includes(item.state))throw Error('unsupported_delivery_state');
  if(typeof item.relative!=='string'||path.isAbsolute(item.relative))throw Error('unsafe_delivery_path');
  const source=fs.realpathSync(path.resolve(root,item.relative)),relative=path.relative(root,source);
  if(!relative||relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative))throw Error('unsafe_delivery_path');
  if(!fs.statSync(source).isFile()||!['.pdf','.jpg','.jpeg','.png','.tif','.tiff'].includes(path.extname(source).toLowerCase()))throw Error('unsupported_delivery_file');
  if(hash(fs.readFileSync(source))!==item.sha256)throw Error('current_delivery_hash_changed');
  const name=(item.state==='approved'?'排版定稿/':'待终检/')+safe(item.author)+'-图'+safe(item.number)+path.extname(source).toLowerCase();
  if(names.has(name.toLowerCase()))throw Error('duplicate_package_filename');names.add(name.toLowerCase());
  return {number:item.number,name,state:item.state,sha256:item.sha256,source};
 });
 files.sort((a,b)=>a.number.localeCompare(b.number,'zh',{numeric:true}));
 return {version:1,type:'optional-current-delivery-package',author:[...authors][0],articleId,
  manifestSha256:hash(manifestBytes),scope:numbers?'explicit-selection':'current-manifest-article',files,
  note:'仅收集当前交付清单版本。待终检不等于验收；未推断Word全套图号，也未修改工作台或验收状态。'};
}
const zipCode=`import io,json,sys,zipfile,hashlib,pathlib
r=json.load(sys.stdin)
b=io.BytesIO()
with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for f in r['files']:
  content=pathlib.Path(f['source']).read_bytes()
  if hashlib.sha256(content).hexdigest()!=f['sha256']: raise ValueError('current_delivery_hash_changed')
  z.writestr(f['name'],content)
 public={**r,'files':[{k:v for k,v in f.items() if k!='source'} for f in r['files']]}
 z.writestr('交付清单.json',json.dumps(public,ensure_ascii=False,indent=2))
sys.stdout.buffer.write(b.getvalue())`;
export function packageCurrentDelivery(options){
 const plan=planCurrentPackage(options),output=path.resolve(options.output);
 if(path.extname(output).toLowerCase()!=='.zip'||fs.existsSync(output))throw Error('new_zip_destination_required');
 const bytes=execFileSync(options.python,["-c",zipCode],{input:JSON.stringify(plan),maxBuffer:128*1024*1024,windowsHide:true});
 if(hash(fs.readFileSync(options.manifestPath))!==plan.manifestSha256||plan.files.some(f=>hash(fs.readFileSync(f.source))!==f.sha256))throw Error('delivery_changed_during_packaging');
 fs.writeFileSync(output,bytes,{flag:'wx'});
 return {output,sha256:hash(bytes),articleId:plan.articleId,author:plan.author,files:plan.files.map(({source,...f})=>f),stateChanged:false};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const [input]=process.argv.slice(2);if(!input)throw Error('Usage: package-current-delivery.mjs request.json');console.log(JSON.stringify(packageCurrentDelivery(read(input))));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
