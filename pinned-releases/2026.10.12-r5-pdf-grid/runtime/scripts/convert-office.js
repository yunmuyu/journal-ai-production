var fso=new ActiveXObject('Scripting.FileSystemObject');
function readUtf8(p){var s=new ActiveXObject('ADODB.Stream');s.Type=2;s.Charset='utf-8';s.Open();s.LoadFromFile(p);var t=s.ReadText();s.Close();return t;}
function writeUtf8(p,t){var s=new ActiveXObject('ADODB.Stream');s.Type=2;s.Charset='utf-8';s.Open();s.WriteText(t);s.SaveToFile(p,2);s.Close();}
    function quote(s) {var out=String.fromCharCode(34),bs=String.fromCharCode(92);s=String(s);for(var i=0;i<s.length;i++){var n=s.charCodeAt(i);if(n===34||n===92)out+=bs+s.charAt(i);else if(n<32)out+=bs+'u'+('0000'+n.toString(16)).slice(-4);else out+=s.charAt(i);}return out+String.fromCharCode(34);}
    function stringify(v) {
        if(v === null || v === undefined) return 'null';
        if(typeof v === 'string') return quote(v);
        if(typeof v === 'number') return isFinite(v)?String(v):'null';
        if(typeof v === 'boolean') return v?'true':'false';
        var a=[],i,k;
        if(v instanceof Array){for(i=0;i<v.length;i++)a.push(stringify(v[i]));return '['+a.join(',')+']';}
        for(k in v)if(v.hasOwnProperty(k))a.push(quote(k)+':'+stringify(v[k]));
        return '{'+a.join(',')+'}';
    }
var json=stringify;
var req=eval('('+readUtf8(WScript.Arguments(0)).replace(/^\uFEFF/,'')+')');
var ext=fso.GetExtensionName(req.input).toLowerCase(),app=null,doc=null,pp=null,pres=null,security=null,out=[],result,start=new Date().getTime();
function output(name,scope){var p=fso.BuildPath(req.directory,name);return {path:p,kind:'pdf',scope:scope};}
var stage='start';
try{
 if(ext==='doc'||ext==='docx'){
  app=new ActiveXObject('Word.Application');security=app.AutomationSecurity;app.AutomationSecurity=3;doc=app.Documents.Open(req.input,false,true,false);
  if(ext==='doc'){var converted=fso.BuildPath(req.directory,'converted.docx');doc.SaveAs2(converted,16);out.push({path:converted,kind:'docx'});}
  var o=output('document.pdf','whole_document');doc.ExportAsFixedFormat(o.path,17);out.push(o);
 }else if(ext==='emf'||ext==='wmf'){
  app=new ActiveXObject('PowerPoint.Application');doc=app.Presentations.Add(false);var slide=doc.Slides.Add(1,12);var picture=slide.Shapes.AddPicture(req.input,false,true,0,0,-1,-1);doc.PageSetup.SlideWidth=picture.Width;doc.PageSetup.SlideHeight=picture.Height;var o=output('metafile.pdf','metafile');doc.SaveAs(o.path,32);out.push(o);
 }else if(/^ppt[xm]?$/.test(ext)){
  app=new ActiveXObject('PowerPoint.Application');security=app.AutomationSecurity;app.AutomationSecurity=3;doc=app.Presentations.Open(req.input,true,false,false);
  var o=output('slides.pdf','all_slides');o.pages=doc.Slides.Count;doc.SaveAs(o.path,32);out.push(o);
 }else if(/^vsd[xm]?$/.test(ext)){
  app=new ActiveXObject('Visio.InvisibleApp');doc=app.Documents.OpenEx(req.input,2+64+128);var o=output('drawing.pdf','all_pages');o.pages=doc.Pages.Count;doc.ExportAsFixedFormat(1,o.path,1,0);out.push(o);
 }else if(/^xls[xmb]?$/.test(ext)){
  stage='excel_open';app=new ActiveXObject('Excel.Application');security=app.AutomationSecurity;app.AutomationSecurity=3;doc=app.Workbooks.Open(req.input,0,true);pp=new ActiveXObject('PowerPoint.Application');var index=0;
  for(var i=1;i<=doc.Charts.Count;i++){var ch=doc.Charts.Item(i);var o=output('chart-'+(++index)+'.pdf','chart_sheet');ch.ExportAsFixedFormat(0,o.path);o.sheet=ch.Name;out.push(o);}
  for(var i=1;i<=doc.Worksheets.Count;i++){var sheet=doc.Worksheets.Item(i),charts=sheet.ChartObjects();for(var j=1;j<=charts.Count;j++){
   stage='chart_activate';sheet.Activate();var ch=charts.Item(j);ch.Activate();stage='copy_picture';ch.CopyPicture(1,-4147);stage='create_slide';pres=pp.Presentations.Add(false);pres.PageSetup.SlideWidth=ch.Width;pres.PageSetup.SlideHeight=ch.Height;
   stage='paste_picture';var slide=pres.Slides.Add(1,12),shape=slide.Shapes.PasteSpecial(2).Item(1);shape.Left=0;shape.Top=0;shape.Width=ch.Width;shape.Height=ch.Height;
   var o=output('chart-'+(++index)+'.pdf','embedded_chart');o.sheet=sheet.Name;pres.SaveAs(o.path,32);pres.Close();pres=null;out.push(o);
  }}
  if(!index)throw Error('No chart objects; explicit table/data figure selection required');
 }else throw Error('Unsupported extension');
 for(var i=0;i<out.length;i++)if(!fso.FileExists(out[i].path))throw Error('Missing output '+out[i].path);
 result={ok:true,outputs:out,durationMs:new Date().getTime()-start};
}catch(e){result={ok:false,error:String(e.message||e.description||e),errorNumber:e.number,stage:stage,outputs:out,durationMs:new Date().getTime()-start};}
finally{
 if(pres)try{pres.Close();}catch(e){}
 if(doc)try{if(/^doc/.test(ext))doc.Close(0);else if(/^xls/.test(ext))doc.Close(false);else doc.Close();}catch(e){result.closeError=String(e.message);}
 if(app&&security!==null)try{app.AutomationSecurity=security;}catch(e){}
 if(app&&/^vsd/.test(ext))try{app.Quit();}catch(e){}
 writeUtf8(req.result,json(result));
}
WScript.Quit(result.ok?0:1);
