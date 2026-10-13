var JFW = (function () {
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
    function read(file) {var f=new File(file);f.encoding='UTF-8';if(!f.open('r'))throw Error('Cannot read '+file);var t=f.read();f.close();if(t.charCodeAt(0)===65279)t=t.substr(1);return t;}
    function write(file,data){var f=new File(file);f.encoding='UTF-8';if(!f.open('w'))throw Error('Cannot write '+file);f.write(stringify(data));f.close();}
    function request(){return eval('('+read($.global.JFW_REQUEST)+')');}
    function bounds(v){return [Number(v[0]),Number(v[1]),Number(v[2]),Number(v[3])];}
    return {stringify:stringify,read:read,write:write,request:request,bounds:bounds};
})();
