import asyncio
import json
import secrets
import time
from urllib.parse import urlencode
import aiohttp
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from desktop.security import Bucket, Rejected


class Transport:
    def __init__(self, session, config, execute, pending, changed, log):
        self.session, self.config, self.execute = session, config, execute
        self.pending, self.changed, self.log = pending, changed, log
        self.http = self.ws = self.pc = self.channel = None
        self.source = self.connection_id = None
        self.last_seen = time.monotonic()
        self.messages = Bucket(30, 40)
        self.tasks = []
        self.closing = False
        self.opened = asyncio.Event()
        self.candidates = []
        self.executing = False

    async def start(self):
        host = self.config.get('host', '0.peerjs.com')
        port = int(self.config.get('port', 443))
        path = self.config.get('path', '/').rstrip('/')
        query = urlencode({'key': self.config.get('key', 'peerjs'), 'id': self.session.id, 'token': secrets.token_urlsafe(24)})
        self.http = aiohttp.ClientSession()
        self.ws = await self.http.ws_connect(f'wss://{host}:{port}{path}/peerjs?{query}', max_msg_size=65536, timeout=15)
        self.tasks = [asyncio.create_task(self.listen()), asyncio.create_task(self.watch())]
        await asyncio.wait_for(self.opened.wait(), timeout=15)

    async def signal(self, kind, payload):
        await self.ws.send_json({'type': kind, 'dst': self.source, 'payload': payload})

    async def listen(self):
        try:
            async for msg in self.ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                data = json.loads(msg.data)
                kind = data.get('type')
                if kind == 'OPEN':
                    self.opened.set()
                elif kind == 'OFFER':
                    if self.pc is not None:
                        continue
                    self.session.valid()
                    payload = data['payload']
                    if payload.get('type') != 'data' or payload.get('serialization') != 'raw':
                        raise Rejected('unsupported_channel')
                    self.source, self.connection_id = data['src'], payload['connectionId']
                    self.last_seen = time.monotonic()
                    ice = self.config.get('iceServers', [{'urls': 'stun:stun.l.google.com:19302'}])
                    self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[RTCIceServer(**server) for server in ice]))
                    self.pc.on('datachannel', self.on_channel)
                    @self.pc.on('connectionstatechange')
                    async def state():
                        if self.pc.connectionState in ('failed', 'closed'):
                            await self.close('webrtc_' + self.pc.connectionState)
                    await self.pc.setRemoteDescription(RTCSessionDescription(**payload['sdp']))
                    answer = await self.pc.createAnswer()
                    await self.pc.setLocalDescription(answer)
                    await self.signal('ANSWER', {'type': 'data', 'connectionId': self.connection_id, 'sdp': {'type': self.pc.localDescription.type, 'sdp': self.pc.localDescription.sdp}})
                elif kind == 'CANDIDATE' and self.pc and data.get('src') == self.source:
                    payload = data['payload']
                    if payload.get('connectionId') != self.connection_id:
                        continue
                    c = payload.get('candidate')
                    if c and c.get('candidate'):
                        candidate = candidate_from_sdp(c['candidate'].removeprefix('candidate:'))
                        candidate.sdpMid, candidate.sdpMLineIndex = c.get('sdpMid'), c.get('sdpMLineIndex')
                        await self.pc.addIceCandidate(candidate)
                elif kind in ('ERROR', 'ID-TAKEN', 'INVALID-KEY', 'EXPIRE') or (kind == 'LEAVE' and data.get('src') == self.source):
                    raise Rejected('signaling_' + kind.lower())
        except asyncio.CancelledError:
            return
        except Exception:
            await self.close('signaling_error')
        finally:
            if not self.closing:
                await self.close('signaling_closed')

    def on_channel(self, channel):
        if self.channel is not None:
            channel.close(); return
        self.channel = channel
        self.last_seen = time.monotonic()
        channel.on('message', self.receive)
        channel.on('close', lambda: asyncio.create_task(self.close('channel_closed')))

    def send(self, data):
        if self.channel and self.channel.readyState == 'open':
            self.channel.send(json.dumps(data, separators=(',', ':')))

    def receive(self, raw):
        seq = None
        try:
            self.messages.take()
            self.session.valid()
            if not isinstance(raw, str) or len(raw) > 2048:
                raise Rejected('envelope_size')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise Rejected('schema')
            kind = data.get('type')
            if kind == 'hello':
                self.session.hello(data)
                self.pending(self.session.device)
            elif kind == 'ping' and set(data) == {'type'}:
                if self.session.device is None:
                    raise Rejected('not_authenticated')
                self.last_seen = time.monotonic(); self.send({'type': 'pong'})
            elif kind == 'command':
                seq = data.get('seq')
                if type(seq) is not int:
                    seq = None
                profile, action, args = self.session.command(data)
                if self.executing:
                    raise Rejected('executor_busy')
                self.executing = True
                self.tasks.append(asyncio.create_task(self.run_command(seq, profile, action, args)))
            else:
                raise Rejected('schema')
        except Rejected as exc:
            code = str(exc)
            if seq is not None and self.session.approved:
                self.send({'type': 'result', 'seq': seq, 'ok': False, 'code': code})
            else:
                self.session.revoke()
                asyncio.create_task(self.close(code))
        except Exception:
            self.session.revoke()
            asyncio.create_task(self.close('invalid_message'))

    async def run_command(self, seq, profile, action, args):
        def work():
            import sys
            if sys.platform == 'win32':
                import pythoncom
                pythoncom.CoInitialize()
            try:
                self.session.valid()
                return self.execute(profile, action, args)
            finally:
                if sys.platform == 'win32':
                    pythoncom.CoUninitialize()
        try:
            code = await asyncio.to_thread(work)
            if not self.session.revoked:
                self.send({'type': 'result', 'seq': seq, 'ok': True, 'code': code})
                self.log(f'#{seq} {profile}/{action}: {code}')
        except asyncio.CancelledError:
            pass
        except Exception:
            self.send({'type': 'result', 'seq': seq, 'ok': False, 'code': 'target_focus_or_execution_failed'})
            self.log(f'#{seq}: execution rejected/failed')
        finally:
            self.executing = False
            current = asyncio.current_task()
            if current in self.tasks:
                self.tasks.remove(current)

    def approve(self):
        if not self.channel or self.channel.readyState != 'open':
            raise Rejected('channel_closed')
        self.session.approve()
        self.send({'type': 'approved'})
        self.changed('接続済み・承認済み（対象アプリを前面にしてください）')

    async def watch(self):
        try:
            while not self.closing:
                await asyncio.sleep(3)
                self.session.valid()
                await self.ws.send_json({'type': 'HEARTBEAT'})
                if self.pc and time.monotonic() - self.last_seen > (12 if self.channel else 45):
                    await self.close('heartbeat_or_ice_timeout')
        except asyncio.CancelledError:
            pass
        except Exception:
            await self.close('session_expired_or_network_lost')

    async def close(self, reason):
        if self.closing:
            return
        self.closing = True
        self.session.revoke()
        self.send({'type': 'error', 'code': reason})
        self.changed(f'切断：{reason}。新しいQRを発行してください')
        for task in self.tasks:
            if task is not asyncio.current_task():
                task.cancel()
        if self.pc:
            await self.pc.close()
        if self.ws:
            await self.ws.close()
        if self.http:
            await self.http.close()
