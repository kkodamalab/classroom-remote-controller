import sys
from types import SimpleNamespace
import pytest
from desktop.controls import Controller


def setup(monkeypatch, foreground=100, exe='chrome.exe'):
    gui=SimpleNamespace(IsWindow=lambda _:True,GetForegroundWindow=lambda:foreground,GetClassName=lambda _:'other')
    monkeypatch.setitem(sys.modules,'win32gui',gui)
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(GetWindowThreadProcessId=lambda _:(1,10)))
    monkeypatch.setattr('desktop.controls.psutil.Process',lambda _:SimpleNamespace(name=lambda:exe))
    c=Controller();c.target=(100,10,exe);return c


def test_focus_change_rejected(monkeypatch):
    c=setup(monkeypatch,200)
    with pytest.raises(RuntimeError,match='focus_changed'):c.execute('browser','next',{})


def test_wrong_application_rejected(monkeypatch):
    c=setup(monkeypatch)
    with pytest.raises(RuntimeError,match='profile_mismatch'):c.execute('powerpoint','next',{})


def test_switch_denied_when_locked(monkeypatch):
    c=setup(monkeypatch)
    with pytest.raises(RuntimeError,match='target_locked'):c.execute('windows','switch_app',{})


def test_mouse_requires_lock(monkeypatch):
    c=setup(monkeypatch);c.locked=False
    with pytest.raises(RuntimeError,match='mouse_requires_lock'):c.execute('mouse','move',{'dx':1,'dy':1})
