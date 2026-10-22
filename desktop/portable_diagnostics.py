"""Offline packaged-process test. Explicit CLI mode only; all OS input is mocked."""
import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from desktop.controls import Controller
from desktop.security import Session, Rejected
from desktop.transport import Transport
from desktop.version import VERSION, APP_IDENTITY, DIAGNOSTICS_VERSION


async def run(window, report_path):
    # Import native COM before any injected adapters. CoInitialize/Uninitialize in
    # Transport still run on the real worker thread in the Windows EXE.
    import pythoncom
    import pywintypes
    import win32com.client
    assert APP_IDENTITY in window.windowTitle()
    assert APP_IDENTITY in window.logs.toPlainText()
    cases = []
    ui_thread = threading.get_ident()
    com_calls = []
    native_initialize, native_uninitialize = pythoncom.CoInitialize, pythoncom.CoUninitialize
    def initialize():
        native_initialize()
        com_calls.append(('initialize', threading.get_ident()))
    def uninitialize():
        native_uninitialize()
        com_calls.append(('uninitialize', threading.get_ident()))
    foreground = [100]
    gui = SimpleNamespace(IsWindow=lambda hwnd: hwnd == 100,
                          GetForegroundWindow=lambda: foreground[0],
                          GetClassName=lambda hwnd: 'PPTFrameClass')
    process = SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (1, 10))
    controller = Controller(); controller.target = (100, 10, 'powerpnt.exe')
    failures = [
        ('focus_changed', RuntimeError('focus_changed')),
        ('com_error', pywintypes.com_error(-2147221021, 'PRIVATE_SENTINEL', None, None)),
        ('win32_error', pywintypes.error(5, 'GetActiveObject', 'PRIVATE_SENTINEL')),
        ('not_approved', Rejected('not_approved')),
        ('unexpected_error', ValueError('PRIVATE_SENTINEL')),
    ]
    with patch.dict(sys.modules, {'win32gui': gui, 'win32process': process}), \
         patch('desktop.controls.psutil.Process', lambda _: SimpleNamespace(name=lambda:'powerpnt.exe')), \
         patch.object(pythoncom, 'CoInitialize', initialize), \
         patch.object(pythoncom, 'CoUninitialize', uninitialize):
        for seq, (expected, failure) in enumerate(failures, 1):
            session = Session()
            session.hello({'type':'hello', 'token':session.token, 'device':'offline self-test'})
            session.approve()
            messages, contexts = [], []
            foreground[0] = 200 if expected == 'focus_changed' else 100
            def prepare(context):
                contexts.append(context)
                return lambda profile, action, args: controller.execute(profile, action, args, authorize=session.authorize_operation, diagnostics=context)
            def com_failure(_):
                raise failure
            transport = Transport(session, {}, None, lambda _:None, lambda _:None,
                                  window.log, prepare=prepare, result=window.operation_result)
            transport.channel = SimpleNamespace(readyState='open', send=lambda raw:messages.append(json.loads(raw)))
            with patch('win32com.client.GetActiveObject', com_failure):
                # Exercise real receive/validation -> worker -> Controller.check
                # -> COM failure classification -> Qt PC log and wire response.
                transport.receive(json.dumps({'type':'command', 'seq':seq, 'profile':'powerpoint', 'action':'next', 'args':{}}))
                await asyncio.gather(*list(transport.tasks))
            assert messages[-1]['code'] == expected, (expected, messages)
            log_line = window.logs.toPlainText().splitlines()[-1]
            assert f'#{seq} powerpoint/next: {expected}' in log_line
            assert 'target_hwnd=100' in log_line and 'target_pid=10' in log_line
            assert 'foreground_hwnd=' in log_line and 'focus_match=' in log_line
            assert 'PRIVATE_SENTINEL' not in log_line + json.dumps(messages)
            if expected == 'com_error':
                assert 'native=-2147221021' in log_line and 'category=com' in log_line
            assert expected in window.last_result.text()
            cases.append({'code':expected, 'pc_log':log_line, 'wire_code':messages[-1]['code'],
                          'last_result':window.last_result.text(), 'context':contexts[-1]})
    assert len(com_calls) == (10 if sys.platform == 'win32' else 0)
    assert all(tid != ui_thread for _, tid in com_calls)
    for index in range(0, len(com_calls), 2):
        assert com_calls[index][0] == 'initialize' and com_calls[index+1][0] == 'uninitialize'
        assert com_calls[index][1] == com_calls[index+1][1]
    report = {'version':VERSION, 'title':window.windowTitle(), 'diagnostics_version':DIAGNOSTICS_VERSION,
              'frozen':bool(getattr(sys, 'frozen', False)), 'platform':sys.platform,
              'worker_com_initializations':len(com_calls)//2, 'worker_com_balanced':True, 'cases':cases,
              'os_input':'mocked; no real PowerPoint/Windows input executed', 'status':'passed'}
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
