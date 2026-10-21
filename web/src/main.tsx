import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import Peer, {DataConnection} from 'peerjs';
import './style.css';

const pair = new URLSearchParams(location.hash.slice(1));
history.replaceState(null, '', location.pathname);
const mock = new URLSearchParams(location.search).has('demo');
function App() {
  const [status, setStatus] = useState(mock ? 'デモ：PC操作は行いません' : 'QRコードを読み取ってください');
  const [ready, setReady] = useState(false), [tab, setTab] = useState('SLIDE');
  const [slide, setSlide] = useState('powerpoint'), [video, setVideo] = useState('youtube');
  const [result, setResult] = useState('操作結果はここに表示されます');
  const [name, setName] = useState('スマートフォン');
  const conn = useRef<DataConnection | null>(null), peer = useRef<Peer | null>(null);
  const seq = useRef(0), last = useRef(0), pong = useRef(0), approved = useRef(false);
  const pending = useRef(new Map<number, number>());
  const point = useRef<{x:number,y:number}|null>(null);
  function stop(reason:string) { approved.current=false; setReady(false); setStatus(reason); conn.current?.close(); peer.current?.destroy(); pending.current.clear(); }
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
    if(mock){setReady(true);setStatus('デモ接続：実機には送信しません');return;}
    if(!pair.get('id') || !pair.get('token') || Number(pair.get('expires'))*1000<Date.now()){setStatus('QRがないか期限切れです。PCで再発行してください');return;}
    setStatus('シグナリング接続中…');
    const p = new Peer({host:pair.get('host')||'0.peerjs.com',port:Number(pair.get('port')||443),path:pair.get('path')||'/',key:pair.get('key')||'peerjs',secure:true,config:{iceServers:iceServers}});
    peer.current=p;
    const timeout=window.setTimeout(()=>{if(!approved.current)stop('接続または承認がタイムアウトしました。ネットワーク・TURN設定を確認してください');},45000);
    p.on('error', e=>{clearTimeout(timeout);stop(`接続失敗：${e.type}。新しいQRで再接続してください`);});
    p.on('disconnected',()=>stop('シグナリング切断。新しいQRが必要です'));
    p.on('open',()=>{
      const c=p.connect(pair.get('id')!,{serialization:'raw',reliable:true});conn.current=c;
      c.on('open',()=>{pong.current=Date.now();setStatus('PCで接続を承認してください');c.send(JSON.stringify({type:'hello',token:pair.get('token'),device:name.slice(0,60)}));});
      c.on('data', raw=>{
        try { const d=JSON.parse(String(raw));
          if(d.type==='pong')pong.current=Date.now();
          if(d.type==='approved'){approved.current=true;clearTimeout(timeout);setReady(true);setStatus('接続済み・PC承認済み');}
          if(d.type==='result' && pending.current.has(d.seq)){pending.current.delete(d.seq);setResult(`#${d.seq} ${d.ok?(d.code==='input_dispatched_unverified'?'PC入力送出済み（画面結果は未確認）':'PC実行成功'):'PC拒否／失敗'}：${d.code}`);}
          if(d.type==='error')stop(`PCが接続を終了：${d.code}`);
        } catch {stop('不正なPC応答');}
      });
      c.on('close',()=>{clearTimeout(timeout);approved.current=false;setReady(false);setStatus('切断しました。PCでQRを再発行してください');});
      c.on('error',()=>stop('DataChannel接続失敗。TURN・学内ネットワーク制限を確認してください'));
    });
  }
  function send(profile:string,action:string,args:Record<string,number>={}) {
    if(!ready||Date.now()-last.current<80)return; last.current=Date.now();
    if(mock){setResult(`デモ表示：${profile} / ${action}（未実行）`);return;}
    if(!conn.current?.open){stop('未接続');return;}
    const id=++seq.current;
    try{conn.current.send(JSON.stringify({type:'command',seq:id,profile,action,args}));pending.current.set(id,Date.now());setResult(`#${id} 送信済み・PC実行結果待ち`);}catch{stop('送信失敗');}
  }
  const button=(label:string,p:string,a:string,big=false)=><button disabled={!ready} className={big?'large':''} onClick={()=>send(p,a)}>{label}</button>;
  return <main><header><span className="eyebrow">CLASSROOM / REMOTE</span><h1>手のひらから、授業を。</h1><p role="status" className={ready?'online':'status'}>{status}</p></header>
    {!ready&&<section><label>端末名<input maxLength={60} value={name} onChange={e=>setName(e.target.value)}/></label><button className="primary" onClick={connect}>接続を開始</button><p className="hint">PCに表示された端末名を確認して承認してください。</p></section>}
    <nav>{['SLIDE','VIDEO','PC'].map(t=><button key={t} aria-pressed={tab===t} onClick={()=>setTab(t)}>{t}</button>)}</nav>
    <section>
    {tab==='SLIDE'&&<><label>操作プロファイル<select value={slide} onChange={e=>setSlide(e.target.value)}><option value="powerpoint">PowerPoint</option><option value="pdf_edge">PDF / Edge</option><option value="pdf_acrobat">PDF / Acrobat</option><option value="browser">Browser</option></select></label><div className="grid">{button('← 前へ',slide,'previous',true)}{button('次へ →',slide,'next',true)}</div>{slide==='powerpoint'?<div className="grid">{button('開始',slide,'start')}{button('終了',slide,'end')}{button('ブラックアウト',slide,'blackout')}</div>:<div className="grid">{slide.startsWith('pdf')?<>{button('拡大',slide,'zoom_in')}{button('縮小',slide,'zoom_out')}</>:<>{button('戻る',slide,'back')}{button('進む',slide,'forward')}{button('前のタブ',slide,'tab_previous')}{button('次のタブ',slide,'tab_next')}</>}</div>}{slide==='pdf_acrobat'&&<form onSubmit={e=>{e.preventDefault();const el=e.currentTarget.elements.namedItem('page') as HTMLInputElement;send(slide,'page',{page:Number(el.value)});}}><input name="page" aria-label="ページ番号" type="number" min="1" max="9999" defaultValue="1"/><button disabled={!ready}>ページ移動</button></form>}</>}
    {tab==='VIDEO'&&<><label>プレイヤー<select value={video} onChange={e=>setVideo(e.target.value)}><option value="youtube">YouTube（プレイヤーにフォーカス）</option><option value="vlc">VLC（標準ショートカット）</option></select></label>{button('再生 / 一時停止',video,'play_pause',true)}<div className="grid">{button('−10秒',video,'seek_back')}{button('＋10秒',video,'seek_forward')}{button('音量 −',video,'volume_down')}{button('音量 ＋',video,'volume_up')}{button('ミュート',video,'mute')}</div></>}
    {tab==='PC'&&<><div className="pad" aria-label="相対移動タッチパッド" onPointerDown={e=>{if(!ready)return;e.currentTarget.setPointerCapture(e.pointerId);point.current={x:e.clientX,y:e.clientY};}} onPointerMove={e=>{if(!point.current)return;const dx=Math.max(-40,Math.min(40,Math.round(e.clientX-point.current.x))),dy=Math.max(-40,Math.min(40,Math.round(e.clientY-point.current.y)));point.current={x:e.clientX,y:e.clientY};send('mouse','move',{dx,dy});}} onPointerUp={()=>point.current=null} onPointerCancel={()=>point.current=null}>TOUCHPAD<span>指でポインターを移動</span></div><div className="grid">{button('左クリック','mouse','left')}{button('右クリック','mouse','right')}<button disabled={!ready} onClick={()=>send('mouse','scroll',{delta:1})}>スクロール ↑</button><button disabled={!ready} onClick={()=>send('mouse','scroll',{delta:-1})}>スクロール ↓</button>{button('アプリ切替 ※ロック解除時','windows','switch_app')}{button('Esc','windows','escape')}{button('音量 −','windows','volume_down')}{button('音量 ＋','windows','volume_up')}{button('ミュート','windows','mute')}</div></>}
    </section><p aria-live="polite" className="result">{result}</p><footer><button onClick={()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen?.().catch(()=>setResult('このブラウザは全画面に対応していません'))}>全画面</button><button className="danger" onClick={()=>stop('切断しました。新しいQRで再接続してください')}>緊急切断</button></footer><p className="hint">対象ウィンドウの選択・固定はPC側で行います。</p></main>;
}
// TURN credentials must be short-lived. Set VITE_ICE_SERVERS at build time for your deployment.
const iceServers:RTCIceServer[]=JSON.parse((import.meta as unknown as {env:Record<string,string>}).env.VITE_ICE_SERVERS||'[{"urls":"stun:stun.l.google.com:19302"}]');
createRoot(document.getElementById('root')!).render(<App/>);
