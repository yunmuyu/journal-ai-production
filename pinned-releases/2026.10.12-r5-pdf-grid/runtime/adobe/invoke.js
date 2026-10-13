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
var application=WScript.Arguments(0),script=WScript.Arguments(1),request=WScript.Arguments(2),result=WScript.Arguments(3);
var root=fso.GetParentFolderName(script).split(String.fromCharCode(92)).join('/');
var currentStage='starting';
function stage(name,extra){currentStage=name;writeUtf8(result+'.bridge.json',json({stage:name,time:new Date().getTime(),detail:extra||null}));}
try{
 stage('connecting');var app=new ActiveXObject(application==='illustrator'?'Illustrator.Application.CC.2019':'Photoshop.Application');
 stage('connected');stage('probing');if(String(app.DoJavaScript('"JFW_HEALTH_OK";'))!=='JFW_HEALTH_OK')throw Error('Script engine health probe returned unexpected value');
 stage('healthy');var lines=readUtf8(script).split(String.fromCharCode(10)),keep=[];
 for(var i=0;i<lines.length;i++)if(lines[i].indexOf('#target')!==0&&lines[i].indexOf('$.evalFile')!==0)keep.push(lines[i]);
 var prefix='$.global.JFW_ADOBE_ROOT='+json(root)+';$.global.JFW_REQUEST='+json(request)+';$.global.JFW_RESULT='+json(result)+';';
 var code=prefix+String.fromCharCode(10)+readUtf8(root+'/common.jsx')+String.fromCharCode(10)+keep.join(String.fromCharCode(10))+String.fromCharCode(10)+'"JFW_FINISHED";';
 stage('executing');var answer=app.DoJavaScript(code);stage('returned',String(answer));
 if(!fso.FileExists(result))throw Error('Adobe did not write a result');
 var data=eval('('+readUtf8(result)+')');if(!data.ok)throw Error(data.error);
 stage('complete');WScript.Quit(0);
}catch(e){stage('failed',{number:e.number,description:String(e.description||e.message||e),during:currentStage});WScript.Quit(1);}
