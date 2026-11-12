const assert = require('node:assert/strict');
const fs = require('fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const root = path.join(__dirname, '..');
const code = fs.readFileSync(path.join(root, 'lib/translation-job-monitor.ts'), 'utf8');
const moduleObject = { exports: {} };
const compiled = ts.transpileModule(code, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, strict: true } });
vm.runInNewContext(compiled.outputText, { module: moduleObject, exports: moduleObject.exports, Date });
const m = moduleObject.exports;
const docId = 'a'.repeat(64), batchId = 'b'.repeat(32);
let passed = 0;
function test(label, f) { f(); passed++; console.log('PASS',label); }
const job = (kind = 'reading') => m.createTrackedJob(kind, kind === 'batch' ? batchId : docId, 'A research article');
const status = (a,b) => m.updateTrackedJob(a,b);

test('reading resumes from queued through running into completed', () => {
  const a = job(); const b = status(a,{status:'running',progress:45});
  assert.equal(b.progress,45); assert.equal(status(b,{status:'completed', untranslated_segments:0}).status,'completed');
});
test('partial reading is visible but never reported as fully completed', () => {
  assert.equal(status(job(),{status:'completed',untranslated_segments:2,quality_status:'needs_review'}).status,'needs_review');
});
test('layout QA failure with a PDF is review only', () => {
  assert.equal(status(job('layout'),{status:'failed',mono_ready:true,qa:{quality_gate:'fail'},progress:100}).status,'needs_review');
});
test('layout engine failure without QA or without PDF is a failure', () => {
  assert.equal(status(job('layout'),{status:'failed',mono_ready:false,qa:{quality_gate:'fail'}}).status,'failed');
  assert.equal(status(job('layout'),{status:'failed',mono_ready:true,qa:null}).status,'failed');
});
test('only QA pass can count as successful layout translation', () => {
  assert.equal(status(job('layout'),{status:'completed',mono_ready:true,qa:{quality_gate:'pass'}}).status,'completed');
  assert.equal(status(job('layout'),{status:'completed',mono_ready:true,qa:{quality_gate:'fail'}}).status,'needs_review');
});
test('production status retains nested full QA semantics', () => {
  assert.equal(status(job('production'),{status:'failed',full:{mono_ready:true,qa:{quality_gate:'fail'}}}).status,'needs_review');
  assert.equal(status(job('production'),{status:'failed',full:{mono_ready:false,qa:{quality_gate:'fail'}}}).status,'failed');
  assert.equal(status(job('production'),{status:'completed',full:{qa:{quality_gate:'pass'}}}).status,'completed');
});
test('preflight never claims success on QA failure', () => {
  assert.equal(status(job('preflight'),{status:'completed',qa:{status:'fail'}}).status,'needs_review');
  assert.equal(status(job('preflight'),{status:'completed',qa:{status:'pass'}}).status,'completed');
});
test('batch with errors is not full success', () => {
  assert.equal(status(job('batch'),{status:'completed_with_errors',completed:2,failed:1}).status,'needs_review');
  assert.equal(status(job('batch'),{status:'completed',completed:3,failed:0}).status,'completed');
});
test('stale not_started needs two observations to become interrupted', () => {
  const once=status(job(),{status:'not_started'}); assert.equal(once.status,'queued');
  assert.equal(status(once,{status:'not_started'}).status,'interrupted');
});
test('progress alone cannot fabricate completion', () => {
  assert.equal(status(job(),{status:'running',progress:100}).status,'running');
});
test('already completed is stable under later polling', () => {
  const complete=status(job(),{status:'completed'});
  assert.equal(status(complete,{status:'running',progress:5}),complete);
});
test('status polling urls point to established read-only API routes', () => {
  const api='http://127.0.0.1:8000';
  assert.equal(m.jobStatusUrl(job('reading'),api),`${api}/api/pdfs/${docId}/translation`);
  assert.equal(m.jobStatusUrl(job('layout'),api),`${api}/api/pdfs/${docId}/layout-translation`);
  assert.equal(m.jobStatusUrl(job('production'),api),`${api}/api/pdfs/${docId}/layout-translation/production`);
  assert.equal(m.jobStatusUrl(job('preflight'),api),`${api}/api/pdfs/${docId}/layout-translation/preflight`);
  assert.equal(m.jobStatusUrl(job('batch'),api),`${api}/api/layout-translation/batches/${batchId}`);
});
test('restoring an active job preserves identity and does not create a new backend job', () => {
  const value=job(); const restored=m.restoreTrackedJobs(JSON.stringify([value]));
  assert.equal(restored.length,1); assert.equal(restored[0].targetId,docId);
  assert.equal(restored[0].status,'queued');
});
test('malformed or malicious stored job ids are discarded', () => {
  assert.equal(m.restoreTrackedJobs('not-json').length,0);
  assert.equal(m.restoreTrackedJobs(JSON.stringify([{...job(),targetId:'../../secret'}])).length,0);
  assert.throws(()=>m.createTrackedJob('reading','../../secret','x'));
});
test('terminal unread state survives restoring and is not silently acknowledged', () => {
  const done={...status(job(),{status:'completed'}),announced:true,acknowledged:false};
  assert.equal(m.restoreTrackedJobs(JSON.stringify([done]))[0].acknowledged,false);
  assert.equal(m.restoreTrackedJobs(JSON.stringify([done]))[0].announced,true);
});
test('history cleanup never drops an active job', () => {
  const active=job(); const history=Array.from({length:25},(_,i)=>({...job(),id:`reading:${String(i).padStart(64,'c')}`,targetId:String(i).padStart(64,'c'),status:'completed',createdAt:new Date(1000000+i).toISOString()}));
  const remaining=m.keepRecentJobs([active,...history]);
  assert.equal(remaining.filter(x=>x.status==='queued').length,1);
  assert.equal(remaining.filter(x=>x.status==='completed').length,16);
});

// Parsing every compiled UI component requires Next/React dependencies. Check the
// changed page's TSX syntax and the integration points without invoking Ollama.
const page = fs.readFileSync(path.join(root,'app/page.tsx'),'utf8');
const ast = ts.createSourceFile('page.tsx',page,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
test('page TSX parses with no diagnostic', () => assert.equal(ast.parseDiagnostics.length,0));
test('single page-level observer does not depend on current document ID', () => {
  assert.ok(page.includes('const active = trackedJobsRef.current.filter((job) => !isTerminalJob(job))'));
  assert.ok(page.includes('jobStatusUrl(job, API_BASE_URL)'));
  assert.ok(page.includes('activeDocumentRef.current !== targetDocumentId'));
});
test('existing start paths track reading, full layout, production, preflight, and batch', () => {
  for (const kind of ['reading','layout','production','preflight','batch']) assert.ok(page.includes(`trackNewJob("${kind}"`));
});
test('system permission is only requested by user-triggered control', () => {
  assert.equal((page.match(/Notification\.requestPermission\(/g)||[]).length,1);
  assert.ok(page.includes('onClick={onEnableDesktopNotifications}'));
});
test('translation state and QA endpoints are not mutated by job polling', () => {
  assert.ok(page.includes('fetch(jobStatusUrl(job, API_BASE_URL), { cache: "no-store" })'));
  assert.ok(!code.includes('fetch('));
});
console.log(`Phase95 job monitor offline regression: ${passed}/${passed} PASS`);
