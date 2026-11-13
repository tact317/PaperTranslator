# Windows版：現行のローカル検証手順

> 2026-11-13時点。これは**開発・動作確認用**です。一般ユーザー向けの完成済みインストーラー手順ではありません。

## 動作確認済みの環境

- 64-bit Windows、PowerShell 5.1
- Node.js 22.16.0 / npm 10.9.2
- Python 3.12（64-bit）
- 既存の動作するPeperTranslator Windowsインストール（Electronバイナリの参照元）
- オンラインでnpm/pip依存を取得できる環境
- 実際の翻訳に必要なエンジン・モデル・接続設定（環境依存）

これは**動作確認実績**であり、最小要件や他のバージョンの保証を意味しません。

## 1. リポジトリの取得

```powershell
# GitHubへのアクセス権が必要です（現在のリポジトリは非公開）。
git clone https://github.com/tact317/PaperTranslator.git
cd PaperTranslator
```

ローカルに既にクローンがある場合、既存の変更やデータを上書きせず、そちらを利用してください。

## 2. ローカル配布候補を構築

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\BUILD_LOCAL_CANDIDATE.ps1 -Repository (Get-Location).Path
```

`PeperTranslator_STAGE2_LOCAL_CANDIDATE_日時` がデスクトップに生成され、`BUILD_REPORT.txt`に結果が記録されます。生成物は**独立した、正式配布不可の検証候補**です。既存のPeperTranslatorは変更しません。

**制約**：このビルドスクリプトは、既存のPeperTranslatorインストールに含まれるElectron本体をコピーします。Electronをソースのみから取得・再構築するものではありません。したがって、このコマンドだけで新しいWindows PCにアプリを導入することはできません。

## 3. 検証候補にPython環境を構築

候補フォルダを対象に実行します。既存の仮想環境を上書きしません。

```powershell
$candidate = "$env:USERPROFILE\Desktop\PeperTranslator_STAGE2_LOCAL_CANDIDATE_日時"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$candidate\SETUP_BACKEND_ON_TARGET.ps1" -CandidateRoot $candidate
```

`日時`は実際の生成フォルダ名に置き換えてください。成功の目安は `PYTHON_SETUP_PASS` です。依存関係は`backend/requirements-win-py312.lock`に基づきますが、翻訳モデルなどの外部コンポーネントは別途必要となる可能性があります。

## 4. 起動・翻訳試験

1. 通常版PeperTranslatorを完全に終了する。ポート`8000`と`31337`が使われていないか確認する。
2. 検証候補の`PeperTranslator.exe`を起動し、ReaderとLibraryが表示されることを確認する。
3. テスト用の英語論文PDFを読み込み、翻訳を試す。
4. 数値・単位・図表の保持と、品質表示を原文に照らして確認する。品質指標は参考値であり、満点を必須としない。
5. 結果の保存・再読み込みや、既存Libraryへの影響を別途確認する。重要データの編集・削除・上書きはしない。

開発者環境ではElectron画面の起動とPDF翻訳の動作が報告済みですが、この手順が他PCでも動くかは未検証です。

## モバイル版

`mobile-pwa/` はWindows版と別系統です。PWA対応ブラウザによる利用やオフライン動作には、配信方式・サービスワーカー・保存データなどの条件が関係します。Windows版の構築手順では配布できません。
