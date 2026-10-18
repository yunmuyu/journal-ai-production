import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

for (const prefix of ['adobe/', 'production-runtime/adobe/']) {
  test(prefix + 'keeps mathematical subscripts literal in Adobe replacement semantics', () => {
    const source = fs.readFileSync(new URL('../' + prefix + 'illustrator.jsx', import.meta.url), 'utf8');
    const line = source.split('\n').find(s => s.includes('code=code.replace(/var input = askJson'));
    const raw = 'var input = askJson("test");\nvar tail = 1;';
    const context = {raw, graphText: JSON.stringify({nodes: [{text: '$I$_q^{*}'}, {text: '$I$_d^{*}'}]})};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(new URL('../' + prefix + 'common.jsx', import.meta.url), 'utf8'), context);
    vm.runInContext('var p={graph:eval("("+graphText+")")};var code={replace:function(pattern,replacement){return raw.replace(pattern,function(){return typeof replacement==="function"?replacement():replacement.split("$_").join(raw);});}};' + line, context);
    const replacement = vm.runInContext("'var input = '+JFW.stringify(JFW.stringify(p.graph))+';'", context);
    assert.equal(context.code, replacement + '\nvar tail = 1;');
    assert.equal(context.code.split('var tail').length, 2);
  });
}
