# PeperTranslator Stage2 Integration Kit (2026-11-12)

## 解析結果

- GitHubのPhase99バックエンドとインストール版の `main.py` はSHA-256一致。
- Phase98.6 UIのNext.js standaloneビルドは生成確認済み。
- インストールされたElectron `app.asar`（SHA-256 `BB05795F3C2A083E0C6FC990C3E74AECFFFD36AC2146D121EAA5DD0E2435DACC`）から `main.js`・`package.json`・`loading.html`・アイコンを復元。
- v1.3.1実行ソースと復元済みv1.3.5ソースを比較。v1.3.5には `native_protocol=2` とrenderer→backend通信検証が追加されている。
- 旧インストーラーは既存インストール先削除を実行するため、実行禁止。

## 適用

このZIPをダウンロードし、下のPowerShell手順でGitHub作業フォルダに補完します。既存のインストール先は変更しません。

```powershell
$zip = "$env:USERPROFILE\Downloads\PeperTranslator_Stage2_IntegrationKit_20261112.zip"
$repo = "$env:USERPROFILE\Desktop\PeperTranslator_GitHub"
$kit = "$env:TEMP\PeperTranslator_Stage2_IntegrationKit_20261112"
Expand-Archive -LiteralPath $zip -DestinationPath $kit -Force
$root = Join-Path $kit 'PeperTranslator_Stage2_IntegrationKit_20261112'
if (!(Test-Path "$root\README_JA.md")) { $root = $kit }
New-Item -ItemType Directory "$repo\native_shell\assets", "$repo\packaging" -Force | Out-Null
Copy-Item "$root\native_shell\loading.html" "$repo\native_shell\loading.html"
Copy-Item "$root\native_shell\assets\PeperTranslator.ico" "$repo\native_shell\assets\PeperTranslator.ico"
Copy-Item "$root\packaging\BUILD_LOCAL_CANDIDATE.ps1" "$repo\packaging\BUILD_LOCAL_CANDIDATE.ps1"
Copy-Item "$root\packaging\SETUP_BACKEND_ON_TARGET.ps1" "$repo\packaging\SETUP_BACKEND_ON_TARGET.ps1"
Copy-Item "$root\packaging\INSTALLED_v131_main.reference.js" "$repo\packaging\INSTALLED_v131_main.reference.js"
Copy-Item "$root\packaging\INSTALLED_v131_package.reference.json" "$repo\packaging\INSTALLED_v131_package.reference.json"
Copy-Item "$root\README_JA.md" "$repo\packaging\README_STAGE2_JA.md"
node --check "$repo\native_shell\main.js"
git -C $repo diff --check
git -C $repo status --short
```

## 隔離ローカル配布候補の組み立て

`npm ci` と `next build` を再度実行し、インストール済みElectron実行ファイル（同一PC限定のブートストラップ）と組み合わせて、デスクトップ上の新規フォルダを作ります。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Desktop\PeperTranslator_GitHub\packaging\BUILD_LOCAL_CANDIDATE.ps1"
```

**重要**: これは配布製品ではありません。既存インストール済みElectronバイナリを参照するため、GitHubソースだけで完全再現できるビルドではありません。開発PC以外のテストPCにはPython 3.12と依存パッケージ導入が必要です。PDF翻訳の追加モデル・Ollama等の準備も別途必要です。既存アプリとポート8000/31337が競合するため、同時起動は禁止します。生成物にはユーザーデータやAPIキー等が含まれていないことを確認するまでは配布しないでください。

## 次のリリースゲート

1. 構築候補が生成でき、`BUILD_REPORT.txt`がPASS。
2. Electronをソースからバージョン固定で再ビルド（インストール済みバイナリに依存しないこと）。
3. Python/PDFモデル依存関係を対象PCでゼロからセットアップして起動検証。
4. 同一ポート占有、更新・アンインストール、データ保持を検証。
5. README、ライセンス、セキュリティ、Windows署名/SmartScreenの扱いを整理した後GitHub Releasesへ。
