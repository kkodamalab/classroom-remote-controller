import os
import sys
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from desktop.controls import Controller
from desktop.security import Session
from desktop.ui import Window


@pytest.fixture
def window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    rows = [(100, 'First title', 'chrome.exe', 10)]
    monkeypatch.setattr(Controller, 'windows', lambda _: rows)
    monkeypatch.setattr(QTimer, 'singleShot', lambda *_: None)  # no external signaling
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(
        GetForegroundWindow=lambda:100, IsWindow=lambda _:True, GetClassName=lambda _:'Chrome_WidgetWin_1'))
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(GetWindowThreadProcessId=lambda _:(1, 10)))
    monkeypatch.setattr('desktop.controls.psutil.Process', lambda _:SimpleNamespace(name=lambda:'chrome.exe'))
    w = Window()
    yield w, rows
    w.focus_timer.stop()
    w.transport = None; w.session = None
    w.close()
    assert app is not None


def test_refresh_retains_same_hwnd_pid_despite_title_change(window):
    w, rows = window
    w.targets.setCurrentIndex(1)
    rows[0] = (100, 'New title', 'chrome.exe', 10)
    w.refresh()
    assert tuple(w.controller.target) == (100, 10, 'chrome.exe')
    assert 'New title' in w.targets.currentText()


def test_recreated_window_requires_explicit_reselection(window):
    w, rows = window
    w.targets.setCurrentIndex(1)
    rows[0] = (200, 'First title', 'chrome.exe', 10)
    w.refresh()
    assert w.controller.target is None
    assert '操作不可' in w.focus_status.text()


def test_failed_preflight_logged_without_repeated_timer_flood(window, monkeypatch):
    w, _ = window
    w.targets.setCurrentIndex(1)
    monkeypatch.setattr(sys.modules['win32gui'], 'GetForegroundWindow', lambda:200)
    w.update_focus()
    text = w.logs.toPlainText()
    assert 'focus_changed' in text and 'target_hwnd=100' in text and 'foreground_hwnd=200' in text
    w.update_focus()
    assert w.logs.toPlainText() == text


def test_approval_button_only_pending_and_operation_separate(window):
    w, _ = window
    assert not w.approval.isEnabled()
    s = Session(); w.session = s
    s.hello({'type':'hello', 'token':s.token, 'device':'スマートフォン'})
    w.pending(s.device); assert w.approval.isEnabled()
    s.approve(); w.pending(s.device); assert not w.approval.isEnabled()
    w.targets.setCurrentIndex(1); w.update_focus()
    assert '操作可能' in w.focus_status.text()
    assert '未実行' in w.last_result.text()
    w.operation_result(4, 'browser', 'next', False, 'profile_mismatch', {})
    assert '#4 browser/next' in w.last_result.text() and 'profile_mismatch' in w.last_result.text()
    s.revoke(); w.changed('切断')
    assert not w.approval.isEnabled() and '操作不可' in w.focus_status.text()
