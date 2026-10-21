"""Production React UI + real signaling/DataChannel; simulated executor only."""
import asyncio
from pathlib import Path
from urllib.parse import urlencode
from aiohttp import web
from playwright.async_api import async_playwright
from desktop.security import Session
from desktop.transport import Transport


async def main():
    app=web.Application()
    app.router.add_static('/classroom-remote-controller/', Path('web/dist'), show_index=False)
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',18766).start()
    s=Session();waiting=asyncio.Event();calls=[]
    t=Transport(s,{},lambda *args:calls.append(args) or 'input_dispatched_unverified',lambda _:waiting.set(),lambda _:None,lambda _:None)
    try:
        await t.start()
        async with async_playwright() as p:
            browser=await p.chromium.launch(channel='msedge',headless=True)
            page=await browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            base='http://127.0.0.1:18766/classroom-remote-controller/index.html'
            await page.goto(base+'#'+urlencode({'id':s.id,'token':s.token,'expires':int(s.expires)}))
            assert await page.locator('button',has_text='次へ →').is_disabled()
            assert await page.evaluate('location.hash') == ''
            await page.get_by_role('button',name='接続を開始',exact=True).click()
            await asyncio.wait_for(waiting.wait(),45)
            assert await page.locator('button',has_text='次へ →').is_disabled()
            t.approve()
            await page.get_by_text('接続済み・PC承認済み',exact=True).wait_for()
            await page.get_by_role('button',name='次へ →',exact=True).click()
            await page.get_by_text('PC入力送出済み',exact=False).wait_for()
            assert len(calls)==1
            for name in ('VIDEO','PC','SLIDE'):
                await page.get_by_role('button',name=name,exact=True).click()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.set_viewport_size({'width':844,'height':390})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.get_by_role('button',name='緊急切断',exact=True).click()
            assert await page.locator('button',has_text='次へ →').is_disabled()
            for _ in range(30):
                if s.revoked:break
                await asyncio.sleep(.1)
            assert s.revoked
            assert not errors,errors
            await page.goto(base+'#'+urlencode({'id':'expired','token':'expired','expires':1}))
            await page.get_by_role('button',name='接続を開始',exact=True).click()
            await page.get_by_text('QRがないか期限切れです。PCで再発行してください').wait_for()
            await page.goto(base+'?demo=1')
            await page.get_by_role('button',name='接続を開始',exact=True).click()
            await page.get_by_role('button',name='次へ →',exact=True).click()
            await page.get_by_text('デモ表示：powerpoint / next（未実行）',exact=True).wait_for()
            print('PASS: production mobile React UI, approval gating, actual DataChannel, result distinction, tabs, portrait/landscape overflow, emergency disconnect, expired QR; no OS input.')
            await browser.close()
    finally:
        await t.close('test_complete');await runner.cleanup()


if __name__=='__main__':asyncio.run(main())
