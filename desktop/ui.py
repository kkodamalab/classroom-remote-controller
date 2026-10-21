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


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Classroom Remote Controller')
        self.resize(580, 820)
        self.transport = None
        self.session = None
        self.setStyleSheet('QWidget {background:#101b29;color:#edf3f5;font-size:14px} QPushButton,QComboBox {padding:12px;background:#23374e;border-radius:6px} QPlainTextEdit {background:#09121d}')
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root)
        self.status = QLabel('セッション準備中'); layout.addWidget(self.status)
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
        from desktop.controls import Controller
        self.controller = Controller()
        self.refresh()
        QTimer.singleShot(0, lambda: asyncio.create_task(self.new_session()))

    def log(self, message):
        self.logs.appendPlainText(message)

    def refresh(self):
        self.targets.clear()
        self.targets.addItem('対象ウィンドウを選択してください', None)
        for hwnd, title, exe, pid in self.controller.windows():
            self.targets.addItem(f'{exe} — {title[:80]}', (hwnd, pid, exe))

    def select_target(self, *_):
        self.controller.target = self.targets.currentData()
        self.controller.locked = self.lock.isChecked()

    async def new_session(self):
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
            self.transport = Transport(self.session, config, self.controller.execute, self.pending, self.changed, self.log)
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
        self.approval.setEnabled(True)
        self.status.setText('接続承認待ち。手元のスマホであることを確認してください')

    def approve(self):
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
