/* PeperTranslator PWA local-only IndexedDB. No network synchronization. */
const DB_NAME = 'PeperTranslatorOfflinePWA';
const DB_VERSION = 1;
let opening;

export function openDatabase() {
  if (!('indexedDB' in window)) return Promise.reject(new Error('このブラウザーではIndexedDBが使えません。'));
  if (!opening) opening = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('documents')) db.createObjectStore('documents', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('files')) db.createObjectStore('files', { keyPath: 'key' });
      if (!db.objectStoreNames.contains('cards')) db.createObjectStore('cards', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('reviews')) db.createObjectStore('reviews', { keyPath: 'key' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => { opening = null; reject(req.error || new Error('データベースを開けません。')); };
    req.onblocked = () => { opening = null; reject(new Error('別のタブでPWAが開いています。閉じて再試行してください。')); };
  });
  return opening;
}

function requestPromise(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error('データの読み込みに失敗しました。'));
  });
}
function completed(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error || new Error('保存処理が中断されました。'));
    tx.onerror = () => reject(tx.error || new Error('保存に失敗しました。容量を確認してください。'));
  });
}
export async function getAll(name) {
  const db = await openDatabase();
  const tx = db.transaction(name, 'readonly');
  const result = await requestPromise(tx.objectStore(name).getAll());
  return result;
}
export async function get(name, key) {
  const db = await openDatabase();
  const tx = db.transaction(name, 'readonly');
  return requestPromise(tx.objectStore(name).get(key));
}
export async function put(name, value) {
  const db = await openDatabase();
  const tx = db.transaction(name, 'readwrite');
  const done = completed(tx);
  tx.objectStore(name).put(value);
  await done;
}
export async function saveDocument(document, pdfFiles) {
  // All variants of one document are committed atomically.
  const old = await get('documents', document.id);
  const byKind = new Map((old?.files || []).map(f => [f.kind, f]));
  for (const f of document.files) byKind.set(f.kind, f);
  const merged = { ...old, ...document, files: [...byKind.values()] };
  const db = await openDatabase();
  const tx = db.transaction(['documents', 'files'], 'readwrite');
  const done = completed(tx);
  for (const file of pdfFiles) tx.objectStore('files').put(file);
  tx.objectStore('documents').put(merged);
  await done;
}
export async function upsertCards(cards) {
  const db = await openDatabase();
  const tx = db.transaction('cards', 'readwrite');
  const done = completed(tx);
  for (const card of cards) tx.objectStore('cards').put(card);
  await done;
}
export async function upsertReviews(reviews) {
  const db = await openDatabase();
  const tx = db.transaction('reviews', 'readwrite');
  const done = completed(tx);
  for (const review of reviews) tx.objectStore('reviews').put(review);
  await done;
}
export async function eraseEverything() {
  const db = await openDatabase();
  const tx = db.transaction(['documents', 'files', 'cards', 'reviews'], 'readwrite');
  const done = completed(tx);
  for (const name of ['documents', 'files', 'cards', 'reviews']) tx.objectStore(name).clear();
  await done;
}
