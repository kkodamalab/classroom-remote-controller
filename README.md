# Classroom Remote Controller

教室のHDMI接続Windows PCを、QRでペアリングしたスマホのWebブラウザから操作する実験版です。画面転送は行いません。

- Web: https://kkodamalab.github.io/classroom-remote-controller/
- EXE: https://github.com/kkodamalab/classroom-remote-controller/releases
- 検証記録: [docs/VALIDATION.md](docs/VALIDATION.md)
- プロトコル: [shared/PROTOCOL.md](shared/PROTOCOL.md)

## 接続手順

1. Releaseから `ClassroomRemoteController.exe` をWindows PCに保存して起動します。x64向け、インストール・管理者権限不要。未署名のためWindowsの評判ベース警告が出る場合があります。出所とSHA256を確認してください。自動起動登録はしません。
2. PowerPoint、PDF、動画等をPCで開き、PCアプリの「対象ウィンドウを更新」から選択します。「対象を固定する」は通常ONにします。
3. 起動時に表示されたQRをスマホのカメラで読み取ります（5分以内）。端末名を入力して「接続を開始」を押します。Webにカメラ権限は不要です。
4. PC側で端末名を確認して承認します。名前は自己申告なので、手元のスマホで接続した直後に承認してください。
5. PCで操作対象アプリを前面に戻します。承認画面が前面のままでは入力を拒否します。スマホで対応するプロファイルを選び操作します。
6. 終了時はPCまたはスマホの「緊急切断」。再接続はPCで「新しいQRを発行」し、読み取りと承認をやり直します。旧トークンの自動再利用はありません。

スマホUIはSLIDE / VIDEO / PCの3タブ。デモはWeb URLの末尾に `?demo=1` を追加（PC操作なし）。通常アクセスだけでは接続できません。QR URLを共有しないでください。

## 対応機能と制約

|プロファイル|操作|方式・注意|
|---|---|---|
|PowerPoint|前・次・開始・終了・ブラックアウト|COM。通常表示の前後移動、スライドショー操作。COM失敗時は明示失敗、キー入力への自動フォールバックなし。複数プレゼン同時表示は対象誤認防止のため避けてください|
|PDF / Edge|前後ページ・ズーム|標準キー。ページ番号指定は未対応|
|PDF / Acrobat|前後ページ・ズーム・ページ番号|ページ指定は標準ダイアログを識別できた場合のみ。新UIや独自ダイアログは拒否|
|Browser|スクロール・戻る・進む・タブ切替・ページ送り|Chrome/Edge/Firefoxの標準キー|
|YouTube|再生/一時停止・±10秒・音量・ミュート|K/J/L等。検索欄ではなくプレイヤーにフォーカスを置く必要あり。URL/DOMの識別は未実装|
|VLC|再生/一時停止・±10秒・音量・ミュート|標準ショートカット。設定変更時の動作は保証しない|
|Windows|アプリ切替・音量・ミュート・Esc|アプリ切替はロックOFFのみ。その後の操作にはPCで対象の再選択が必要|
|Mouse|相対移動・左右クリック・スクロール|ロックON必須。対象ウィンドウ内、他ウィンドウの重なりを除外。最大40px/軸/コマンド、20コマンド/秒の制限|

「送信済み」は実行成功を意味しません。COM完了、入力送出済み（画面結果未確認）、拒否/失敗、結果タイムアウトを区別します。キーボード操作はアプリ内のフォーカスや独自キー設定に影響されます。OSのフォーカス確認と入力の間には微小な競合窓があり、完全な原子性はありません。管理者権限で動くアプリ、UAC画面、保護コンテンツは対象外です。

画面キャプチャ・録画・ファイル送信・任意シェル・任意文字列入力のAPIはありません。Acrobatページ番号のみ、スキーマ検証した整数を既知の入力欄に設定します。操作ログはメモリ上の200行に限定し、トークン・SDP・端末URLを記録しません。

## 外部通信サービス

GitHub Pagesは静的Webのみを配信します。シグナリングやTURNをPages上で実行することはできません。

初期構成:

- **シグナリング**: PeerJS Cloud `0.peerjs.com:443` / WSS、path `/`、key `peerjs`。公開共有サービスであり稼働保証はありません。セッションIDと接続メタデータを扱います。
- **STUN**: Google `stun:stun.l.google.com:19302`。NAT越え候補の収集に使用します。
- **TURN**: 初期設定では**なし**。対称NAT、P2P/UDP制限、大学のネットワークで接続できない場合はTURNが必要です。
- **データ**: PeerJS raw/ordered/reliable DataChannel ↔ Python aiortc。DTLS暗号化。メディアトラックなし。

PC設定はEXEと同じフォルダーの `config.json`（ソース実行時はカレントフォルダー）。`desktop/config.example.json` をコピーして編集します。設定には秘密情報を含む場合があるためGitに追加しません。

### 自前PeerServer

外部VM等で公式PeerServerを動かし、Caddy/nginx等で有効なTLS証明書とWebSocket転送を設定します。例:

```sh
docker run -d --name classroom-peer -p 127.0.0.1:9000:9000 peerjs/peerjs-server --port 9000 --path /
```

Caddyfile例（DNSをVMに向け、80/443を許可）:

```text
signal.example.edu {
  reverse_proxy 127.0.0.1:9000
}
```

PC設定の `host` を `signal.example.edu`、`port` を443、`path` を `/` にします。QRに設定が含まれ、スマホは同じPeerServerへ接続します。運用時は接続数・要求頻度制限、監視、更新、ログ保持方針を設定してください。PeerServerのkeyは認証秘密ではありません。

### TURN

外部のcoturnまたは組織が契約したTURNサービスを用意します。UDP/TCP 3478、TLS 5349（制限環境では専用ホストのTLS 443）、relay用UDPポート範囲をFW/NATで開き、TLS証明書・外部IP・認証を設定します。認証なしの公開relayは使用しません。

PCの `iceServers` と、GitHub Repository Settings → Secrets and variables → Actions → **Variables** の `VITE_ICE_SERVERS` に、同じ到達可能な構成を設定しPagesを再デプロイします:

```json
[
  {"urls":"stun:stun.l.google.com:19302"},
  {"urls":["turn:turn.example.edu:3478?transport=udp","turns:turn.example.edu:443?transport=tcp"],"username":"SHORT_LIVED_USERNAME","credential":"SHORT_LIVED_PASSWORD"}
]
```

**Webのビルド変数は公開されます。永続TURN認証情報やcoturn共有署名鍵を置かないでください。** 現段階では授業期間に合わせた短期資格情報の手動配布/再ビルドを想定します。資格情報を動的発行するバックエンド、relay強制モード、学内プロキシへの対応は未実装です。TURN設定を入れただけで到達性が保証されるわけではありません。大学管理者にWSS・STUN/TURNの許可を確認してください。

接続失敗はPC・Webに表示され、承認済みDataChannelが開くまで操作できません。45秒の接続/承認タイムアウト、12秒のハートビート停止検知があります。シグナリング切断でも安全側に切断します。

## 開発とテスト

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r desktop/requirements.txt pytest pyinstaller
.\.venv\Scripts\python -m desktop.main
npm --prefix web ci
npm --prefix web run dev
npm --prefix web run build
.\.venv\Scripts\python -m pytest tests -q
```

実通信テスト（EdgeがインストールされたWindows、インターネット接続が必要。OS入力なし）:

```powershell
.\.venv\Scripts\python -m pip install playwright
.\.venv\Scripts\python -m tests.interop_browser
.\.venv\Scripts\python -m tests.web_smoke
```

Portable EXEビルド:

```powershell
.\.venv\Scripts\python -m PyInstaller --noconfirm --paths . --clean --onefile --windowed --name ClassroomRemoteController --collect-all aiortc --collect-all aioice --hidden-import win32timezone --hidden-import pythoncom --hidden-import win32com.client desktop/main.py
```

`dist/ClassroomRemoteController.exe` は一時フォルダーに展開して実行されます（Portable＝完全にディスク書込なしではありません）。CIはWebビルド・Windows自動テスト・EXEビルド・`--self-test`起動確認を実行します。mainはPagesへ、`v*`タグはEXEとSHA256付きの実験版Releaseへ公開します。

PC操作はワーカースレッドで実行し、COM待機中も緊急停止UIを応答可能に保ちます。停止は新規操作を直ちに拒否しますが、既にOS/COMに渡した操作を取り消すことはできません。実行中の追加コマンドは `executor_busy` として拒否し、キューに溜めません。

## Phase完了条件

|Phase|成果物の条件|受入状態|
|---|---|---|
|1|3タブUI、PC承認UI、モック、プロトコル|実装済み・Webビルド/PC UI構築確認|
|2|QR、明示承認、WebRTC、失効/重複抑止|実装済み・Edge↔aiortc実通信確認。スマホ実機未検証|
|3|対象確認、PowerPoint/PDF/Browser|実装済み・実アプリ受入検証未完了|
|4|Video/Windows/Mouse、安全制限|実装済み・実アプリ受入検証未完了|
|5|自動テスト、Windowsビルド、Pages、Release|CI/公開結果は検証記録を参照。全実機受入は未完了|

## 次の改善候補

実機マトリクス完了、プロファイル別UI Automationによるアプリ内フォーカス確認、PowerPoint複数ウィンドウの厳密な対応、短期TURN資格情報API、詳細ICE診断、コード署名、依存関係の完全固定、アクセシビリティ監査。

## 参照

- [PeerJS API](https://peerjs.com/client/api/peer) / [PeerServer](https://github.com/peers/peerjs-server)
- [aiortc API](https://aiortc.readthedocs.io/en/latest/api.html)
- [PowerPoint SlideShowView.State](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.slideshowview.state)
- [coturn](https://github.com/coturn/coturn)

MIT License。
