'use strict';

// Strictly stage a Next.js 16 standalone build without touching the installed app.
// Supports both .next/standalone/server.js and a traced-workspace subdirectory.
const fs = require('node:fs');
const path = require('node:path');

function requiredDirectory(p, description) {
  if (!fs.existsSync(p) || !fs.statSync(p).isDirectory()) {
    throw new Error(`${description} missing: ${p}`);
  }
}

function findEntryPoints(standalone) {
  const results = [];
  function walk(dir, levels) {
    if (levels > 5) return;
    const localServer = path.join(dir, 'server.js');
    if (fs.existsSync(localServer) && fs.statSync(localServer).isFile()) {
      results.push({ dir, file: localServer });
    }
    if (levels === 5) return;
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!ent.isDirectory() || ent.isSymbolicLink()) continue;
      if (['node_modules', '.next', '.git', '.cache'].includes(ent.name)) continue;
      walk(path.join(dir, ent.name), levels + 1);
    }
  }
  walk(standalone, 0);
  return results;
}

function scanForMarker(directory, marker) {
  let scanned = 0;
  let markerPath = null;
  const stack = [directory];
  while (stack.length) {
    const here = stack.pop();
    for (const entry of fs.readdirSync(here, { withFileTypes: true })) {
      const file = path.join(here, entry.name);
      if (entry.isDirectory()) stack.push(file);
      if (!entry.isFile() || !entry.name.endsWith('.js')) continue;
      scanned++;
      if (!markerPath && fs.readFileSync(file, 'utf8').includes(marker)) markerPath = file;
    }
  }
  if (!markerPath) throw new Error(`Compiled client JS marker ${marker} not found in ${directory} (${scanned} JS files scanned)`);
  return { markerPath, scanned };
}

function inspect(buildDir, marker) {
  const absolute = path.resolve(buildDir);
  const nextDir = path.join(absolute, '.next');
  const standalone = path.join(nextDir, 'standalone');
  const staticDir = path.join(nextDir, 'static');
  requiredDirectory(nextDir, 'Next.js .next output');
  requiredDirectory(standalone, 'Next.js standalone output');
  requiredDirectory(staticDir, 'Next.js client static output');
  const servers = findEntryPoints(standalone);
  if (servers.length !== 1) {
    throw new Error(`Expected one standalone app server.js (outside node_modules), found ${servers.length}: ${servers.map(s => path.relative(standalone, s.file)).join(', ') || '(none)'}`);
  }
  const relServerDir = path.relative(standalone, servers[0].dir);
  if (relServerDir.split(path.sep).some(part => part === '..')) throw new Error('Server directory escaped standalone root');
  const markerResult = scanForMarker(staticDir, marker);
  const buildId = path.join(nextDir, 'BUILD_ID');
  requiredFile(buildId, 'Next.js BUILD_ID');
  return { absolute, standalone, staticDir, relServerDir, serverPath: servers[0].file, markerResult, buildId };
}

function requiredFile(p, description) {
  if (!fs.existsSync(p) || !fs.statSync(p).isFile()) throw new Error(`${description} missing: ${p}`);
}

function prepare(buildDir, candidateDir, marker) {
  const found = inspect(buildDir, marker);
  const candidate = path.resolve(candidateDir);
  if (candidate === found.absolute || candidate.startsWith(found.absolute + path.sep) || found.absolute.startsWith(candidate + path.sep)) {
    throw new Error('Refusing overlapping source and candidate directories');
  }
  if (fs.existsSync(candidate)) {
    const items = fs.readdirSync(candidate);
    if (items.length) throw new Error(`Refusing nonempty candidate directory: ${candidate}`);
  } else {
    fs.mkdirSync(candidate, { recursive: true });
  }
  fs.cpSync(found.standalone, candidate, { recursive: true, force: false, dereference: true });
  const serverDir = path.join(candidate, found.relServerDir);
  fs.mkdirSync(path.join(serverDir, '.next'), { recursive: true });
  fs.cpSync(found.staticDir, path.join(serverDir, '.next', 'static'), { recursive: true, force: false, dereference: true });
  const stagedBuildId = path.join(serverDir, '.next', 'BUILD_ID');
  if (!fs.existsSync(stagedBuildId)) fs.copyFileSync(found.buildId, stagedBuildId);
  else if (fs.readFileSync(stagedBuildId, 'utf8') !== fs.readFileSync(found.buildId, 'utf8')) {
    throw new Error('Staged standalone BUILD_ID does not match built application');
  }
  const publicDir = path.join(found.absolute, 'public');
  if (fs.existsSync(publicDir)) {
    requiredDirectory(publicDir, 'Next.js public directory');
    fs.cpSync(publicDir, path.join(serverDir, 'public'), { recursive: true, force: false, dereference: true });
  }
  if (found.relServerDir !== '') {
    // The native launcher expects frontend_server/server.js. Keep the traced tree
    // intact, and only add a thin CommonJS wrapper at that exact entrypoint.
    const relative = './' + path.join(found.relServerDir, 'server.js').split(path.sep).join('/');
    fs.writeFileSync(path.join(candidate, 'server.js'), `require(${JSON.stringify(relative)});\n`, { flag: 'wx' });
  }
  requiredFile(path.join(candidate, 'server.js'), 'Staged root server.js');
  requiredDirectory(path.join(serverDir, '.next', 'static'), 'Staged Next.js static assets');
  requiredFile(path.join(serverDir, '.next', 'BUILD_ID'), 'Staged Next.js BUILD_ID');
  return {
    serverDir: found.relServerDir || '.',
    tracedWorkspace: found.relServerDir !== '',
    stagedEntrypoint: path.join(candidate, 'server.js'),
    markerAsset: path.relative(found.staticDir, found.markerResult.markerPath).split(path.sep).join('/'),
    javascriptFilesChecked: found.markerResult.scanned,
  };
}

if (require.main === module) {
  try {
    const [buildDir, candidateDir, marker] = process.argv.slice(2);
    if (!buildDir || !candidateDir || !marker || !/^pt-graph-ux-98\.4$/.test(marker)) {
      throw new Error('Usage: node prepare_next_artifacts.cjs <buildDir> <candidateDir> pt-graph-ux-98.4');
    }
    const result = prepare(buildDir, candidateDir, marker);
    console.log('PHASE98.5 STANDALONE STAGING PASS');
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error('PHASE98.5 ARTIFACT ERROR:', error.message);
    process.exitCode = 1;
  }
}

module.exports = { inspect, prepare, findEntryPoints, scanForMarker };
