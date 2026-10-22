import asyncio
import json
import sys
import threading
from types import SimpleNamespace

import pytest

from desktop.controls import Controller
from desktop.diagnostics import ERRORS, classify
from desktop.security import Rejected, Session
from desktop.transport import Transport


@pytest.fixture
def windows(monkeypatch):
    state = SimpleNamespace(foreground=100, pid=10, exe='chrome.exe', valid=True,
                            classname='Chrome_WidgetWin_1', keys=[])
    gui = SimpleNamespace(IsWindow=lambda hwnd: state.valid and hwnd == 100,
                          GetForegroundWindow=lambda: state.foreground,
                          GetClassName=lambda hwnd: state.classname)
    monkeypatch.setitem(sys.modules, 'win32gui', gui)
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (1, state.pid)))
    monkeypatch.setitem(sys.modules, 'win32api', SimpleNamespace(keybd_event=lambda *args: state.keys.append(args)))
    monkeypatch.setitem(sys.modules, 'win32con', SimpleNamespace(KEYEVENTF_KEYUP=2))
    monkeypatch.setattr('desktop.controls.psutil.Process', lambda pid: SimpleNamespace(name=lambda: state.exe))
    return state


def controller(exe='chrome.exe'):
    c = Controller(); c.target = (100, 10, exe)
    return c


@pytest.mark.parametrize('action,key', [('scroll_up', 38), ('scroll_down', 40), ('next', 34), ('previous', 33), ('back', 18), ('forward', 18)])
def test_chrome_focused_key_dispatch(windows, action, key):
    context = {}
    assert controller().execute('browser', action, {}, diagnostics=context) == 'input_dispatched_unverified'
    assert windows.keys[0][0] == key and windows.keys[-1][2] == 2
    assert context['focus_match'] and context['target_valid'] and context['foreground_pid'] == 10
    assert context['checks'] == 2  # includes immediate check before input


def test_chrome_restore_foreground_without_reconnect(windows):
    c = controller(); windows.foreground = 200
    with pytest.raises(RuntimeError, match='focus_changed'):
        c.execute('browser', 'next', {})
    assert not windows.keys
    windows.foreground = 100
    assert c.execute('browser', 'next', {}) == 'input_dispatched_unverified'


@pytest.mark.parametrize('change', ['hwnd', 'pid', 'exe'])
def test_recreated_or_reused_target_is_not_retargeted(windows, change):
    c = controller()
    if change == 'hwnd': windows.valid = False; windows.foreground = 200
    elif change == 'pid': windows.pid = 20
    else: windows.exe = 'other.exe'
    with pytest.raises(RuntimeError, match='target_changed'):
        c.execute('browser', 'next', {})
    assert not windows.keys


def test_profile_mismatch_has_no_os_input(windows):
    with pytest.raises(RuntimeError, match='profile_mismatch'):
        controller().execute('powerpoint', 'next', {})
    assert not windows.keys


def test_focus_change_between_checks_rejects_input(windows):
    count = []
    def guard():
        count.append(1)
        if len(count) == 1: windows.foreground = 200
    with pytest.raises(RuntimeError, match='focus_changed'):
        controller().execute('browser', 'next', {}, authorize=guard)
    assert not windows.keys


def test_zero_foreground_rejected_with_diagnostics(windows):
    windows.foreground = 0
    context = {}
    with pytest.raises(RuntimeError, match='focus_changed'):
        controller().execute('browser', 'next', {}, diagnostics=context)
    assert context['foreground_hwnd'] == 0 and context['foreground_pid'] == 0


def powerpoint(monkeypatch, windows, slideshow=False, mismatched=False):
    windows.exe = 'powerpnt.exe'
    windows.classname = 'screenClass' if slideshow else 'PPTFrameClass'
    windows.foreground = 200 if slideshow else 100
    calls = []
    presentation = SimpleNamespace(FullName='local-document-not-for-logs', Slides=SimpleNamespace(Count=10))
    view = SimpleNamespace(Slide=SimpleNamespace(SlideIndex=3), GotoSlide=lambda index: calls.append(index),
                           Next=lambda: calls.append('next'), Previous=lambda: calls.append('previous'))
    edit = SimpleNamespace(HWND=100, Presentation=presentation, View=view)
    show = SimpleNamespace(HWND=200, Presentation=SimpleNamespace(FullName='other-document') if mismatched else presentation, View=view)
    class Collection:
        def __init__(self, items): self.items, self.Count = items, len(items)
        def __call__(self, index): return self.items[index - 1]
    app = SimpleNamespace(HWND=100, Windows=Collection([edit]), SlideShowWindows=Collection([show] if slideshow else []))
    client = SimpleNamespace(GetActiveObject=lambda name: app)
    monkeypatch.setitem(sys.modules, 'win32com', SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, 'win32com.client', client)
    return calls


@pytest.mark.parametrize('slideshow', [False, True])
@pytest.mark.parametrize('action,expected', [('next', 4), ('previous', 2)])
def test_powerpoint_edit_and_show_hwnds(monkeypatch, windows, slideshow, action, expected):
    calls = powerpoint(monkeypatch, windows, slideshow)
    context = {}
    assert controller('powerpnt.exe').execute('powerpoint', action, {}, diagnostics=context) == 'com_completed'
    assert calls == [action if slideshow else expected]
    assert context['com_window_match'] and context['slideshow_match'] == slideshow
    assert not windows.keys


def test_other_presentation_slideshow_is_rejected(monkeypatch, windows):
    calls = powerpoint(monkeypatch, windows, True, True)
    with pytest.raises(RuntimeError, match='com_presentation_mismatch'):
        controller('powerpnt.exe').execute('powerpoint', 'next', {})
    assert not calls and not windows.keys


def test_snapshot_does_not_follow_ui_selection(windows):
    c = controller(); snapshot = c.snapshot(); c.target = (200, 20, 'other.exe'); c.locked = False
    assert snapshot.target == (100, 10, 'chrome.exe') and snapshot.locked
    assert snapshot.execute('browser', 'next', {}) == 'input_dispatched_unverified'


@pytest.fixture
def native_errors(monkeypatch):
    class ComError(Exception):
        hresult = -2147221008
    class Win32Error(Exception):
        winerror = 5
    monkeypatch.setitem(sys.modules, 'pywintypes', SimpleNamespace(com_error=ComError, error=Win32Error))
    return ComError, Win32Error


@pytest.mark.parametrize('kind,expected,category', [
    ('runtime', 'focus_changed', 'runtime'), ('rejected', 'not_approved', 'rejected'),
    ('com', 'com_error', 'com'), ('win32', 'win32_error', 'win32'),
    ('unknown_runtime', 'runtime_error', 'runtime'), ('unexpected', 'unexpected_error', 'unexpected'),
])
def test_error_code_log_and_phone_redaction(native_errors, kind, expected, category):
    secret = 'C:/private/token-SDP-password'
    types = {'runtime': lambda: RuntimeError('focus_changed'), 'rejected': lambda: Rejected('not_approved'),
             'com': lambda: native_errors[0](secret), 'win32': lambda: native_errors[1](secret),
             'unknown_runtime': lambda: RuntimeError(secret), 'unexpected': lambda: ValueError(secret)}
    async def run():
        s = Session(); s.hello({'type': 'hello', 'token': s.token, 'device': 'phone'}); s.approve()
        sent, logs, results = [], [], []
        def fail(*args): raise types[kind]()
        t = Transport(s, {}, fail, lambda _: None, lambda _: None, logs.append,
                      result=lambda *args: results.append(args))
        t.channel = SimpleNamespace(readyState='open', send=lambda raw: sent.append(json.loads(raw)))
        await t.run_command(7, 'powerpoint', 'next', {})
        assert sent[-1] == {'type': 'result', 'seq': 7, 'ok': False, 'code': expected, 'message': ERRORS[expected]}
        assert f'category={category}' in logs[-1] and f'#7 powerpoint/next: {expected}' in logs[-1]
        assert secret not in ''.join(logs) + json.dumps(sent)
        assert 'stack=' in logs[-1] or category == 'rejected'
        assert results[-1][4] == expected and not t.executing
        assert not s.revoked  # execution rejection does not force reconnection
    asyncio.run(run())


def test_com_failure_has_no_keyboard_fallback(monkeypatch, windows, native_errors):
    powerpoint(monkeypatch, windows)
    def fail(_): raise native_errors[0]('private presentation path')
    sys.modules['win32com.client'].GetActiveObject = fail
    with pytest.raises(native_errors[0]) as caught:
        controller('powerpnt.exe').execute('powerpoint', 'next', {})
    assert classify(caught.value)[0] == 'com_error'
    assert not windows.keys


def test_prepare_on_ui_thread_com_balanced_on_worker(monkeypatch, native_errors):
    async def run():
        ui_thread = threading.get_ident(); calls = []
        s = Session(); s.hello({'type':'hello', 'token':s.token, 'device':'phone'}); s.approve()
        def prepare(context):
            assert threading.get_ident() == ui_thread
            context['target_hwnd'] = 100
            def execute(*_):
                calls.append(('execute', threading.get_ident()))
                raise native_errors[0]('not copied')
            return execute
        t = Transport(s, {}, None, lambda _:None, lambda _:None, lambda _:None, prepare=prepare)
        monkeypatch.setitem(sys.modules, 'pythoncom', SimpleNamespace(
            CoInitialize=lambda: calls.append(('init', threading.get_ident())),
            CoUninitialize=lambda: calls.append(('uninit', threading.get_ident()))))
        # Scope platform override to work() without affecting asyncio creation.
        original_to_thread = asyncio.to_thread
        async def win_thread(fn):
            def wrapper():
                with monkeypatch.context() as scoped:
                    scoped.setattr(sys, 'platform', 'win32')
                    return fn()
            return await original_to_thread(wrapper)
        monkeypatch.setattr(asyncio, 'to_thread', win_thread)
        await t.run_command(1, 'powerpoint', 'next', {})
        assert [name for name, _ in calls] == ['init', 'execute', 'uninit']
        assert len({tid for _, tid in calls}) == 1 and calls[0][1] != ui_thread
    asyncio.run(run())


def test_revoked_session_prevents_worker_execution():
    async def run():
        s = Session(); s.revoke(); calls = []
        t = Transport(s, {}, lambda *_:calls.append(1), lambda _:None, lambda _:None, lambda _:None)
        await t.run_command(1, 'browser', 'next', {})
        assert not calls
    asyncio.run(run())
