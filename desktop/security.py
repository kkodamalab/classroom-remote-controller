"""Transport-independent, fail-closed authorization and command validation."""
import secrets
import time

PROFILES = {
    'powerpoint': {'next', 'previous', 'start', 'end', 'blackout'},
    'pdf_edge': {'next', 'previous', 'zoom_in', 'zoom_out'},
    'pdf_acrobat': {'next', 'previous', 'zoom_in', 'zoom_out', 'page'},
    'browser': {'scroll_up', 'scroll_down', 'back', 'forward', 'tab_next', 'tab_previous', 'next', 'previous'},
    'youtube': {'play_pause', 'seek_forward', 'seek_back', 'volume_up', 'volume_down', 'mute'},
    'vlc': {'play_pause', 'seek_forward', 'seek_back', 'volume_up', 'volume_down', 'mute'},
    'windows': {'switch_app', 'volume_up', 'volume_down', 'mute', 'escape'},
    'mouse': {'move', 'left', 'right', 'scroll'},
}


class Rejected(Exception):
    pass


class Bucket:
    def __init__(self, rate, burst, clock=time.monotonic):
        self.rate, self.burst, self.clock = rate, burst, clock
        self.tokens, self.last = burst, clock()

    def take(self):
        now = self.clock()
        self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1:
            raise Rejected('rate_limit')
        self.tokens -= 1


class Session:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.id, self.token = secrets.token_hex(24), secrets.token_urlsafe(32)
        self.expires = clock() + 300
        self.approved = False
        self.revoked = False
        self.device = None
        self.seq = 0
        self.commands = Bucket(20, 25)

    def valid(self):
        if self.revoked or self.clock() >= self.expires:
            raise Rejected('session_expired')

    def authorize_operation(self):
        """Recheck approval on the executor thread immediately before OS/COM use."""
        self.valid()
        if not self.approved:
            raise Rejected('not_approved')

    def hello(self, data):
        self.valid()
        if set(data) != {'type', 'token', 'device'} or data['type'] != 'hello':
            raise Rejected('bad_hello')
        if not isinstance(data['token'], str) or not secrets.compare_digest(data['token'], self.token):
            raise Rejected('bad_token')
        if self.device is not None:
            raise Rejected('occupied')
        name = data['device']
        if not isinstance(name, str) or not 1 <= len(name) <= 60 or not name.isprintable():
            raise Rejected('bad_device')
        self.device = name

    def approve(self):
        self.valid()
        if self.device is None:
            raise Rejected('no_candidate')
        self.approved = True
        self.expires = self.clock() + 7200

    def revoke(self):
        self.revoked, self.approved, self.token = True, False, ''

    def command(self, data):
        self.authorize_operation()
        if set(data) != {'type', 'seq', 'profile', 'action', 'args'} or data['type'] != 'command':
            raise Rejected('schema')
        seq = data['seq']
        if type(seq) is not int or not 1 <= seq <= 9007199254740991:
            raise Rejected('sequence')
        if seq <= self.seq:
            raise Rejected('duplicate')
        self.seq = seq
        self.commands.take()
        profile, action, args = data['profile'], data['action'], data['args']
        if not isinstance(profile, str) or not isinstance(action, str) or action not in PROFILES.get(profile, set()):
            raise Rejected('not_allowed')
        expected = {'dx': (-40, 40), 'dy': (-40, 40)} if (profile, action) == ('mouse', 'move') else {'delta': (-3, 3)} if (profile, action) == ('mouse', 'scroll') else {'page': (1, 9999)} if action == 'page' else {}
        if not isinstance(args, dict) or set(args) != set(expected):
            raise Rejected('arguments')
        for key, (low, high) in expected.items():
            if type(args[key]) is not int or not low <= args[key] <= high:
                raise Rejected('arguments')
        return profile, action, args
