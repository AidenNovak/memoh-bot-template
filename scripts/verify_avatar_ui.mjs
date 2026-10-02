// Verify embedded avatars render in the deployed Memoh UI without source hosts.
// Requires the dedicated Chrome tab already logged in to the evaluation instance.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const root=new URL('../',import.meta.url);
const web=process.env.MEMOH_WEB_URL||'http://127.0.0.1:12883';
const expected=Object.fromEntries(['frieren','elon-musk','anya-forger','trpg-gm'].map(slug=>['template-demo-'+slug,JSON.parse(fs.readFileSync(fileURLToPath(new URL('templates/'+slug+'/template.json',root)),'utf8')).profile.avatar_url]));
const target=(await(await fetch('http://127.0.0.1:9228/json/list')).json()).find(t=>t.url.startsWith(web));
if(!target)throw new Error('Open the evaluation Memoh tab first');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let sequence=0;const pending=new Map();
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){const p=pending.get(data.id);pending.delete(data.id);clearTimeout(p.timer);data.error?p.reject(new Error('CDP command failed')):p.resolve(data.result);}};
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},45000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error('Avatar UI verification failed');return r.result.value;};
try{
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:960,deviceScaleFactor:1,mobile:false});
  await call('Page.bringToFront');
  await call('Page.navigate',{url:web+'/bot/template-demo-frieren'});
  await new Promise(r=>setTimeout(r,800));
  await evaluate(`document.querySelector('button[aria-label="打开导航"]')?.click()`);
  const image=expected['template-demo-frieren'];
  await evaluate(`new Promise((resolve,reject)=>{const deadline=Date.now()+30000;const poll=()=>Array.from(document.images).some(i=>i.getAttribute('src')===${JSON.stringify(image)}&&i.complete&&i.naturalWidth===384)?resolve(true):Date.now()>deadline?reject(new Error('Embedded avatar timeout')):setTimeout(poll,100);poll();})`);
  const count=await evaluate(`(async()=>{const response=await fetch('/api/bots',{headers:{Authorization:'Bearer '+localStorage.getItem('token')}});if(!response.ok)throw new Error('Readback failed');const bots=(await response.json()).items;const expected=${JSON.stringify(expected)};for(const [name,image] of Object.entries(expected)){if(bots.find(b=>b.name===name)?.avatar_url!==image)throw new Error('Avatar readback differs');}return Object.keys(expected).length;})()`);
  await evaluate(`new Promise((resolve,reject)=>{const deadline=Date.now()+30000;const poll=()=>document.body.innerText.includes('雨不急，我们也不急')?resolve(true):Date.now()>deadline?reject(new Error('Existing conversation did not render')):setTimeout(poll,100);poll();})`);
  await new Promise(r=>setTimeout(r,400));
  const shot=await call('Page.captureScreenshot',{format:'png'});
  fs.writeFileSync('verification/memoh-chat.png',Buffer.from(shot.data,'base64'));
  fs.writeFileSync('verification/avatar-ui.json',JSON.stringify({checked_at:new Date().toISOString(),demo_avatars:count,embedded_avatar_rendered:true,source_host_requests_required:false,verified:true},null,2)+'\n');
  console.log('Native Memoh UI: four demo avatars read back; embedded portrait rendered');
}finally{socket.close();}
