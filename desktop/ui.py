import asyncio
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
import qrcode
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QComboBox, QCheckBox, QPlainTextEdit, QMessageBox
from desktop.security import Session
from desktop.diagnostics import ERRORS, classify, context_text
from desktop.version import APP_IDENTITY, DIAGNOSTICS_VERSION


class Window(QMainWindow):
    def __init__(self, autostart=True):
        super().__init__()
        self.setWindowTitle(APP_IDENTITY)
        self.resize(580, 820)
        self.transport = None
        self.session = None
        self.renewing = False
        self.focus_observation = None
        self.setStyleSheet('QWidget {background:#101b29;color:#edf3f5;font-size:14px} QPushButton,QComboBox {padding:12px;background:#23374e;border-radius:6px} QPlainTextEdit {background:#09121d}')
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root)
        self.status = QLabel('セッション準備中'); layout.addWidget(self.status)
        self.identity = QLabel(f'{APP_IDENTITY} ／ 診断機能 v{DIAGNOSTICS_VERSION}'); layout.addWidget(self.identity)
        self.target_status = QLabel('対象：未選択'); self.target_status.setWordWrap(True); layout.addWidget(self.target_status)
        self.focus_status = QLabel('操作不可：対象を選択してください'); self.focus_status.setWordWrap(True); layout.addWidget(self.focus_status)
        self.last_result = QLabel('最後の操作：未実行（接続成功と操作成功は別です）'); self.last_result.setWordWrap(True); layout.addWidget(self.last_result)
        self.qr = QLabel(); layout.addWidget(self.qr)
        self.device = QLabel('端末：未接続'); layout.addWidget(self.device)
        self.targets = QComboBox(); layout.addWidget(self.targets)
        refresh = QPushButton('対象ウィンドウを更新'); refresh.clicked.connect(self.refresh); layout.addWidget(refresh)
        self.lock = QCheckBox('対象を固定する（推奨）'); self.lock.setChecked(True); layout.addWidget(self.lock)
        self.targets.currentIndexChanged.connect(self.select_target)
        self.lock.toggled.connect(self.select_target)
        self.approval = QPushButton('表示された端末の接続を承認'); self.approval.setEnabled(False); self.approval.clicked.connect(self.approve); layout.addWidget(self.approval)
        reject = QPushButton('拒否 / 緊急切断'); reject.setStyleSheet('background:#913d50;font-weight:bold'); reject.clicked.connect(self.emergency); layout.addWidget(reject)
        renew = QPushButton('新しいQRを発行'); renew.clicked.connect(lambda: asyncio.create_task(self.new_session())); layout.addWidget(renew)
        self.logs = QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.setMaximumBlockCount(200); layout.addWidget(self.logs)
        self.log(f'{APP_IDENTITY} diagnostics={DIAGNOSTICS_VERSION} 起動')
        from desktop.controls import Controller
        self.controller = Controller()
        self.refresh()
        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self.update_focus)
        if autostart:
            self.focus_timer.start(750)
            QTimer.singleShot(0, lambda: asyncio.create_task(self.new_session()))

    def log(self, message):
        self.logs.appendPlainText(message)

    def refresh(self):
        previous = tuple(self.controller.target) if self.controller.target else None
        self.targets.blockSignals(True)
        self.targets.clear()
        self.targets.addItem('対象ウィンドウを選択してください', None)
        for hwnd, title, exe, pid in self.controller.windows():
            self.targets.addItem(f'{exe} — {title[:80]}', (hwnd, pid, exe))
            if previous == (hwnd, pid, exe):
                self.targets.setCurrentIndex(self.targets.count() - 1)
        self.targets.blockSignals(False)
        self.select_target()

    def select_target(self, *_):
        self.controller.target = self.targets.currentData()
        self.controller.locked = self.lock.isChecked()
        self.update_focus()

    def update_focus(self):
        snapshot = self.controller.snapshot()
        target = snapshot.target
        self.target_status.setText(f'対象：{target[2]} HWND={target[0]} PID={target[1]} ／ 固定={snapshot.locked}' if target else '対象：未選択')
        code, detail = None, ''
        try:
            snapshot.check('powerpoint' if target and target[2] == 'powerpnt.exe' else 'mouse')
        except Exception as exc:
            code, detail = classify(exc)
        approved = bool(self.session and self.session.approved and not self.session.revoked)
        context = snapshot.diagnostics
        observation = (code, target, snapshot.locked, context.get('foreground_hwnd'), context.get('foreground_pid'), detail)
        if code and observation != self.focus_observation:
            # A failed preflight disables remote buttons; keep its diagnosis
            # locally too, so the user never needs to bypass the guard to log it.
            self.log(f'target_status: {code} {detail} {context_text(context)}')
        self.focus_observation = observation
        self.focus_status.setText(('操作可能（画面結果は各操作後に確認）' if approved and code is None else '操作不可：' + (ERRORS[code] if code else 'PCの接続承認が必要です。')) + f"\n前面 HWND={context.get('foreground_hwnd')} PID={context.get('foreground_pid')} ／ 一致={context.get('focus_match')} スライドショー一致={context.get('slideshow_match')}")
        if self.transport and approved:
            self.transport.send({'type': 'control_state', 'available': code is None, 'code': code or 'ready', 'locked': snapshot.locked})

    def operation_result(self, seq, profile, action, ok, code, context):
        descriptions = {'com_completed': 'COM操作完了', 'input_dispatched_unverified': '入力送出済み（画面結果未確認）'}
        self.last_result.setText(f'最後の操作：#{seq} {profile}/{action} {descriptions.get(code, ERRORS.get(code, code))} [{code}]')

    async def new_session(self):
        if self.renewing:
            return
        self.renewing = True
        try:
            await self._new_session()
        finally:
            self.renewing = False

    async def _new_session(self):
        if self.transport:
            await self.transport.close('session_replaced')
        self.approval.setEnabled(False)
        self.qr.clear()
        self.session = Session()
        base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
        config_path = base / 'config.json'
        try:
            config = json.loads(config_path.read_text('utf-8')) if config_path.exists() else {}
            self.config = config
            from desktop.transport import Transport
            session = self.session
            def prepare(context):
                snapshot = self.controller.snapshot()
                if snapshot.target:
                    context.update(zip(('target_hwnd', 'target_pid', 'target_exe'), snapshot.target))
                context['locked'] = snapshot.locked
                return lambda profile, action, args: snapshot.execute(profile, action, args, authorize=session.authorize_operation, diagnostics=context)
            self.transport = Transport(session, config, None, self.pending, self.changed, self.log, prepare=prepare, result=self.operation_result)
            self.status.setText('シグナリング接続中…')
            await self.transport.start()
            if self.session.revoked:
                return
            query = {'id': self.session.id, 'token': self.session.token, 'expires': int(self.session.expires), 'host': config.get('host', '0.peerjs.com'), 'port': config.get('port', 443), 'path': config.get('path', '/'), 'key': config.get('key', 'peerjs')}
            url = config.get('web_url', 'https://kkodamalab.github.io/classroom-remote-controller/') + '#' + urlencode(query)
            buffer = io.BytesIO(); qrcode.make(url).save(buffer, format='PNG')
            pixmap = QPixmap(); pixmap.loadFromData(buffer.getvalue()); self.qr.setPixmap(pixmap.scaledToWidth(320))
            self.status.setText('QR待機中（5分以内）・接続後はPC承認が必要')
        except Exception as exc:
            if self.transport:
                await self.transport.close('signaling_failed')
            self.status.setText(f'起動失敗：{type(exc).__name__}。設定とネットワークを確認してください')

    def pending(self, device):
        self.device.setText(f'端末（自己申告）：{device}')
        self.approval.setEnabled(bool(self.session and self.session.device and not self.session.approved and not self.session.revoked))
        self.status.setText('接続承認待ち。手元のスマホであることを確認してください')

    def approve(self):
        if not self.session or self.session.revoked or self.session.approved or not self.session.device:
            return
        if not self.controller.target:
            QMessageBox.information(self, '対象の選択', '先に操作対象ウィンドウを選択してください。'); return
        try:
            self.transport.approve()
            self.approval.setEnabled(False)
            self.qr.clear()
        except Exception:
            self.emergency()

    def changed(self, text):
        self.status.setText(text)
        self.update_focus()
        if self.session and self.session.revoked:
            self.approval.setEnabled(False); self.qr.clear()

    def emergency(self):
        if self.session:
            self.session.revoke()  # synchronous: stop accepting before scheduling network cleanup
        if self.transport:
            asyncio.create_task(self.transport.close('local_stop'))
        self.approval.setEnabled(False); self.qr.clear()
        self.status.setText('セッション破棄済み。再接続には新しいQRが必要です')

    def closeEvent(self, event):
        self.emergency()
        event.accept()
