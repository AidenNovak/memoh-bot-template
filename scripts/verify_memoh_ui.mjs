// Verify a real reply through the deployed upstream Web UI and retain a screenshot.
// Requires a logged-in dedicated Chrome tab on MEMOH_WEB_URL and demo bots seeded.
import fs from 'node:fs';
const web=process.env.MEMOH_WEB_URL||'http://127.0.0.1:12883';
const target=(await(await fetch('http://127.0.0.1:9228/json/list')).json()).find(t=>t.url.startsWith(web));
if(!target)throw new Error('Open the dedicated Memoh evaluation tab first');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let sequence=0;const pending=new Map();
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.id){const entry=pending.get(data.id);pending.delete(data.id);if(entry)data.error?entry.reject(new Error('CDP command failed')):entry.resolve(data.result);}};
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async(expression)=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error('Browser evaluation failed');return r.result.value;};
const waitFor=expr=>evaluate(`new Promise((resolve,reject)=>{const deadline=Date.now()+120000;const poll=()=>(${expr})?resolve(true):Date.now()>deadline?reject(new Error('UI timeout')):setTimeout(poll,150);poll();})`);
try{
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:960,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:web+'/bot/template-demo-frieren'});
  await waitFor(`document.querySelector('textarea')&&document.querySelector('button[aria-label="Send message"]')&&document.body.innerText.includes('DeepSeek V4 Flash')`);
  await evaluate(`(async()=>{
    const headers={Authorization:'Bearer '+localStorage.getItem('token')};
    const api=async p=>{const r=await fetch('/api'+p,{headers});if(!r.ok)throw new Error('API readback failed');return r.json();};
    const bot=(await api('/bots')).items.find(b=>b.name==='template-demo-frieren');
    const sessions=(await api('/bots/'+bot.id+'/sessions')).items;
    window.memohVerificationSeen=new Set();
    for(const session of sessions){
      const turns=(await api('/bots/'+bot.id+'/messages?session_id='+session.id+'&limit=100')).items;
      turns.forEach(t=>window.memohVerificationSeen.add(t.id));
    }
  })()`);
  const text='窗边那只杯子已经凉了。今天不想做任务，就陪我看一会儿雨吧。';
  await evaluate(`document.querySelector('textarea').value=${JSON.stringify(text)};document.querySelector('textarea').dispatchEvent(new Event('input',{bubbles:true}));`);
  await evaluate(`new Promise(r=>setTimeout(r,50))`);
  const rect=await evaluate(`document.querySelector('button[aria-label="Send message"]').getBoundingClientRect().toJSON()`);
  // A real pointer activates the dock pane before its send handler runs.
  await call('Input.dispatchMouseEvent',{type:'mousePressed',x:rect.x+rect.width/2,y:rect.y+rect.height/2,button:'left',clickCount:1});
  await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:rect.x+rect.width/2,y:rect.y+rect.height/2,button:'left',clickCount:1});
  await waitFor(`document.body.innerText.includes(${JSON.stringify(text)})&&document.querySelector('textarea').value===''`);
  // Fetch through the actual page's authenticated API; token stays inside Chrome.
  const reply=await evaluate(`(async()=>{
    const headers={Authorization:'Bearer '+localStorage.getItem('token')};
    const api=async p=>{const r=await fetch('/api'+p,{headers});if(!r.ok)throw new Error('API readback failed');return r.json();};
    const bot=(await api('/bots')).items.find(b=>b.name==='template-demo-frieren');
    const deadline=Date.now()+120000;
    while(Date.now()<deadline){
      const sessions=(await api('/bots/'+bot.id+'/sessions')).items;
      for(const session of sessions){
        const turns=(await api('/bots/'+bot.id+'/messages?session_id='+session.id+'&limit=100')).items;
        const user=turns.filter(t=>t.role==='user'&&t.text===${JSON.stringify(text)}&&!window.memohVerificationSeen.has(t.id)).sort((a,b)=>(b.turn_position||0)-(a.turn_position||0))[0];
        const assistant=turns.filter(t=>t.role==='assistant'&&!window.memohVerificationSeen.has(t.id)).sort((a,b)=>(b.turn_position||0)-(a.turn_position||0))[0];
        const content=assistant&&(assistant.text||assistant.messages?.filter(m=>m.type==='text').map(m=>m.content).join('\\n'));
        if(user&&assistant&&assistant.turn_position>=user.turn_position&&content&&document.body.innerText.includes(content.split('\\n').filter(Boolean)[0]))return content;
      }
      await new Promise(r=>setTimeout(r,300));
    }
    throw new Error('No rendered persisted assistant reply');
  })()`);
  await evaluate(`document.querySelector('button[aria-label="打开导航"]')?.click()`);
  await evaluate(`new Promise(r=>setTimeout(r,350))`);
  const screenshot=await call('Page.captureScreenshot',{format:'png'});
  fs.writeFileSync('verification/memoh-chat.png',Buffer.from(screenshot.data,'base64'));
  fs.writeFileSync('verification/memoh-ui.json',JSON.stringify({checked_at:new Date().toISOString(),upstream_commit:'1bfb42154e09efacd34f68898ceaab78c10c85f3',template:'frieren',transport:'native upstream web composer',user:text,assistant:reply,verified:true},null,2)+'\n');
  console.log('Native Memoh Web UI verified: composer, real reply, rendered persisted text');
}finally{socket.close();}
