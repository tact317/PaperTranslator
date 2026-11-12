const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'page.tsx'), 'utf8');
const doc = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
assert.equal(doc.parseDiagnostics.length, 0, 'TSX syntax must parse');
const panelPosition = source.indexOf('function LayoutTranslationPanel(');
assert.ok(panelPosition > 0, 'LayoutTranslationPanel must exist');
const panel = source.slice(panelPosition);
const subdoc = ts.createSourceFile('panel.tsx', panel, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let readyNode = null;
const find = (node) => {
  if (ts.isVariableDeclaration(node) && node.name.getText(subdoc) === 'ready') {
    readyNode = node.initializer;
  }
  ts.forEachChild(node, find);
};
find(subdoc);
assert.ok(readyNode, 'ready declaration must be present');
const readyExpression = readyNode.getText(subdoc);
const ready = (status) => vm.runInNewContext(`(${readyExpression})`, {status});
const checks = [
  [{status:'completed', mono_ready:true, qa:{quality_gate:'pass'}}, true, 'QA PASS with PDF'],
  [{status:'completed', mono_ready:false, qa:{quality_gate:'pass'}}, false, 'QA PASS without PDF'],
  [{status:'failed', mono_ready:true, qa:{quality_gate:'fail'}}, true, 'QA FAIL with PDF'],
  [{status:'failed', mono_ready:false, qa:{quality_gate:'fail'}}, false, 'QA FAIL without PDF'],
  [{status:'failed', mono_ready:true, qa:null}, false, 'runtime error, no QA'],
  [{status:'failed', mono_ready:true, qa:{quality_gate:'pass'}}, false, 'runtime error, QA PASS'],
  [{status:'running', mono_ready:true, qa:{quality_gate:'fail'}}, false, 'running still blocks preview'],
  [{status:'queued', mono_ready:true, qa:{quality_gate:'fail'}}, false, 'queued still blocks preview'],
  [{status:'not_started', mono_ready:true, qa:{quality_gate:'fail'}}, false, 'stale unstarted state not previewed'],
];
for (const [status, expected, label] of checks) {
  assert.equal(Boolean(ready(status)), expected, label);
}
assert.ok(panel.includes('if (productionFailed && !ready)'), 'production failure must not mask QA-FAIL artifact');
assert.ok(panel.includes('if (status.status === "failed" && !ready)'), 'full job failure must not mask QA-FAIL artifact');
assert.ok(panel.includes('status.qa?.quality_gate === "fail"'), 'warning must be visible');
assert.ok(panel.includes('role="alert"'), 'warning must have alert role');
assert.ok(panel.includes('status.qa.critical_count'), 'critical count must be visible');
assert.ok(source.includes('layoutStatus.qa?.quality_gate === "fail" ?'), 'download must be marked provisional');
assert.ok(source.includes('item.mono_ready && item.quality_gate === "fail"'), 'Library must distinguish preview artifacts');
console.log(`Phase94 UI gate regression: ${checks.length}/9 PASS`);
console.log('Phase94 source-level QA visibility and library checks: PASS');
