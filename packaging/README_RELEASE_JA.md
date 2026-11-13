# PeperTranslator Windows 配布手順 (2026-11-13)

## 現在の判定

**開発・ローカル検証用候補のみ。公開配布は未承認。** Windowsで稼働している Electron 1.3.1 アプリの実行ファイルを再利用するため、ElectronをGitHubのソースから再現したものではない。製品全体のライセンス・セキュリティ・PDF翻訳性能・別PC動作の検証も未完了。

## ソース構成

- `backend/`: Phase99 (2026-10-16)。`main.py` SHA256 `8F1F922B43F86C9552234552EFDA5099AF099281B2CBB723A42DF573E550A9B2`
- `frontend/`: Phase98.6、Next.js 16.4.6 を含む検証済み依存関係。`npm ci`, `npm run build`。
- `native_shell/`: Electron起動ソース。歴史的な`package.json`のversion=1.3.5は**アプリのバージョンでありElectronランタイムのバージョンではない**。
- `mobile-pwa/`: Phase97.2。Windowsの配布とは別系統。
- `packaging/`: 検証ビルドと新規PC用のPython環境構築。

## 開発機 Windows候補ビルド

PowerShell 5.1、Node.js 22.x、npm 10.x、インストール済みの動作する PeperTranslator、ネットワークが必要。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\BUILD_LOCAL_CANDIDATE.ps1
```

デスクトップに `PeperTranslator_STAGE2_LOCAL_CANDIDATE_日時` ができる。この処理はインストール済みアプリを更新しない。旧インストーラーは絶対に使わない。既存ユーザーデータを消す操作は一切含めない。

## 別のWindows PCでの試験

1. 上記候補フォルダ全体をコピーする。64-bit Windows、Python 3.12、Ollamaなど実際に必要な外部サービスとモデルを用意する。
2. コピーしたフォルダで `SETUP_BACKEND_ON_TARGET.ps1` を実行して依存関係を準備する（オンライン）。
3. **現行インストール済みアプリと同時起動しない**。`8000`/`31337` ポートの衝突がある。
4. アプリ起動、backend/frontendヘルス、Reader/Library/翻訳PDFの数値・図表・単位保持、オフライン挙動を確認する。合格記録が出るまでは再配布しない。

## セキュリティ

2026-11-13に `npm audit --omit=dev` 0件、`next build` PASS。ただし開発依存を含むnpm auditには12件の指摘が残り、PythonやElectronの脆弱性監査は完了していない。環境変数・認証情報・ユーザーのPDF/Libraryは配布物に含めない。

## 正式リリースまでの必須条件

- Electronランタイムの**正確な**バージョンを特定、開発依存として固定し、クリーン環境でインストーラーとEXEを再生成すること。アプリversion=1.3.5をElectronランタイムのversionとして扱わない。
- Python依存関係の固定候補をクリーンなWindows PCで検証すること。`pip freeze`に基づく固定であり、ハッシュ固定やすべての外部依存の固定ではない。
- 外部モデル・翻訳パイプラインの起動およびPDF全文翻訳を実試験すること。
- 開発依存・Electron・Pythonのセキュリティと再配布ライセンスを確認すること。
- READMEの利用者向け手順を確認した後、GitHub Releasesに正式パッケージを登録すること。
