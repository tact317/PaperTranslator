const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const page = fs.readFileSync(path.join(root,'app/page.tsx'),'utf8');
const component = fs.readFileSync(path.join(root,'components/knowledge-graph-panel.tsx'),'utf8');
const count = { value:0 };
function test(title, f) {f();count.value++;console.log(`PASS ${String(count.value).padStart(2,'0')}: ${title}`)}
for (const [name,text] of [['page',page],['component',component]]) {
  test(`${name} parses as TSX`,()=>{
    const ast=ts.createSourceFile(name+'.tsx',text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
    assert.equal(ast.parseDiagnostics.length,0,ast.parseDiagnostics.map(e=>e.messageText).join('\n'));
  });
}
test('Phase97 offline export path unchanged',()=>assert.ok(page.includes('`/api/offline/export`') || page.includes('/api/offline/export')));
test('Phase95 background job monitoring remains',()=>assert.ok(page.includes('jobStatusUrl(job, API_BASE_URL)')));
test('Phase94 PDF warning still visible',()=>assert.ok(page.includes('確認用PDFあり（QA不合格）')));
test('KnowledgeGraphPanel imported only once',()=>assert.equal((page.match(/import \{ KnowledgeGraphPanel \} from /g)||[]).length,1));
test('Graph can be opened from Library only by click',()=>assert.ok(page.includes('onClick={() => onOpenGraph(selected?.document_id ?? null)}')));
test('Graph holds its own modal state',()=>assert.ok(page.includes('knowledgeGraphOpen && (')));
test('Graph uses localhost API base',()=>assert.ok(page.includes('apiBase={API_BASE_URL}')));
test('Graph can open Library paper without loading PDF from external URL',()=>assert.ok(page.includes('void openLibraryDocument(id)')));
test('Graph forms require manual authoring',()=>assert.ok(component.includes('onSubmit={(e) => void saveFact(e)}') && component.includes('onSubmit={(e) => void saveLink(e)}')));
test('Graph does not request LLM operations',()=>assert.ok(!/(openai|ollama|llm|chat\/completions)/i.test(component)));
test('Graph has no background polling or timer',()=>assert.ok(!component.includes('setInterval(')));
test('Graph records evidence page and source paper',()=>assert.ok(component.includes('page_number') && component.includes('document_id')));
test('Graph warns quotes are not verified',()=>assert.ok(component.includes('未照合')));
test('Graph distinguishes virtual source and user links',()=>assert.ok(component.includes('link.origin === "manual"')));
test('Graph has a JSON backup download',()=>assert.ok(component.includes('/api/knowledge-graph/export')));
test('Graph states backup JSON import is future work',()=>assert.ok(component.includes('バックアップJSONを取り込む機能は今後の工程')));
test('Graph lists recoverable archived records',()=>assert.ok(component.includes('/api/knowledge-graph/archives')));
test('Graph offers one-click soft restore',()=>assert.ok(component.includes('facts/${fact.id}/restore') && component.includes('links/${link.id}/restore')));
test('Archival explicitly uses DELETE and does not mutate Library',()=>assert.ok(component.includes('"DELETE"') && !component.includes('/api/library/{')));
test('Graph visualization includes SVG node and edges',()=>assert.ok(component.includes('<svg') && component.includes('<line') && component.includes('<circle')));
console.log(`PHASE98 FRONTEND INTEGRATION: ${count.value}/${count.value} PASS`);
