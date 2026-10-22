// Display only known protocol codes; never render arbitrary exception text.
export const errors: Record<string, string> = {
  no_target: 'PCで操作対象を選択してください。再接続は不要です。',
  target_changed: '対象が閉じられたか作り直されました。PCで対象を更新して選び直してください。',
  focus_changed: 'PCで選択した対象ウィンドウを前面に戻してください。再接続は不要です。',
  profile_mismatch: 'スマホの操作プロファイルとPCで選んだアプリを合わせてください。',
  target_locked: 'アプリ切替にはPCの対象固定をOFFにしてください。切替後は対象を選び直してください。',
  mouse_requires_lock: 'PCの「対象を固定する」をONにしてください。',
  pointer_outside_target: 'PCのポインターを対象内へ移し、別ウィンドウの重なりを避けてください。',
  com_target_mismatch: 'PowerPointのプロセスが異なります。PCで操作するPowerPointを選び直してください。',
  com_window_mismatch: '対応するPowerPoint文書を確認できません。PCで対象を更新して選び直してください。',
  com_presentation_mismatch: '選択した文書のスライドショーをPCで前面にしてください。',
  slideshow_not_running: 'スライドショーの「開始」を押してください。',
  slideshow_not_foreground: '操作するスライドショーをPCで前面にしてください。',
  page_dialog_unrecognized: 'Acrobatのページ移動欄を確認できません。ダイアログを閉じ、前後ページ操作を使ってください。',
  unsupported: '対応するプロファイル・操作を選んでください。',
  com_error: 'PowerPointのCOM操作に失敗しました。PCのエラー番号と文書・ダイアログの状態を確認してください。',
  win32_error: 'Windows操作に失敗しました。PCのエラー番号と対象アプリの権限・状態を確認してください。',
  runtime_error: '実行時エラーです。PCの診断ログを確認してください。',
  unexpected_error: '予期しないエラーです。PCの型名と診断スタックを確認してください。',
  target_focus_or_execution_failed: '旧EXEでは理由を表示できません。診断対応の新しいEXEに更新してください。',
  executor_busy: '前の操作を処理中です。結果を待ってから操作してください。',
  duplicate: '重複した操作を拒否しました。自動再送はしません。',
  rate_limit: '操作が速すぎます。少し待ってください。',
  session_expired: '有効期限が切れました。PCで新しいQRを発行してください。',
  not_approved: 'PCで接続を承認してください。',
  schema: '操作形式が正しくありません。Webを更新してください。',
  sequence: '操作番号が正しくありません。Webを更新してください。',
  not_allowed: '対応する操作を選んでください。',
  arguments: '操作の入力値を確認してください。',
  rejected: '安全確認で拒否しました。PCの診断ログを確認してください。',
};
export function failure(code: unknown): string {
  return typeof code === 'string' && Object.hasOwn(errors, code)
    ? `${errors[code]} [${code}]` : '操作に失敗しました。PCの診断ログを確認してください。';
}
