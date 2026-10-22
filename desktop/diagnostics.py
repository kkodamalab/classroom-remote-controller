"""Allowlisted wire errors and local diagnostics without exception text or paths."""
import re
import traceback

from desktop.security import Rejected


ERRORS = {
    'no_target': 'PCで操作対象ウィンドウを選択してください。接続のやり直しは不要です。',
    'target_changed': '対象ウィンドウが閉じられたか作り直されました。PCで対象を更新して選び直してください。',
    'focus_changed': '選択した対象と前面ウィンドウが異なります。PCで選択したウィンドウを前面に戻してください。',
    'profile_mismatch': '対象アプリと操作プロファイルが一致しません。スマホのプロファイルとPCの選択を合わせてください。',
    'target_locked': 'アプリ切替にはPCの対象固定を解除してください。切替後は操作対象を選び直してください。',
    'mouse_requires_lock': 'マウス操作にはPCの「対象を固定する」をONにしてください。',
    'pointer_outside_target': 'PCのポインターを対象ウィンドウ内に置き、重なった別ウィンドウを避けてください。',
    'com_target_mismatch': 'PowerPointのプロセスが選択対象と異なります。操作するPowerPointを選び直してください。',
    'com_window_mismatch': '選択したウィンドウに対応するPowerPoint文書を確認できません。対象を更新して選び直してください。',
    'com_presentation_mismatch': '前面のスライドショーと選択した文書が異なります。選択した文書を前面にしてください。',
    'slideshow_not_running': 'スライドショーが開始されていません。「開始」を押してください。',
    'slideshow_not_foreground': '操作するスライドショーをPCで前面にしてください。',
    'page_dialog_unrecognized': 'Acrobatのページ移動欄を確認できません。ダイアログを閉じ、前後ページ操作を使ってください。',
    'unsupported': 'この操作には対応していません。対応するプロファイルを選んでください。',
    'com_error': 'PowerPointのCOM操作に失敗しました。PCのエラー番号を確認し、文書・ダイアログの状態を確認してください。',
    'win32_error': 'Windows操作に失敗しました。PCのエラー番号と対象アプリの権限・状態を確認してください。',
    'runtime_error': '操作処理で実行時エラーが発生しました。PCの診断ログを確認してください。',
    'unexpected_error': '予期しない操作エラーです。PCの型名と診断スタックを確認してください。',
    'session_expired': '接続の有効期限が切れました。PCで新しいQRを発行してください。',
    'not_approved': 'PCで接続を承認してください。',
    'executor_busy': '前の操作を処理中です。結果を待ってから操作してください。',
    'duplicate': '重複した操作を拒否しました。自動再送はしません。',
    'rate_limit': '操作が速すぎます。少し待って操作してください。',
    'schema': '操作形式が正しくありません。Webを更新してください。',
    'sequence': '操作番号が正しくありません。Webを更新してください。',
    'not_allowed': '許可されていない操作です。対応する操作を選んでください。',
    'arguments': '操作の値が範囲外です。入力値を確認してください。',
    'rejected': '安全確認により操作を拒否しました。PCの診断ログを確認してください。',
}
CONTROL_ERRORS = frozenset({
    'no_target', 'target_changed', 'focus_changed', 'profile_mismatch', 'target_locked',
    'mouse_requires_lock', 'pointer_outside_target', 'com_target_mismatch',
    'com_window_mismatch', 'com_presentation_mismatch', 'slideshow_not_running',
    'slideshow_not_foreground', 'page_dialog_unrecognized', 'unsupported',
})


def safe_name(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', value) else 'unknown'


def classify(exc):
    """Never use arbitrary exception messages as protocol fields or log messages."""
    native = None
    try:
        import pywintypes
    except ImportError:
        pywintypes = None
    if isinstance(exc, Rejected):
        category, code = 'rejected', str(exc) if str(exc) in ERRORS else 'rejected'
    elif pywintypes and isinstance(exc, pywintypes.com_error):
        category, code, native = 'com', 'com_error', getattr(exc, 'hresult', None)
    elif (pywintypes and isinstance(exc, pywintypes.error)) or (isinstance(exc, OSError) and type(getattr(exc, 'winerror', None)) is int):
        category, code, native = 'win32', 'win32_error', getattr(exc, 'winerror', None)
    elif isinstance(exc, RuntimeError):
        category, code = 'runtime', str(exc) if str(exc) in CONTROL_ERRORS else 'runtime_error'
    else:
        category, code = 'unexpected', 'unexpected_error'
    detail = f'category={category} type={safe_name(type(exc).__name__)}'
    if type(native) is int:
        detail += f' native={native} (0x{native & 0xffffffff:08X})'
    # Frame locations only: no source lines, exception text, locals, absolute paths,
    # document names, token/SDP/credential values, or chained exception messages.
    if category in ('unexpected', 'runtime', 'com', 'win32'):
        frames = []
        for frame, line in traceback.walk_tb(exc.__traceback__):
            filename = frame.f_code.co_filename.replace('\\', '/').rsplit('/', 1)[-1]
            module = filename if filename in {'transport.py', 'controls.py', 'ui.py', 'security.py', 'diagnostics.py'} else '<external>'
            frames.append(f'{module}:{line}:{safe_name(frame.f_code.co_name)}')
        detail += ' stack=' + ' > '.join(frames[-12:])
    return code, detail


def context_text(context):
    """Only known numeric/boolean fields and sanitized executable basenames."""
    fields = []
    for key in ('target_hwnd', 'target_pid', 'foreground_hwnd', 'foreground_pid', 'locked', 'target_valid', 'focus_match', 'slideshow_match', 'checks', 'com_target_hwnd', 'com_window_match', 'com_show_match'):
        value = context.get(key)
        if type(value) in (int, bool) or value is None:
            fields.append(f'{key}={value}')
    for key in ('target_exe', 'foreground_exe'):
        value = context.get(key, '')
        if isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}', value):
            fields.append(f'{key}={value}')
    return ' '.join(fields)
