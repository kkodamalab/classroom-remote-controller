/* Local UI contract test. PeerJS is explicitly mocked; no WebRTC/OS-input claim.
 * Start Vite on 127.0.0.1:5173, then node tests/browser_diagnostics.cjs.
 * Requires Playwright; CHROMIUM_PATH optionally selects an installed browser.
 */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const fakePeer = `
class Events {
  handlers = {};
  on(name, cb) { this.handlers[name] = cb; }
  emit(name, value) { this.handlers[name]?.(value); }
}
export default class Peer extends Events {
  constructor() { super(); window.__peer = this; setTimeout(()=>this.emit('open'), 0); }
  connect() {
    const c = new Events(); c.open = true; window.__channel = c; window.__sent = [];
    c.send = raw => { const d=JSON.parse(raw); window.__sent.push(d);
      if(d.type==='ping')c.emit('data',JSON.stringify({type:'pong'}));
      if(d.type==='command')setTimeout(()=>c.emit('data',JSON.stringify({type:'result',seq:d.seq,ok:false,code:window.__code||'focus_changed',message:'C:/secret/token/SDP'})),0);
    };
    c.close = () => { c.open=false; c.emit('close'); };
    setTimeout(()=>c.emit('open'), 0); return c;
  }
  destroy() {}
}`;

(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {}),
    args:['--no-sandbox','--disable-dev-shm-usage']});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    const errors = []; page.on('pageerror', error=>errors.push(String(error)));
    await page.route('**/node_modules/.vite/deps/peerjs.js*', route=>route.fulfill({contentType:'application/javascript',body:fakePeer}));
    const base = 'http://127.0.0.1:5173/classroom-remote-controller/';
    await page.goto(base+'#id=test&token=not-a-secret&expires='+Math.floor(Date.now()/1000+300));
    assert.equal(await page.evaluate(()=>location.hash), '');
    const next = page.getByRole('button',{name:'次へ →',exact:true});
    assert(await next.isDisabled());
    await page.getByRole('button',{name:'接続を開始',exact:true}).click();
    await page.getByText('PCで接続を承認してください',{exact:true}).waitFor();
    assert(await next.isDisabled());
    await page.evaluate(()=>window.__channel.emit('data',JSON.stringify({type:'approved'})));
    for(const code of ['focus_changed','target_changed','profile_mismatch','com_error','win32_error','unexpected_error']) {
      await page.waitForTimeout(100); // stay outside the UI's 80ms command throttle
      await page.evaluate(value=>window.__code=value,code);
      await next.click();
      await page.locator('.result').filter({hasText:'['+code+']'}).waitFor();
      assert(!await page.locator('.result').innerText().then(text=>text.includes('C:/secret')));
      assert(await next.isEnabled()); // execution failure never forces reconnection
    }
    await page.evaluate(()=>window.__channel.emit('data',JSON.stringify({type:'control_state',available:false,code:'focus_changed',locked:true})));
    await page.getByText('接続済み・操作不可：',{exact:false}).waitFor();
    assert(await next.isDisabled());
    await page.evaluate(()=>window.__channel.emit('data',JSON.stringify({type:'control_state',available:true,code:'ready',locked:true})));
    await page.getByRole('combobox').selectOption('browser');
    await page.getByText('Browserの「前へ／次へ」はPageUp／PageDown',{exact:false}).waitFor();
    for (const tab of ['PC','VIDEO','SLIDE']) {
      await page.getByRole('button',{name:tab,exact:true}).click();
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    await page.getByRole('button',{name:'PC',exact:true}).click();
    await page.getByText('スクロールはマウスホイールです。',{exact:false}).waitFor();
    await page.getByRole('button',{name:'緊急切断',exact:true}).click();
    assert(await page.getByRole('button',{name:'左クリック',exact:true}).isDisabled());
    await page.goto(base+'?demo=1');
    await page.getByRole('button',{name:'接続を開始',exact:true}).click();
    await page.getByRole('button',{name:'次へ →',exact:true}).click();
    await page.getByText('デモ表示：powerpoint / next（未実行）',{exact:true}).waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS: mocked PeerJS UI: QR clearing, approval gating, six Japanese error codes, no private response text, no reconnect on execution failure, focus gating/recovery, instructions, tabs/mobile width, emergency disconnect, demo');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
