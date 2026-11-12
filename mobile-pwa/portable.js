/* Compatible with the unchanged Phase97.1 Windows ZIP export. */
import { saveDocument, upsertCards, upsertReviews, getAll, get } from './db.js';
import { DIRECTIONS, normalizedReview } from './review.js';

const FILE_RE = /^pdfs\/[0-9a-f]{16}-(?:original|layout-ja|reading-ja|layout|reading|dual)\.pdf$/;
const DOC_RE = /^[0-9a-f]{64}$/;
const KINDS = new Set(['original', 'layout', 'reading', 'dual']);
const KIND_SUFFIX = { original: '-original.pdf', layout: '-layout-ja.pdf', reading: '-reading-ja.pdf', dual: '-dual.pdf' };
const LIMIT_COMPRESSED = 160 * 1024 * 1024;
const LIMIT_FILE = 160 * 1024 * 1024;
const LIMIT_TOTAL = 300 * 1024 * 1024;
const LIMIT_DOCS = 10;
const LIMIT_CARDS = 10000;
const enc = new TextEncoder();

function assert(condition, message) { if (!condition) throw new Error(message); }
function safeText(value, max) { return String(value || '').trim().slice(0, max); }
function safePath(value) {
  assert(typeof value === 'string' && FILE_RE.test(value) && !value.includes('..') && !value.includes('\\'), 'ZIP内のPDFパスが不正です。');
  return value;
}
function entry(zip, path) {
  const item = zip.file(path);
  assert(item && !item.dir, 'ZIP内に必要なファイルがありません: ' + path);
  // JSZip reads the central directory; also verify the bytes after decompression.
  assert(!item._data?.uncompressedSize || item._data.uncompressedSize <= LIMIT_FILE, 'PDFが160MiBを超えています。');
  return item;
}
async function sha256(bytes) {
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(x => x.toString(16).padStart(2, '0')).join('');
}
async function cardsFromTSV(tsv) {
  const lines = tsv.replace(/^\ufeff/, '').replace(/\r\n?/g, '\n').split('\n');
  assert(lines.shift()?.trim() === 'source\ttranslation\tkind', '語彙TSVの形式が不正です。');
  const seen = new Set(), result = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    const cols = line.split('\t');
    assert(cols.length === 3, '語彙TSVに不正な行があります。');
    const source = safeText(cols[0], 1000), translation = safeText(cols[1], 1000);
    if (!source || !translation) continue;
    const kind = safeText(cols[2], 20) || 'term';
    const id = await sha256(enc.encode(source.toLowerCase() + '\0' + translation).buffer);
    if (seen.has(id)) continue;
    seen.add(id);
    result.push({ id, source, translation, kind, example: '' });
    assert(result.length <= LIMIT_CARDS, '語彙カードが多すぎます。');
  }
  return result;
}
async function loadZip(file) {
  assert(file && file.name && file.name.toLowerCase().endsWith('.zip'), 'ZIPファイルを選択してください。');
  assert(file.size <= LIMIT_COMPRESSED, 'ZIPが160MiBを超えています。分割して取り込んでください。');
  assert(globalThis.JSZip, 'ZIP読み込みライブラリを読み込めません。');
  const bytes = await file.arrayBuffer();
  return globalThis.JSZip.loadAsync(bytes, { checkCRC32: false, createFolders: false });
}
function validateManifest(documents, maxDocs = LIMIT_DOCS) {
  assert(Array.isArray(documents) && documents.length >= 1 && documents.length <= maxDocs, '論文件数が1～10件の範囲外です。');
  const allIds = new Set();
  for (const d of documents) {
    assert(d && DOC_RE.test(d.id) && !allIds.has(d.id), '論文IDが不正または重複しています。');
    allIds.add(d.id);
    assert(Array.isArray(d.files) && d.files.length <= 4, 'PDF一覧が不正です。');
    const kinds = new Set();
    for (const f of d.files) {
      assert(f && KINDS.has(f.kind) && !kinds.has(f.kind), 'PDF種別が不正です。');
      kinds.add(f.kind);
      safePath(f.path);
      assert(f.path === 'pdfs/' + d.id.slice(0, 16) + KIND_SUFFIX[f.kind], 'PDFの文書ID・種別が一致しません。');
    }
    assert(kinds.has('original'), '原文PDFがありません。');
  }
}
function displayDocument(doc) {
  return { id: doc.id, title: safeText(doc.title, 500) || doc.id.slice(0, 12), doi: safeText(doc.doi, 200),
    quality_gate: doc.quality_gate === 'pass' ? 'pass' : (doc.quality_gate === 'fail' ? 'fail' : 'unknown'),
    qa_status: safeText(doc.qa_status, 40), importedAt: Date.now(), files: doc.files.map(f => ({path: safePath(f.path), label: safeText(f.label, 50), kind: f.kind})) };
}
async function pdfData(zip, document) {
  const files = [], display = displayDocument(document);
  let bytesTotal = 0;
  for (const f of display.files) {
    const bytes = await entry(zip, f.path).async('uint8array');
    assert(bytes.byteLength >= 5 && bytes.byteLength <= LIMIT_FILE, 'PDFサイズが不正です。');
    assert(String.fromCharCode(...bytes.subarray(0, 5)) === '%PDF-', 'PDFファイルのヘッダーが不正です。');
    bytesTotal += bytes.byteLength;
    assert(bytesTotal <= LIMIT_TOTAL, '論文PDFの合計が300MiBを超えています。');
    if (f.kind === 'original') {
      assert(await sha256(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)) === document.id, '原文PDFのSHA-256がIDと一致しません。破損した持ち出しデータの可能性があります。');
    }
    files.push({ key: document.id + ':' + f.kind, documentId: document.id, kind: f.kind,
      blob: new Blob([bytes], { type: 'application/pdf' }), bytes: bytes.byteLength });
  }
  return { files, display, bytesTotal };
}

export async function importPortableZip(file, progress = () => {}, preloaded = null) {
  const zip = preloaded || await loadZip(file);
  const manifest = JSON.parse(await entry(zip, 'manifest.json').async('string'));
  assert(manifest.schema === 'pepertranslator-offline-v1', 'Phase97.1形式のZIPではありません。');
  validateManifest(manifest.documents);
  const tsv = zip.file('vocabulary.tsv');
  const cards = tsv ? await cardsFromTSV(await tsv.async('string')) : [];
  let allBytes = 0;
  for (let i = 0; i < manifest.documents.length; i++) {
    const doc = manifest.documents[i];
    progress(`${i + 1}/${manifest.documents.length} 件目のPDFを確認中…`);
    const ready = await pdfData(zip, doc);
    allBytes += ready.bytesTotal;
    assert(allBytes <= LIMIT_TOTAL, 'ZIP内のPDF合計が300MiBを超えています。');
    await saveDocument(ready.display, ready.files);
  }
  progress('語彙カードを保存中…');
  if (cards.length) await upsertCards(cards);
  return { documents: manifest.documents.length, cards: cards.length, bytes: allBytes, mode: 'portable' };
}

function validateReviews(reviews, knownIds) {
  assert(Array.isArray(reviews) && reviews.length <= 2 * LIMIT_CARDS, '復習履歴の件数が不正です。');
  return reviews.map(r => {
    assert(r && typeof r.cardId === 'string' && knownIds.has(r.cardId) && DIRECTIONS.includes(r.direction), '復習履歴のカード参照が不正です。');
    return normalizedReview(r, r.cardId, r.direction);
  });
}
export async function importBackupZip(file, progress = () => {}, preloaded = null) {
  const zip = preloaded || await loadZip(file);
  const content = JSON.parse(await entry(zip, 'data.json').async('string'));
  assert(content.schema === 'pepertranslator-pwa-backup-v1', 'PWAバックアップの形式が不正です。');
  validateManifest(content.documents, 50);
  assert(Array.isArray(content.cards) && content.cards.length <= LIMIT_CARDS, 'バックアップの語彙件数が不正です。');
  const ids = new Set();
  const cards = content.cards.map(c => {
    assert(c && /^[0-9a-f]{64}$/.test(c.id) && !ids.has(c.id), '語彙IDが不正です。');
    ids.add(c.id);
    return { id: c.id, source: safeText(c.source, 1000), translation: safeText(c.translation, 1000),
      kind: safeText(c.kind, 20), example: safeText(c.example, 500) };
  }).filter(c => c.source && c.translation);
  const reviews = validateReviews(content.reviews || [], ids);
  let allBytes = 0;
  for (let i = 0; i < content.documents.length; i++) {
    progress(`バックアップを復元中… ${i + 1}/${content.documents.length}`);
    const ready = await pdfData(zip, content.documents[i]);
    allBytes += ready.bytesTotal;
    assert(allBytes <= LIMIT_TOTAL, 'バックアップ内のPDFが300MiBを超えています。');
    await saveDocument(ready.display, ready.files);
  }
  if (cards.length) await upsertCards(cards);
  if (reviews.length) await upsertReviews(reviews);
  return { documents: content.documents.length, cards: cards.length, reviews: reviews.length, bytes: allBytes, mode: 'backup' };
}
export async function importZip(file, progress) {
  const zip = await loadZip(file);
  if (zip.file('data.json')) return importBackupZip(file, progress, zip);
  return importPortableZip(file, progress, zip);
}
export async function makeBackupZip(progress = () => {}) {
  assert(globalThis.JSZip, 'ZIP書き出しライブラリがありません。');
  const docs = await getAll('documents'), cards = await getAll('cards'), reviews = await getAll('reviews');
  assert(docs.length > 0 && docs.length <= 50, 'バックアップする論文がありません。または50件を超えています。');
  const zip = new globalThis.JSZip();
  const manifest = [];
  let total = 0;
  for (const doc of docs) {
    const entryDoc = { id: doc.id, title: doc.title, doi: doc.doi, quality_gate: doc.quality_gate,
      qa_status: doc.qa_status, files: [] };
    for (const item of doc.files || []) {
      const stored = await get('files', doc.id + ':' + item.kind);
      if (!stored?.blob) continue;
      const path = 'pdfs/' + doc.id.slice(0, 16) + KIND_SUFFIX[item.kind];
      total += stored.blob.size;
      assert(total <= LIMIT_TOTAL, 'バックアップ上限300MiBを超えています。論文を分割してください。');
      zip.file(path, await stored.blob.arrayBuffer(), { compression: 'STORE' });
      entryDoc.files.push({ path, label: item.label, kind: item.kind });
    }
    if (entryDoc.files.some(f => f.kind === 'original')) manifest.push(entryDoc);
  }
  assert(manifest.length > 0, 'バックアップできる原文PDFがありません。');
  zip.file('data.json', JSON.stringify({ schema: 'pepertranslator-pwa-backup-v1', exportedAt: new Date().toISOString(),
    documents: manifest, cards, reviews }, null, 2));
  progress('バックアップZIPを生成中…');
  return zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 3 } });
}
