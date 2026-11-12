# PeperReader Phase97.2 - スマホ用オフラインPWA

**これはWindows版PeperTranslatorの更新ZIPではありません。** Phase97.1までのWindows版をそのまま使用し、持ち出しZIPを取り込む独立したスマホ用Webアプリです。インストール済みアプリ・Library・翻訳・クイズ・語彙には変更しません。

## 実装機能

- ホーム画面のアイコンから起動するPWA（iOS Safari / Android Chrome、初回はHTTPS必要）
- Service Workerによるアプリ本体のオフラインキャッシュ
- Windows Phase97.1で生成した `PeperTranslator_Offline_*.zip` の読み込み
- PDFを端末のIndexedDBにBlobとして保存し、通信なしで閲覧（内蔵表示が動かない端末ではPDF保存）
- 原文・本文訳・レイアウト訳・英日対訳の各PDFを区別して表示
- QA不合格・未判定を警告表示して維持
- 語彙TSVから英日・日英カード作成、方向別の復習予定・履歴をIndexedDB保存
- 全論文PDF・語彙・履歴の一括バックアップZIPと復元
- 元PDFハッシュ、ファイル形式、件数、サイズ、ZIPパスの検証
- 保存容量の表示、永続ストレージ保持申請（ブラウザーが許可する場合）

**翻訳、PCとの同期、スマホでのOllama実行は実装していません。**

## 利用方法（初回）

1. このZIPを展開すると `index.html`, `sw.js`, `app.js`, `db.js`, `portable.js`, `review.js`, `app.css`, `manifest.json`, `icons/`, `vendor/` が得られます。**個人の論文PDFやPhase97.1持ち出しZIPをWebサイトにアップロードしないでください。** 公開するのは本アプリの静的ファイルのみです。
2. これらの静的ファイルをHTTPS配信するWebサイトに配置します。例：GitHub Pagesの公開リポジトリ（内容はアプリ本体だけ）またはCloudflare Pages。既にHTTPSサイトをお持ちならそこでも可。ファイルを `file://` で直接開いてもService Workerは起動せずPWAとしてインストールできません。
3. スマホでそのHTTPSページを開きます。Android Chromeの場合「アプリをインストール」または「ホーム画面に追加」、iPhoneのSafariの場合「共有」→「ホーム画面に追加」を選びます。
4. **ホーム画面のPeperReaderアイコンから開いた後で**、Windows版PeperTranslatorのLibraryから書き出したスマホ用ZIPをスマホに保存し、PWAの「論文ZIPを取り込む」を押します。
5. PDFと語彙が表示されたら、電波の届かない状態でも起動できます。PDFはメニューから個別保存も可能です。端末依存のため実機で確認してください。
6. 定期的に「設定・バックアップ」→「全データをZIPへバックアップ」を押し、ブラウザー外の場所へ保管してください。

## GitHub Pagesを使う場合の具体的な手順

A. GitHubで新しい**公開リポジトリ**（例：`peperreader-pwa`）を作成し、この配布ZIPのファイルを**展開して**リポジトリのルートにアップロードします。`index.html` がリポジトリのルートに存在する状態にしてください。

B. リポジトリの `Settings` → `Pages` → `Build and deployment` を `Deploy from a branch` にし、`main` / `(root)` を選んで保存します。

C. 配信されたHTTPS URL（例：`https://USERNAME.github.io/peperreader-pwa/`）をスマホのSafari/Chromeで開き、ホーム画面に追加します。リポジトリは公開されますが、そこに上げるのはアプリの静的コードだけです。自分の論文・単語・バックアップを含むZIPは絶対にコミット／アップロードしないでください。

D. GitHub Pagesのホスティングが不要なら、ご自身で管理するHTTPSの静的ホスティングでも使用できます。公開URLが変更されると端末内保存領域は別扱いになるので、先にバックアップしてください。

## Windows上でのデスクトップ動作確認

`START_LOCAL_PREVIEW.ps1` をPowerShellから実行してください。Python 3がある場合、`http://127.0.0.1:8765/` で開きます。**これはPC上のlocalhost確認用で、スマホからLANのHTTP経由で開いてもPWAとしてインストールできません。** HTTPSでの利用と端末内保存はブラウザー・OSの実機検証が必要です。

## 注意事項・制限

- 一度に読み込む持ち出しZIPは論文1～10件・圧縮済み160 MiBまで。PDF合計300 MiBまで。大きなZIPは分割してください。バックアップは全データ50論文・PDF合計300 MiBまでです。
- 古い論文のフォント・科学単位・数式は翻訳品質QAの対象外ではありません。QA不合格PDFは**確認用**であり、研究で使う数値は原文と照合してください。
- iOSのブラウザーやOSはPDF Blobのインライン表示を制限する場合があります。内蔵ビューアーで表示できなければ「PDF保存」で端末標準アプリを使用してください。
- ブラウザーのサイトデータ削除やストレージ不足でIndexedDBが消去される場合があります。明示的にバックアップを保存してください。
- スマホの復習履歴はPCのPeperTranslatorへ自動同期しません。PWAバックアップZIPの復元はスマホPWA間でのみ確認する設計です。
- `localStorage` は大容量のPDFに不向きなため、保存にはIndexedDBを利用しています。通信を使った書き出し・同期機構はありません。

## 検証・信頼性

Node.js + ZIP実データで19/19、Service Worker模擬検証10/10、静的結合検査8/8、合計37/37 PASS。ただし実ブラウザーのE2E起動試験は実行環境のChromium企業管理ポリシーが全ローカルURLをブロックするため未完了であり、iOS/Android実機でも未確認です。配布ZIPはソースと静的ファイルのみで、個人論文や語彙データは含まれていません。

This package includes JSZip, licensed under MIT. The license is in `vendor/JSZIP_LICENSE.md`.
