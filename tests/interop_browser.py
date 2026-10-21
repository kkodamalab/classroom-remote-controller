"""Opt-in real PeerJS Cloud / Chromium -> aiortc smoke test. No OS input.
Run: python -m tests.interop_browser (requires npm ci, Playwright and Edge).
"""
import asyncio
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright
from desktop.security import Session
from desktop.transport import Transport


async def main():
    session = Session()
    executions = []
    pending = asyncio.Event()
    transport = Transport(session, {}, lambda *args: executions.append(args) or 'test_executor_only', lambda _: pending.set(), print, print)
    async def index(_):
        return web.Response(text='<script src="/peer.js"></script>', content_type='text/html')
    async def script(_):
        return web.FileResponse(Path('web/node_modules/peerjs/dist/peerjs.min.js'))
    app = web.Application(); app.router.add_get('/', index); app.router.add_get('/peer.js', script)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 18765); await site.start()
    try:
        await transport.start()
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='msedge', headless=True)
            page = await browser.new_page()
            await page.goto('http://127.0.0.1:18765')
            await page.evaluate('''({id,token}) => {
              window.messages=[]; window.errors=[];
              window.peer=new Peer({host:'0.peerjs.com',port:443,secure:true});
              peer.on('error', e=>errors.push(e.type));
              peer.on('open',()=>{
                window.c=peer.connect(id,{serialization:'raw',reliable:true});
                c.on('open',()=>{c.send(JSON.stringify({type:'hello',token,device:'automated Edge test'})); window.hb=setInterval(()=>c.open&&c.send(JSON.stringify({type:'ping'})),3000);});
                c.on('data',d=>messages.push(JSON.parse(d)));
              });
            }''', {'id': session.id, 'token': session.token})
            await asyncio.wait_for(pending.wait(), 45)
            assert not session.approved
            transport.approve()
            await page.wait_for_function("messages.some(m=>m.type==='approved')")
            command = {'type':'command','seq':1,'profile':'powerpoint','action':'next','args':{}}
            await page.evaluate('(d)=>c.send(JSON.stringify(d))', command)
            await page.wait_for_function("messages.some(m=>m.type==='result'&&m.ok)")
            await page.evaluate('(d)=>c.send(JSON.stringify(d))', command)
            await page.wait_for_function("messages.some(m=>m.code==='duplicate')")
            assert len(executions) == 1
            await page.evaluate('c.close()')
            for _ in range(30):
                if session.revoked: break
                await asyncio.sleep(.1)
            assert session.revoked
            print('PASS: Edge -> PeerJS Cloud -> aiortc; approval, result, duplicate suppression, disconnect revocation. No OS input executed.')
            await browser.close()
    finally:
        await transport.close('test_complete')
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
