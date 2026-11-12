'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const { inspect, prepare } = require('./prepare_next_artifacts.cjs');
const marker = 'pt-graph-ux-98.4';
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pt985-fixture-'));
let count = 0;
function test(name, fn) {
  fn(); count++; console.log(`PASS ${String(count).padStart(2, '0')}: ${name}`);
}
function put(p, content = 'ok') { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, content); }
function fixture(name, nested = false) {
  const build = path.join(root, name, 'source folder');
  const location = path.join(build, '.next', 'standalone', ...(nested ? ['workspace', 'frontend'] : []));
  put(path.join(location, 'server.js'), 'module.exports={};\n');
  put(path.join(location, '.next', 'server', 'app.js'), 'module.exports={};\n');
  put(path.join(build, '.next', 'static', 'chunks', 'app.js'), `const marker=${JSON.stringify(marker)};`);
  put(path.join(build, '.next', 'BUILD_ID'), 'fake-build-123');
  put(path.join(build, 'public', 'file.svg'), '<svg/>');
  put(path.join(build, '.next', 'standalone', 'node_modules', 'bar', 'server.js'), 'module.exports={};');
  return build;
}
try {
  const flat = fixture('flat');
  const nested = fixture('nested', true);
  test('detect root standalone entrypoint', () => assert.equal(inspect(flat, marker).relServerDir, ''));
  test('ignore node_modules/server.js', () => assert.equal(inspect(flat, marker).serverPath, path.join(flat, '.next', 'standalone', 'server.js')));
  test('detect nested traced workspace', () => assert.equal(inspect(nested, marker).relServerDir, path.join('workspace', 'frontend')));
  const flatOut = path.join(root, 'flat output');
  test('stage flat standalone successfully', () => assert.equal(prepare(flat, flatOut, marker).tracedWorkspace, false));
  test('flat boot entrypoint remains original', () => assert.match(fs.readFileSync(path.join(flatOut, 'server.js'), 'utf8'), /module.exports/));
  test('flat static assets and BUILD_ID copied', () => assert.equal(fs.readFileSync(path.join(flatOut, '.next', 'BUILD_ID'), 'utf8'), 'fake-build-123'));
  test('flat public assets copied', () => assert.ok(fs.existsSync(path.join(flatOut, 'public', 'file.svg'))));
  const nestedOut = path.join(root, 'nested output');
  test('stage nested standalone successfully', () => assert.equal(prepare(nested, nestedOut, marker).tracedWorkspace, true));
  test('nested root wrapper resolves real traced server', () => assert.equal(fs.readFileSync(path.join(nestedOut, 'server.js'), 'utf8').trim(), 'require("./workspace/frontend/server.js");'));
  test('nested project BUILD_ID and static assets copied', () => assert.ok(fs.existsSync(path.join(nestedOut, 'workspace', 'frontend', '.next', 'static', 'chunks', 'app.js'))));
  test('outer trace dependencies remain available', () => assert.ok(fs.existsSync(path.join(nestedOut, 'node_modules', 'bar', 'server.js'))));
  test('nested wrapper executes traced entrypoint', () => assert.deepEqual(require(path.join(nestedOut, 'server.js')), {}));
  test('source standalone server remains unchanged', () => assert.equal(fs.readFileSync(path.join(nested, '.next', 'standalone', 'workspace', 'frontend', 'server.js'), 'utf8'), 'module.exports={};\n'));
  test('reject missing standalone artifacts', () => {
    const bad = fixture('missing'); fs.rmSync(path.join(bad, '.next', 'standalone'), { recursive: true });
    assert.throws(() => inspect(bad, marker), /standalone output missing/);
  });
  test('reject missing compiled marker', () => {
    const bad = fixture('marker'); put(path.join(bad, '.next', 'static', 'chunks', 'app.js'), 'const other=4;');
    assert.throws(() => inspect(bad, marker), /marker.*not found/);
  });
  test('reject missing BUILD_ID', () => {
    const bad = fixture('build-id'); fs.rmSync(path.join(bad, '.next', 'BUILD_ID'));
    assert.throws(() => inspect(bad, marker), /BUILD_ID missing/);
  });
  test('reject multiple possible app entrypoints', () => {
    const bad = fixture('multiple'); put(path.join(bad, '.next', 'standalone', 'another', 'server.js'), 'hi');
    assert.throws(() => inspect(bad, marker), /found 2/);
  });
  test('reject nonempty candidate rather than overwrite', () => assert.throws(() => prepare(flat, flatOut, marker), /nonempty candidate/));
  test('reject source/candidate path overlap', () => assert.throws(() => prepare(flat, path.join(flat, 'candidate'), marker), /overlapping/));
  test('reject missing client static directory', () => {
    const bad = fixture('static'); fs.rmSync(path.join(bad, '.next', 'static'), { recursive: true });
    assert.throws(() => inspect(bad, marker), /static output missing/);
  });
  console.log(`PHASE98.5 NEXT ARTIFACT REGRESSION: ${count}/${count} PASS`);
} finally { fs.rmSync(root, { recursive: true, force: true }); }
