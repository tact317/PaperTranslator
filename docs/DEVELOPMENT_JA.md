# 開発・再ビルドの構成

## 構成とバージョンの区別

- **Electronアプリの表示バージョン**：Windows動作確認環境のEXEは`1.3.1`。
- **Electronランタイムのバージョン**：`native_shell/package.json`のアプリバージョンとは別。**正確なバージョン未固定**。
- **バックエンド**：Phase99、`backend/main.py` SHA-256 `8F1F922B43F86C9552234552EFDA5099AF099281B2CBB723A42DF573E550A9B2`。
- **フロントエンド**：Phase98.6系のUIソースと更新済みnpmロックファイル。Next.js 16.4.6でビルド確認。
- **Python**：3.12環境で`requirements-win-py312.lock`をインストールし、`pip check` PASS。
- **スマホ版**：`mobile-pwa/`にPhase97.2系のファイル。

## フロントエンド単体の再ビルド

```powershell
cd frontend
npm ci
npm run build
Test-Path .next\standalone\server.js
```

Next.jsの`standalone`出力を使用し、実行時には`.next/static`と`public`も配布先に配置します。ロックファイルを更新すると再現性に影響するため、変更時は`npm ci`とビルドを再確認してください。

## バックエンド依存関係

```powershell
py -3.12 -m venv .venv-test
.\.venv-test\Scripts\python.exe -m pip install -r backend\requirements-win-py312.lock
.\.venv-test\Scripts\python.exe -m pip check
```

`pip freeze`に基づく固定はOS・Python構成への依存や外部PDFエンジン・モデルまでは固定しません。クリーン環境での動作確認は別途必要です。

## 現在のビルドの限界

`packaging/BUILD_LOCAL_CANDIDATE.ps1`はインストール済みのElectron実行ファイルと`app.asar`をコピーします。**GitHubのソースだけからバイナリを再生成することは未達成**です。正式なWindows配布では、ランタイムを正しく固定し、独立したビルドと更新・アンインストールの安全性を検証する必要があります。

セキュリティ監査は2026-11-13の時点で`npm audit --omit=dev`が0件でした。開発用依存には12件の検出が残り、Python/Electron/モデル/外部サービスの検査を含む全体評価は未完了です。検出数は日時や脆弱性データベースにより変化します。
