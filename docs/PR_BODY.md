## 実装

空のリポジトリから、QRでWindows PCとスマホをペアリングする実験版を構築しました。Reactの3タブUI、PySide6のQR/明示承認/緊急停止、PeerJS CloudとaiortcのDataChannel、期限・重複抑止・レート制限、対象アプリとフォーカス確認、操作プロファイルを含みます。

入力送出と実行結果を区別し、接続失敗を成功として表示しません。切断すると旧トークンを失効し、新QRでの承認が必要です。GitHub Pages、Windows Portable EXEビルドと実験版ReleaseのActionsを追加しました。

## 検証

- TypeScript/Vite本番ビルド成功
- 認証/期限/重複/allowlist/引数/レート/対象フォーカスの自動テスト成功
- Windows上の実Edgeと公共PeerJS Cloud、Python aiortcの実DataChannel接続成功（操作実行器はモック）
- PySide6 UI構築成功

iPhone/Android、PowerPoint/PDF/動画の実アプリ操作、学内ネットワーク/TURNは未検証です。Phase別の受入条件と残項目はREADME、詳細はdocs/VALIDATION.mdに記録しています。署名なしpre-releaseとして公開します。
