import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import Peer, {DataConnection} from 'peerjs';
import './style.css';
import {failure} from './errors';

const pair = new URLSearchParams(location.hash.slice(1));
const mock = new URLSearchParams(location.search).has('demo');
history.replaceState(null, '', location.pathname);
// A newly scanned QR may navigate only the fragment in an already-open tab.
window.addEventListener('hashchange',()=>{if(location.hash)location.reload();});
function App() {
  const [status, setStatus] = useState(mock ? 'デモ：PC操作は行いません' : 'QRコードを読み取ってください');
  const [ready, setReady] = useState(false), [tab, setTab] = useState('SLIDE');
  const [slide, setSlide] = useState('powerpoint'), [video, setVideo] = useState('youtube');
  const [result, setResult] = useState('操作結果はここに表示されます');
  const [name, setName] = useState('スマートフォン');
  const [pcVersion,setPcVersion] = useState('');
  const [gain,setGain] = useState(()=>{try{const value=Number(localStorage.getItem('touchpadGain'));return value>=0.5&&value<=4?value:2;}catch{return 2;}});
  const motion = useRef({dx:0,dy:0});
  const [connecting,setConnecting] = useState(false);
  const [control, setControl] = useState<{available:boolean,code:string,locked:boolean}|null>(null);
  const conn = useRef<DataConnection | null>(null), peer = useRef<Peer | null>(null);
  const seq = useRef(0), last = useRef(0), pong = useRef(0), approved = useRef(false);
  const pending = useRef(new Map<number, number>());
  const connectTimer = useRef<number | undefined>(undefined);
  const point = useRef<{x:number,y:number}|null>(null);
  function stop(reason:string) { clearTimeout(connectTimer.current); approved.current=false; setReady(false); setControl(null); setConnecting(false); conn.current?.close(); peer.current?.destroy(); pending.current.clear(); setStatus(reason); }
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (conn.current?.open) {
        if (Date.now()-pong.current>12000) {stop('応答タイムアウト。PCで新しいQRを発行してください');return;}
        conn.current.send(JSON.stringify({type:'ping'}));
      }
      for (const [id,time] of pending.current) if (Date.now()-time>5000) {pending.current.delete(id);setResult(`#${id} PC実行結果不明（自動再送しません）`);}
    },3000);
    return () => {clearInterval(timer);conn.current?.close();peer.current?.destroy();};
  },[]);
  function connect() {
    if(connecting)return;
    if(mock){setReady(true);setStatus('デモ接続：実機には送信しません');return;}
    const expiry=Number(pair.get('expires'));
    if(!pair.get('id') || !pair.get('token') || !Number.isFinite(expiry) || expiry*1000<Date.now()){setStatus('QRがないか期限切れです。PCで再発行してください');return;}
    setConnecting(true);setStatus('シグナリング接続中…');
    const p = new Peer({host:pair.get('host')||'0.peerjs.com',port:Number(pair.get('port')||443),path:pair.get('path')||'/',key:pair.get('key')||'peerjs',secure:true,config:{iceServers:iceServers}});
    peer.current=p;
    const timeout=window.setTimeout(()=>{if(!approved.current)stop('接続または承認がタイムアウトしました。ネットワーク・TURN設定を確認してください');},45000);
    connectTimer.current=timeout;
    p.on('error', e=>{clearTimeout(timeout);stop(`接続失敗：${e.type}。新しいQRで再接続してください`);});
    p.on('disconnected',()=>stop('シグナリング切断。新しいQRが必要です'));
    p.on('open',()=>{
      const c=p.connect(pair.get('id')!,{serialization:'raw',reliable:true});conn.current=c;
      c.on('open',()=>{pong.current=Date.now();setStatus('PCで接続を承認してください');c.send(JSON.stringify({type:'hello',token:pair.get('token'),device:name.slice(0,60)}));});
      c.on('data', raw=>{
        try { const d=JSON.parse(String(raw));
          if(d.type==='pong')pong.current=Date.now();
          if(d.type==='approved'){setPcVersion(typeof d.version==='string'&&/^\d+\.\d+\.\d+(?:-alpha\.\d+)?$/.test(d.version)?d.version:'');approved.current=true;clearTimeout(timeout);setReady(true);setStatus('接続済み・PC承認済み');}
          if(d.type==='control_state' && typeof d.available==='boolean' && typeof d.code==='string' && typeof d.locked==='boolean')setControl({available:d.available,code:d.code,locked:d.locked});
          if(d.type==='result' && pending.current.has(d.seq)){pending.current.delete(d.seq);setResult(`#${d.seq} ${d.ok?(d.code==='input_dispatched_unverified'?'PC入力送出済み（画面結果は未確認）':'PC実行成功（COM完了）'):'PC拒否／失敗：'+failure(d.code)}`);}
          if(d.type==='error')stop(`PCが接続を終了：${d.code}`);
        } catch {stop('不正なPC応答');}
      });
      c.on('close',()=>{clearTimeout(timeout);approved.current=false;setReady(false);setControl(null);setConnecting(false);pending.current.clear();setStatus('切断しました。PCでQRを再発行してください');});
      c.on('error',()=>stop('DataChannel接続失敗。TURN・学内ネットワーク制限を確認してください'));
    });
  }
  function send(profile:string,action:string,args:Record<string,number>={}):boolean {
    if(!ready||control?.available===false||Date.now()-last.current<80)return false; last.current=Date.now();
    if(mock){setResult(`デモ表示：${profile} / ${action}（未実行）`);return true;}
    if(!conn.current?.open){stop('未接続');return false;}
    const id=++seq.current;
    try{conn.current.send(JSON.stringify({type:'command',seq:id,profile,action,args}));pending.current.set(id,Date.now());setResult(`#${id} 送信済み・PC実行結果待ち`);return true;}catch{stop('送信失敗');return false;}
  }
  const enabled = ready && control?.available!==false;
  useEffect(()=>{try{localStorage.setItem('touchpadGain',String(gain));}catch{/* Storage can be unavailable in private browsing. */}},[gain]);
  useEffect(()=>{
    if(!enabled){motion.current={dx:0,dy:0};point.current=null;return;}
    // Merge pointer events instead of losing every delta during the send throttle.
    const timer=window.setInterval(()=>{
      const dx=Math.max(-40,Math.min(40,Math.trunc(motion.current.dx)));
      const dy=Math.max(-40,Math.min(40,Math.trunc(motion.current.dy)));
      if((dx||dy)&&send('mouse','move',{dx,dy})){motion.current.dx-=dx;motion.current.dy-=dy;}
    },80);
    return ()=>{clearInterval(timer);motion.current={dx:0,dy:0};point.current=null;};
  },[enabled]);
  const button=(label:string,p:string,a:string,big=false)=><button disabled={!enabled} className={big?'large':''} onClick={()=>send(p,a)}>{label}</button>;
  return <main><header><span className="eyebrow">CLASSROOM / REMOTE</span><h1>手のひらから、授業を。</h1><p role="status" className={ready?'online':'status'}>{status}</p>{ready&&!mock&&<p className="hint">{pcVersion?`接続先PC v${pcVersion}`:'PCバージョン不明：旧EXEの可能性があります。版番号付きEXEを確認してください。'}</p>}</header>
    {!ready&&<section><label>端末名<input maxLength={60} value={name} onChange={e=>setName(e.target.value)}/></label><button className="primary" disabled={connecting} onClick={connect}>接続を開始</button><p className="hint">PCに表示された端末名を確認して承認してください。</p></section>}
    <nav>{['SLIDE','VIDEO','PC'].map(t=><button key={t} aria-pressed={tab===t} onClick={()=>setTab(t)}>{t}</button>)}</nav>
    <p aria-live="polite" className="hint">{!ready?'操作不可：接続とPC承認が必要です。':control?.available===false?`接続済み・操作不可：${failure(control.code)}`:mock?'デモ操作可能（実機操作なし）':'接続承認済み・操作要求を送信可能（操作成功は下の結果で確認）'}</p>
    <section>
    {tab==='SLIDE'&&<><label>操作プロファイル<select value={slide} onChange={e=>setSlide(e.target.value)}><option value="powerpoint">PowerPoint</option><option value="pdf_edge">PDF / Edge</option><option value="pdf_acrobat">PDF / Acrobat</option><option value="browser">Browser</option></select></label><div className="grid">{button('← 前へ',slide,'previous',true)}{button('次へ →',slide,'next',true)}</div>{slide==='powerpoint'?<div className="grid">{button('開始',slide,'start')}{button('終了',slide,'end')}{button('ブラックアウト',slide,'blackout')}</div>:<div className="grid">{slide.startsWith('pdf')?<>{button('拡大',slide,'zoom_in')}{button('縮小',slide,'zoom_out')}</>:<>{button('戻る',slide,'back')}{button('進む',slide,'forward')}{button('前のタブ',slide,'tab_previous')}{button('次のタブ',slide,'tab_next')}</>}</div>}{slide==='pdf_acrobat'&&<form onSubmit={e=>{e.preventDefault();const el=e.currentTarget.elements.namedItem('page') as HTMLInputElement;send(slide,'page',{page:Number(el.value)});}}><input name="page" aria-label="ページ番号" type="number" min="1" max="9999" defaultValue="1"/><button disabled={!enabled}>ページ移動</button></form>}</>}
    {tab==='VIDEO'&&<><label>プレイヤー<select value={video} onChange={e=>setVideo(e.target.value)}><option value="youtube">YouTube（プレイヤーにフォーカス）</option><option value="vlc">VLC（標準ショートカット）</option></select></label>{button('再生 / 一時停止',video,'play_pause',true)}<div className="grid">{button('−10秒',video,'seek_back')}{button('＋10秒',video,'seek_forward')}{button('音量 −',video,'volume_down')}{button('音量 ＋',video,'volume_up')}{button('ミュート',video,'mute')}</div></>}
    {tab==='PC'&&<><label>タッチパッド感度：{gain.toFixed(1)}×<input aria-label="タッチパッド感度" type="range" min="0.5" max="4" step="0.5" value={gain} onChange={e=>setGain(Number(e.target.value))}/></label><div className="pad" aria-label="相対移動タッチパッド" onPointerDown={e=>{if(!enabled)return;e.currentTarget.setPointerCapture(e.pointerId);point.current={x:e.clientX,y:e.clientY};}} onPointerMove={e=>{if(!point.current)return;motion.current.dx=Math.max(-120,Math.min(120,motion.current.dx+(e.clientX-point.current.x)*gain));motion.current.dy=Math.max(-120,Math.min(120,motion.current.dy+(e.clientY-point.current.y)*gain));point.current={x:e.clientX,y:e.clientY};}} onPointerUp={()=>point.current=null} onPointerCancel={()=>{point.current=null;motion.current={dx:0,dy:0};}}>TOUCHPAD<span>指でポインターを移動</span></div><div className="grid">{button('左クリック','mouse','left')}{button('右クリック','mouse','right')}<button disabled={!enabled} onClick={()=>send('mouse','scroll',{delta:1})}>スクロール ↑</button><button disabled={!enabled} onClick={()=>send('mouse','scroll',{delta:-1})}>スクロール ↓</button>{button('アプリ切替 ※ロック解除時','windows','switch_app')}{button('Esc','windows','escape')}{button('音量 −','windows','volume_down')}{button('音量 ＋','windows','volume_up')}{button('ミュート','windows','mute')}</div></>}
    </section><p aria-live="polite" className="result">{result}</p><p className="hint">{tab==='SLIDE'?'Browserの「前へ／次へ」はPageUp／PageDownでページ内を移動します。「戻る／進む」は閲覧履歴です。PCで選んだ同じウィンドウを前面にしてください。':tab==='PC'?'スクロールはマウスホイールです。対象固定ON、ポインターが対象内、別ウィンドウの重なりがない状態が必要です。アプリ切替後はPCで対象を選び直してください。':'動画プレイヤーにPCのフォーカスを置いてください。'}</p><footer><button onClick={()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen?.().catch(()=>setResult('このブラウザは全画面に対応していません'))}>全画面</button><button className="danger" onClick={()=>stop('切断しました。新しいQRで再接続してください')}>緊急切断</button></footer><p className="hint">対象ウィンドウの選択・固定はPC側で行います。操作の拒否だけなら再接続は不要です。</p></main>;
}
// TURN credentials must be short-lived. Set VITE_ICE_SERVERS at build time for your deployment.
const iceServers:RTCIceServer[]=JSON.parse((import.meta as unknown as {env:Record<string,string>}).env.VITE_ICE_SERVERS||'[{"urls":"stun:stun.l.google.com:19302"}]');
createRoot(document.getElementById('root')!).render(<App/>);
