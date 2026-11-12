const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const panel = fs.readFileSync(path.join(root, 'components/knowledge-graph-panel.tsx'), 'utf8');
const css = fs.readFileSync(path.join(root, 'app/globals.css'), 'utf8');
const tests = [];
function test(label, fn) { fn(); tests.push(label); console.log(`PASS ${String(tests.length).padStart(2,'0')} ${label}`); }
test('Panel is valid TSX', () => {
  const f = ts.createSourceFile('panel.tsx', panel, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  assert.equal(f.parseDiagnostics.length, 0, f.parseDiagnostics.map(e => String(e.messageText)).join('\n'));
});
test('All papers visible by default, Library selection only highlights', () => assert.match(panel, /\[focus, setFocus\] = React\.useState\(""\)/));
test('User can select full graph explicitly', () => assert.match(panel, /全論文を表示（既定）/));
test('Graph filters only after explicit focus', () => assert.match(panel, /else if \(focus\)/));
test('Existing paper nodes and stored graph links are retained', () => {
  assert.match(panel, /graph\.papers, \.\.\.graph\.facts/);
  assert.match(panel, /graph\.links\.filter\(/);
});
test('Form submission always reaches explicit validation', () => assert.match(panel, /<form noValidate onSubmit=\{\(e\) => void saveFact\(e\)\}/));
test('Blank title yields visible actionable error', () => {
  assert.match(panel, /if \(!factForm\.title\.trim\(\)\)/);
  assert.match(panel, /titleInputRef\.current\?\.focus\(\)/);
});
test('Save feedback is in sidebar above input form', () => assert.ok(panel.indexOf('role="alert"') < panel.indexOf('<form noValidate')));
test('After successful fact create, source paper neighborhood is revealed', () => assert.match(panel, /setFocus\("paper_" \+ factForm\.document_id\)/));
test('After successful link create, entire graph is revealed', () => assert.match(panel, /setNotice\("関係を登録しました。全体グラフ/));
test('Editing tab explains that bottom button performs the save', () => assert.match(panel, /上の「項目の作成・編集」はタブ/));
test('View navigation supports wheel zoom and pointer dragging', () => {
  assert.match(panel, /onWheel=\{zoomGraph\}/);
  assert.match(panel, /onPointerDown=\{\(event\) => beginGraphGesture\(event, "pan"\)\}/);
  assert.match(panel, /graphNodePointerDown\(e, node\.id\)/);
});
test('Zoom and reset buttons accessible', () => {
  assert.match(panel, /aria-label="拡大"/);
  assert.match(panel, /aria-label="縮小"/);
  assert.match(panel, /配置リセット/);
});
test('Canvas is dark in light theme', () => {
  assert.match(css, /\.pt-theme-light \.pt-kg-shell \[class\*="bg-zinc-900"\]/);
  assert.match(css, /\.pt-kg-canvas \{ touch-action:none/);
});
test('Colors, labels and graph edges have distinct visual semantics', () => {
  assert.match(panel, /nodeColor\(node\)/);
  assert.match(panel, /link\.origin === "manual"/);
  assert.match(panel, /破線＝出典、実線＝手動登録の関係/);
});
test('No derived citation relation auto-created by UI', () => assert.ok(!/(autoCreateLink|inferCitations|suggestLinks)/.test(panel)));
test('Existing export, archive and local endpoints remain', () => {
  assert.match(panel, /\/api\/knowledge-graph\/export/);
  assert.match(panel, /\/api\/knowledge-graph\/archives/);
  assert.match(panel, /\/api\/knowledge-graph\/facts/);
});
// Execute only the pure deterministic layout helper, with no browser or React dependencies.
const part = panel.substring(panel.indexOf('type Paper ='), panel.indexOf('\nexport function KnowledgeGraphPanel'));
const transpiled = ts.transpileModule(part + '\nmodule.exports = { layoutGraph, idLabel };', {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  reportDiagnostics: true,
});
assert.equal((transpiled.diagnostics || []).length, 0);
const sandboxModule = { exports: {} };
new Function('module', 'exports', transpiled.outputText)(sandboxModule, sandboxModule.exports);
const { layoutGraph } = sandboxModule.exports;
const papers = Array.from({length:15},(_,i)=>({id:'paper_p'+i,kind:'paper',title:'Research paper '+i,document_id:'p'+i}));
test('15 disconnected Library papers remain 15 visible nodes', () => {
  const coords = layoutGraph(papers, '', []);
  assert.equal(coords.size, 15);
  const unique = new Set([...coords.values()].map(v=>Math.round(v.x)+','+Math.round(v.y)));
  assert.equal(unique.size,15);
});
test('Deterministic layout and bounding box',()=>{
  const a=[...layoutGraph(papers,'',[])], b=[...layoutGraph(papers,'',[])];
  assert.deepEqual(a,b);
  assert.ok(a.every(([,v])=>v.x>=90 && v.x<=910 && v.y>=82 && v.y<=413));
});
test('One selected paper still permits full graph layout',()=>assert.equal(layoutGraph(papers,'paper_p0',[]).size,15));
test('Manual relation does not delete either endpoint',()=>{
  const edges=[{id:'link_x',from_id:'paper_p0',to_id:'paper_p1',origin:'manual',relation:'compares'}];
  assert.equal(layoutGraph(papers,'',edges).size,15);
});
test('Newly created evidence fact appears as a separate linked node',()=>{
  const fact={id:'fact_x',kind:'measurement',title:'10 T',document_id:'p0'};
  const coords=layoutGraph([...papers,fact], '', [{id:'derived',from_id:'paper_p0',to_id:'fact_x',origin:'derived'}]);
  assert.ok(coords.has('fact_x')); assert.ok(coords.has('paper_p0'));
  assert.notDeepEqual(coords.get('fact_x'),coords.get('paper_p0'));
});
console.log(`PHASE98.4 GRAPH UX REGRESSION: ${tests.length}/${tests.length} PASS`);
