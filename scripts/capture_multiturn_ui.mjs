// Read back complete evaluation sessions, then capture their actual native UI.
// Dedicated, already authenticated Chrome on port 9228; no messages are sent.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const source=process.env.MEMOH_MULTITURN_REPORT||path.join(root,'verification/model-replies/multiturn-followup.json');
const report=JSON.parse(fs.readFileSync(source,'utf8'));
const selected=['frieren--deepseek-v4-flash','elon-musk--deepseek-v4-flash','anya-forger--k3','trpg-gm--deepseek-v4-flash'];
const web=process.env.MEMOH_WEB_URL||'http://127.0.0.1:12883';
const target=(await(await fetch('http://127.0.0.1:9228/json/list')).json()).find(t=>t.url.startsWith(web));
if(!target)throw new Error('Open the authenticated evaluation Memoh tab first');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let sequence=0;const pending=new Map();
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){const p=pending.get(data.id);pending.delete(data.id);clearTimeout(p.timer);data.error?p.reject(new Error('CDP command failed')):p.resolve(data.result);}};
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},45000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error('Native conversation verification failed');return r.result.value;};
const receipts=[];const directory=path.join(root,'verification/multiturn-ui');fs.mkdirSync(directory,{recursive:true});
try{
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
  await call('Page.bringToFront');
  for(const id of selected){
    const test=report.cases.find(c=>c.id===id);
    if(!test||!test.session_verified||test.turns.length!==8)throw new Error('Incomplete source conversation: '+id);
    const verified=await evaluate(`(async()=>{
      const request=async url=>{const r=await fetch('/api'+url,{headers:{Authorization:'Bearer '+localStorage.getItem('token')}});if(!r.ok)throw new Error('API readback failed');return r.json();};
      const test=${JSON.stringify(test)};
      const bot=(await request('/bots')).items.find(b=>b.name===test.bot_name);
      if(!bot)throw new Error('Disposable source Bot no longer exists');
      const sessions=(await request('/bots/'+bot.id+'/sessions')).items;
      if(sessions.length!==1)throw new Error('Expected one unchanged session');
      const hash=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),b=>b.toString(16).padStart(2,'0')).join('');
      const session=sessions[0].id;
      if(await hash(session)!==test.turns[0].session_sha256)throw new Error('Session differs from recorded source');
      const messages=(await request('/bots/'+bot.id+'/messages?session_id='+encodeURIComponent(session)+'&limit=100')).items;
      const text=t=>t.text||t.messages.filter(m=>m.type==='text').map(m=>m.content).join('\\n');
      const ordered=role=>messages.filter(t=>t.role===role).sort((a,b)=>a.turn_position-b.turn_position);
      const users=ordered('user'),assistants=ordered('assistant');
      if(users.length!==8||assistants.length!==8)throw new Error('Native source is not eight complete pairs');
      for(let i=0;i<8;i++)if(text(users[i])!==test.turns[i].user||text(assistants[i])!==test.turns[i].assistant||users[i].turn_id!==assistants[i].turn_id)throw new Error('Persisted native text differs from published source');
      return {session_sha256:await hash(session),pairs:8};
    })()`);
    await call('Page.navigate',{url:web+'/bot/'+encodeURIComponent(test.bot_name)});
    await new Promise(r=>setTimeout(r,700));
    // A new browser tab/layout opens a draft. Select the persisted session via
    // the same native workspace action used by the sidebar, without sending.
    await evaluate(`(async()=>{
      const get=async url=>(await fetch('/api'+url,{headers:{Authorization:'Bearer '+localStorage.getItem('token')}})).json();
      const bot=(await get('/bots')).items.find(b=>b.name===${JSON.stringify(test.bot_name)});
      const session=(await get('/bots/'+bot.id+'/sessions')).items[0];
      const stores=document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s;
      await stores.get('workspace-tabs').openSessionChat({sessionId:session.id,title:session.title,explicitSelection:true});
      return true;
    })()`);
    const normalized=test.turns[7].assistant.replaceAll('**','').replaceAll('\n',' ').trim();
    const fragment=normalized.slice(0,24);
    await evaluate(`new Promise((resolve,reject)=>{const end=Date.now()+30000;const poll=()=>document.body.innerText.replaceAll('\\n',' ').includes(${JSON.stringify(fragment)})&&document.body.innerText.includes(${JSON.stringify(test.turns[7].user)})?resolve(true):Date.now()>end?reject(new Error('Last complete pair did not render')):setTimeout(poll,150);poll();})`);
    await evaluate(`document.querySelector('button[aria-label="打开导航"]')?.click()`);
    await new Promise(r=>setTimeout(r,400));
    const shot=await call('Page.captureScreenshot',{format:'png'});
    const bytes=Buffer.from(shot.data,'base64');fs.writeFileSync(path.join(directory,id+'.png'),bytes);
    receipts.push({case_id:id,...verified,rendered:true,screenshot:'verification/multiturn-ui/'+id+'.png',screenshot_sha256:crypto.createHash('sha256').update(bytes).digest('hex')});
    console.log('Verified and captured eight actual pairs: '+id);
  }
  fs.writeFileSync(path.join(root,'verification/multiturn-ui.json'),JSON.stringify({checked_at:new Date().toISOString(),source:'verification/model-replies/multiturn-followup.json',messages_sent:0,cases:receipts,verified:true},null,2)+'\n');
}finally{socket.close();}
