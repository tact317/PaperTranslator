import { openDatabase, getAll, get, put, eraseEverything } from './db.js';
import { importZip, makeBackupZip } from './portable.js';
import { reviewNext, due } from './review.js';

const $ = id => document.getElementById(id);
const state = { documents: [], cards: [], reviews: new Map(), direction: 'en-ja', queue: [], index: 0,
  revealed: false, deferredPrompt: null, pdfUrl: null, pdfName: '', pdfBlob: null, busy: false };
let noticeTimer;
const fmtBytes = n => n < 1024 * 1024 ? `${(n / 1024).toFixed(0)} KiB` : `${(n / 1024 / 1024).toFixed(1)} MiB`;
function announce(message, ms = 5000) {
  const el = $('toast'); el.textContent = message; el.hidden = false;
  clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { el.hidden = true; }, ms);
}
function create(tag, text, className) {
  const el = document.createElement(tag); if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function tab(name) {
  for (const target of ['papers', 'cards', 'settings']) {
    $(target + 'Panel').classList.toggle('hidden', target !== name);
    const btn = $(target + 'Tab'); btn.classList.toggle('active', target === name);
    btn.setAttribute('aria-selected', String(target === name));
  }
  if (name === 'settings') updateStorage();
}
function qaLabel(doc) {
  if (doc.quality_gate === 'fail') return ['QA不合格', 'quality bad'];
  if (doc.quality_gate === 'pass') return ['QA合格', 'quality good'];
  return ['品質未確認', 'quality'];
}
function documentPanel(doc) {
  const article = create('article', undefined, 'paper-card');
  const [label, className] = qaLabel(doc);
  article.append(create('div', label, className));
  article.append(create('h3', doc.title || doc.id));
  if (doc.doi) article.append(create('div', 'DOI: ' + doc.doi, 'doi'));
  if (doc.quality_gate !== 'pass') article.append(create('p', '日本語PDFは確認用です。科学値・数式は原文と照合してください。', 'status-note'));
  const div = create('div', undefined, 'files');
  const order = { original: 0, layout: 1, reading: 2, dual: 3 };
  for (const f of [...(doc.files || [])].sort((a,b) => order[a.kind] - order[b.kind])) {
    const b = create('button', f.label || f.kind, 'btn secondary');
    b.type = 'button';
    b.addEventListener('click', () => openPDF(doc, f).catch(e => announce('PDF表示エラー: ' + e.message, 9000)));
    div.append(b);
  }
  article.append(div);
  return article;
}
function renderDocuments() {
  $('docBadge').textContent = String(state.documents.length);
  $('paperCount').textContent = `${state.documents.length} 件保存済み`;
  const list = $('paperList'); list.replaceChildren();
  if (!state.documents.length) {
    list.append(create('p', 'まだ論文がありません。Windows版のLibraryで「スマホ用ZIP」を出力し、上のボタンから取り込んでください。', 'empty'));
    return;
  }
  for (const doc of state.documents) list.append(documentPanel(doc));
}
function closeViewer() {
  $('pdfFrame').src = 'about:blank';
  if (state.pdfUrl) URL.revokeObjectURL(state.pdfUrl);
  state.pdfUrl = null; state.pdfBlob = null; state.pdfName = '';
}
async function openPDF(doc, file) {
  const stored = await get('files', doc.id + ':' + file.kind);
  if (!stored?.blob) throw new Error('PDFが端末に保存されていません。ZIPをもう一度読み込んでください。');
  closeViewer();
  state.pdfBlob = stored.blob;
  state.pdfUrl = URL.createObjectURL(stored.blob);
  state.pdfName = doc.id.slice(0, 12) + '-' + file.kind + '.pdf';
  $('viewerTitle').textContent = `${doc.title} / ${file.label}`;
  $('viewerWarning').hidden = file.kind === 'original' || doc.quality_gate === 'pass';
  $('pdfFrame').src = state.pdfUrl;
  $('viewerDialog').showModal();
}
function pdfDownload() {
  if (!state.pdfUrl) return;
  const a = document.createElement('a'); a.href = state.pdfUrl; a.download = state.pdfName; a.click();
}
function pdfOpen() {
  if (!state.pdfUrl) return;
  const externalUrl = URL.createObjectURL(state.pdfBlob);
  const a = document.createElement('a'); a.href = externalUrl; a.target = '_blank'; a.rel = 'noopener noreferrer';
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(externalUrl), 60000);
}
function dueCards() { return state.cards.filter(c => due(c, state.reviews, state.direction)); }
function resetQueue() {
  state.queue = dueCards().map(c => c.id); state.index = 0; state.revealed = false;
  renderStudy();
}
function currentCard() { return state.cards.find(c => c.id === state.queue[state.index]); }
function renderStudy() {
  $('cardCount').textContent = `${state.cards.length} 語`;
  $('dueBadge').textContent = String(dueCards().length);
  $('enJa').classList.toggle('selected', state.direction === 'en-ja');
  $('jaEn').classList.toggle('selected', state.direction === 'ja-en');
  const card = currentCard();
  $('studyEmpty').classList.toggle('hidden', !!card);
  $('studyCard').classList.toggle('hidden', !card);
  if (!card) {
    $('studyEmpty').textContent = state.cards.length ? '今回の復習は完了です。次の復習予定までお待ちください。' : '単語カードがありません。持ち出しZIPを取り込むと復習できます。';
    return;
  }
  $('studyCounter').textContent = `${state.index + 1} / ${state.queue.length}（今すぐ復習）`;
  $('studyQuestion').textContent = state.direction === 'en-ja' ? card.source : card.translation;
  $('studyAnswer').textContent = state.direction === 'en-ja' ? card.translation : card.source;
  $('studyAnswer').classList.toggle('hidden', !state.revealed);
  $('revealBtn').classList.toggle('hidden', state.revealed);
  $('knownBtn').classList.toggle('hidden', !state.revealed);
  $('againBtn').classList.toggle('hidden', !state.revealed);
}
function nextCard() {
  state.index += 1;
  state.revealed = false;
  renderStudy();
}
async function rate(remembered) {
  const card = currentCard(); if (!card || !state.revealed) return;
  const key = card.id + ':' + state.direction;
  const updated = reviewNext(state.reviews.get(key), card.id, state.direction, remembered);
  await put('reviews', updated);
  state.reviews.set(key, updated);
  nextCard();
}
async function refresh() {
  state.documents = (await getAll('documents')).sort((a, b) => (b.importedAt || 0) - (a.importedAt || 0));
  state.cards = (await getAll('cards')).sort((a,b) => a.source.localeCompare(b.source));
  state.reviews = new Map((await getAll('reviews')).map(r => [r.key, r]));
  renderDocuments(); resetQueue(); updateStorage();
}
async function updateStorage() {
  const label = `${state.documents.length}論文 / ${state.cards.length}語 / ${state.reviews.size}件の復習履歴`;
  if (navigator.storage?.estimate) {
    try { const x = await navigator.storage.estimate(); $('storageStats').textContent = `${label} ・ 使用量 約${fmtBytes(x.usage || 0)}`; return; } catch {}
  }
  $('storageStats').textContent = label;
}
function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
async function busy(task) {
  if (state.busy) { announce('現在処理中です。少しお待ちください。'); return; }
  state.busy = true;
  try { await task(); } catch (err) { console.error(err); announce('処理できませんでした: ' + (err.message || String(err)), 12000); }
  finally { state.busy = false; }
}
async function chooseImport(file) {
  if (!file) return;
  await busy(async () => {
    announce('ZIPを確認しています…', 60000);
    const result = await importZip(file, msg => announce(msg, 60000));
    await refresh();
    announce(`${result.documents}論文・${result.cards}語を取り込みました。端末内でオフライン利用できます。`, 9000);
    tab('papers');
  });
}
async function backup() {
  await busy(async () => {
    announce('バックアップを作成しています…', 60000);
    const blob = await makeBackupZip(msg => announce(msg, 60000));
    const stamp = new Date().toISOString().slice(0, 10);
    downloadBlob(blob, `PeperReader_Backup_${stamp}.zip`);
    announce('全データのバックアップZIPを保存しました。別の安全な場所にも保管してください。', 8000);
  });
}
async function clearData() {
  if (!confirm('端末内の論文PDF・語彙・復習履歴をすべて削除します。バックアップ済みですか？')) return;
  if (!confirm('本当に削除しますか？元に戻すにはバックアップZIPが必要です。')) return;
  await busy(async () => { await eraseEverything(); await refresh(); announce('端末内データを削除しました。'); });
}
function updateConnection() {
  const ready = !!navigator.serviceWorker?.controller;
  const chip = $('onlineChip');
  if (!navigator.onLine) { chip.textContent = ready ? 'オフライン利用中' : '接続なし'; chip.className = 'connection ' + (ready ? 'ready' : 'warn'); }
  else { chip.textContent = ready ? 'オフライン対応' : '初回準備中'; chip.className = 'connection ' + (ready ? 'ready' : 'warn'); }
}
async function setupServiceWorker() {
  if (!('serviceWorker' in navigator)) { $('swInfo').textContent = 'この環境ではService Workerが使えません。HTTPSの対応ブラウザーで開いてください。'; return; }
  try {
    const reg = await navigator.serviceWorker.register('./sw.js', { scope: './' });
    await navigator.serviceWorker.ready;
    $('swInfo').textContent = 'アプリ本体をオフライン用に保存しました。ZIPデータは端末内にのみ保存されます。';
    updateConnection();
    navigator.serviceWorker.addEventListener('controllerchange', updateConnection);
    if (!navigator.serviceWorker.controller && reg.active) {
      $('swInfo').textContent += ' 初回のみ、再読み込み後にオフライン起動できます。';
    }
  } catch (err) { $('swInfo').textContent = 'PWAの準備ができませんでした。HTTPSまたはlocalhostが必要です。'; console.error(err); }
}
function setupInstall() {
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault(); state.deferredPrompt = e;
    $('installBtn').hidden = false;
  });
  $('installBtn').addEventListener('click', async () => {
    if (!state.deferredPrompt) return;
    await state.deferredPrompt.prompt(); state.deferredPrompt = null;
    $('installBtn').hidden = true;
  });
  $('installationHelp').textContent = /iPad|iPhone|iPod/.test(navigator.userAgent)
    ? 'iPhone/iPad: Safariの「共有」→「ホーム画面に追加」を選択してください。'
    : 'Android: Chromeのメニュー→「アプリをインストール」または「ホーム画面に追加」を選択してください。';
}
async function main() {
  await openDatabase();
  for (const name of ['papers', 'cards', 'settings']) $(name + 'Tab').addEventListener('click', () => tab(name));
  $('zipInput').addEventListener('change', async e => { const f = e.target.files?.[0]; e.target.value = ''; await chooseImport(f); });
  $('restoreInput').addEventListener('change', async e => { const f = e.target.files?.[0]; e.target.value = ''; await chooseImport(f); });
  $('viewerClose').addEventListener('click', () => $('viewerDialog').close());
  $('viewerDialog').addEventListener('close', closeViewer);
  $('viewerDownload').addEventListener('click', pdfDownload);
  $('viewerOpen').addEventListener('click', pdfOpen);
  $('revealBtn').addEventListener('click', () => { state.revealed = true; renderStudy(); });
  $('againBtn').addEventListener('click', () => busy(() => rate(false)));
  $('knownBtn').addEventListener('click', () => busy(() => rate(true)));
  $('skipBtn').addEventListener('click', nextCard);
  $('enJa').addEventListener('click', () => { state.direction = 'en-ja'; resetQueue(); });
  $('jaEn').addEventListener('click', () => { state.direction = 'ja-en'; resetQueue(); });
  $('shuffleBtn').addEventListener('click', () => { resetQueue(); for (let i = state.queue.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [state.queue[i],state.queue[j]]=[state.queue[j],state.queue[i]]; } renderStudy(); });
  $('backupBtn').addEventListener('click', backup);
  $('clearBtn').addEventListener('click', clearData);
  $('persistentBtn').addEventListener('click', async () => {
    if (!navigator.storage?.persist) return announce('このブラウザーはストレージ保持申請に非対応です。');
    const granted = await navigator.storage.persist();
    announce(granted ? 'ストレージの保持が許可されました。バックアップも継続してください。' : '保持は許可されませんでした。バックアップを定期的に作成してください。');
  });
  window.addEventListener('online', updateConnection);
  window.addEventListener('offline', updateConnection);
  updateConnection();
  setupInstall();
  await refresh();
  setupServiceWorker();
}
main().catch(e => { console.error(e); announce('起動エラー: ' + e.message, 30000); $('swInfo').textContent = '端末内データベースを利用できません。ブラウザーの設定をご確認ください。'; });
