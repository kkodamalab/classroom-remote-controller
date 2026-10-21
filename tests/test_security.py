import pytest
from desktop.security import Session, Rejected, Bucket, PROFILES


def authorized():
    s = Session()
    s.hello({'type': 'hello', 'token': s.token, 'device': 'test phone'})
    s.approve()
    return s


def command(**changes):
    return {'type': 'command', 'seq': 1, 'profile': 'powerpoint', 'action': 'next', 'args': {}, **changes}


def test_requires_approval():
    with pytest.raises(Rejected, match='not_approved'): Session().command(command())


def test_token_and_single_phone():
    s = Session()
    with pytest.raises(Rejected, match='bad_token'): s.hello({'type':'hello','token':'wrong','device':'x'})
    s.hello({'type':'hello','token':s.token,'device':'x'})
    with pytest.raises(Rejected, match='occupied'): s.hello({'type':'hello','token':s.token,'device':'y'})


def test_expiry_and_revoke():
    now = [0]
    s = Session(lambda: now[0]); now[0] = 300
    with pytest.raises(Rejected, match='expired'): s.valid()
    s = authorized(); s.revoke()
    assert s.token == ''
    with pytest.raises(Rejected): s.command(command())


def test_replay_rejected_and_failed_sequence_consumed():
    s = authorized(); s.command(command())
    with pytest.raises(Rejected, match='duplicate'): s.command(command())
    with pytest.raises(Rejected): s.command(command(seq=2, action='shell'))
    with pytest.raises(Rejected, match='duplicate'): s.command(command(seq=2))


@pytest.mark.parametrize('change', [{'seq':True},{'seq':0},{'seq':1.1},{'action':'capture'},{'profile':[]},{'args':{'text':'abc'}},{'args':[]},{'extra':1}])
def test_schema(change):
    with pytest.raises(Rejected): authorized().command(command(**change))


@pytest.mark.parametrize('args', [{'dx':41,'dy':0},{'dx':True,'dy':0},{'dx':0,'dy':0,'text':'bad'}])
def test_mouse_bounds(args):
    with pytest.raises(Rejected): authorized().command(command(profile='mouse',action='move',args=args))


def test_all_allowed_commands():
    for p, actions in PROFILES.items():
        for a in actions:
            args = {'dx':1,'dy':-1} if a=='move' else {'delta':1} if a=='scroll' else {'page':10} if a=='page' else {}
            assert authorized().command(command(profile=p,action=a,args=args)) == (p,a,args)


def test_rate_bucket():
    now=[0]; b=Bucket(2,2,lambda:now[0]); b.take();b.take()
    with pytest.raises(Rejected, match='rate_limit'): b.take()
    now[0]=.5;b.take()


def test_new_session_cannot_reuse_token():
    old=authorized();token=old.token;old.revoke();new=Session()
    with pytest.raises(Rejected, match='bad_token'):new.hello({'type':'hello','token':token,'device':'x'})
