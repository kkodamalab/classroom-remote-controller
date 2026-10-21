import asyncio
import json
from desktop.security import Session
from desktop.transport import Transport


class Channel:
    readyState = 'open'
    def __init__(self): self.messages=[]
    def send(self, raw): self.messages.append(json.loads(raw))


def make():
    calls=[]
    s=Session()
    t=Transport(s,{},lambda *args:calls.append(args) or 'test',lambda _:None,lambda _:None,lambda _:None)
    t.channel=Channel()
    return s,t,calls


def test_unauthorized_wire_command_revokes():
    async def run():
        s,t,calls=make()
        t.receive(json.dumps({'type':'command','seq':1,'profile':'windows','action':'escape','args':{}}))
        await asyncio.sleep(0)
        assert s.revoked and not calls
        assert t.channel.messages[-1]['code']=='not_approved'
    asyncio.run(run())


def test_bad_json_and_binary_revoked():
    async def run():
        for message in ('{', '[]', 'x'*2049, b'not text'):
            s,t,calls=make();t.receive(message);await asyncio.sleep(0)
            assert s.revoked and not calls
    asyncio.run(run())


def test_approved_execution_and_failure_are_acknowledged():
    async def run():
        s,t,calls=make();t.receive(json.dumps({'type':'hello','token':s.token,'device':'phone'}));t.approve()
        t.receive(json.dumps({'type':'command','seq':1,'profile':'windows','action':'escape','args':{}}))
        await asyncio.gather(*list(t.tasks))
        assert len(calls)==1 and t.channel.messages[-1]['ok']
        t.receive(json.dumps({'type':'command','seq':1,'profile':'windows','action':'escape','args':{}}))
        assert len(calls)==1 and t.channel.messages[-1]['code']=='duplicate'
        def fail(*_):raise RuntimeError('private details must not leak')
        t.execute=fail
        t.receive(json.dumps({'type':'command','seq':2,'profile':'windows','action':'escape','args':{}}))
        await asyncio.gather(*list(t.tasks))
        assert not t.channel.messages[-1]['ok']
        assert 'private' not in json.dumps(t.channel.messages)
        await t.close('test')
    asyncio.run(run())
