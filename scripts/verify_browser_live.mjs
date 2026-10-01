// Run only against a development instance; creates and removes a disposable Bot.
// MEMOH_VERIFY_ENV points to a private env file containing MEMOH_ADMIN_PASSWORD.
// Start the local gallery and a dedicated Chrome with debugging port 9228 first.
import fs from 'node:fs';
const base=process.env.MEMOH_URL||'http://127.0.0.1:18081';
const env=fs.readFileSync(process.env.MEMOH_VERIFY_ENV,'utf8');
const line=env.split('\n').find(s=>s.startsWith('MEMOH_ADMIN_PASSWORD='));
if(!line)throw new Error('Missing development password');
let password=line.slice(line.indexOf('=')+1).trim();
if((password.startsWith('"')&&password.endsWith('"'))||(password.startsWith("'")&&password.endsWith("'")))password=password.slice(1,-1);
let token='';
async function api(method,path,data){const response=await fetch(base+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(180000)});if(!response.ok)throw new Error('Memoh '+method+' '+path.split('?')[0]+' HTTP '+response.status);return response.status===204?{}:response.json();}
token=(await api('POST','/auth/login',{username:'admin',password})).access_token;
const target=(await (await fetch('http://127.0.0.1:9228/json/list')).json()).find(t=>t.url==='http://127.0.0.1:8765/');
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let seq=0;const pending=new Map();socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){const {resolve,reject}=pending.get(data.id);pending.delete(data.id);data.error?reject(new Error(data.error.message)):resolve(data.result);}};
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const evaluate=async(expression)=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error('Browser evaluation failed');return r.result.value;};
const waitFor=expr=>evaluate(`new Promise((resolve,reject)=>{const deadline=Date.now()+150000;const poll=()=>(${expr})?resolve(true):Date.now()>deadline?reject(new Error('UI timeout')):setTimeout(poll,100);poll();})`);
const botsBefore=new Set((await api('GET','/bots')).items.map(b=>b.id));
let bot;
try{
  const models=await api('GET','/models');const model=models.find(m=>m.type==='chat'&&m.enable!==false);if(!model)throw new Error('No chat model');
  bot=await api('POST','/bots',{name:'template-browser-'+Date.now(),display_name:'Temporary template check',wait_for_ready:true});
  await api('PUT','/bots/'+bot.id+'/settings',{chat_model_id:model.id});
  await api('POST','/bots/'+bot.id+'/container/fs/write',{path:'/data/preserve-test.txt',content:'preserve browser sentinel'});
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});await call('Page.reload');
  await waitFor(`document.querySelectorAll('.card').length===56`);
  await evaluate(`document.querySelector('.connection').open=true;document.querySelector('#url').value=${JSON.stringify(base)};document.querySelector('#password').value=${JSON.stringify(password)};document.querySelector('#connect-form').requestSubmit()`);
  await waitFor(`Array.from(document.querySelector('#bot').options).some(o=>o.value===${JSON.stringify(bot.id)})`);
  if(!await evaluate(`document.querySelector('#password').value===''&&document.querySelector('#token').value===''`))throw new Error('Credential inputs were not cleared');
  await evaluate(`document.querySelector('[data-id="frieren"]').click()`);await waitFor(`document.querySelector('#detail').open`);
  await evaluate(`document.querySelector('[data-tab="tune"]').click();document.querySelector('[data-parameter="user_name"]').value='网页测试旅伴';document.querySelector('[data-parameter="journey_pace"]').value='非常慢';document.querySelector('#bot').value=${JSON.stringify(bot.id)};document.querySelector('#bot').dispatchEvent(new Event('change'));document.querySelector('#preview').click()`);
  await waitFor(`document.querySelector('#result').textContent.includes('"dry_run": true')&&!document.querySelector('#apply').disabled`);
  await evaluate(`document.querySelector('#apply').click()`);
  await waitFor(`document.querySelector('#result').textContent.includes('"verified": true')&&!document.querySelector('#apply').disabled`);
  const profile=await api('GET','/bots/'+bot.id),settings=await api('GET','/bots/'+bot.id+'/settings');
  const agents=await api('GET','/bots/'+bot.id+'/container/fs/read?path=%2Fdata%2FAGENTS.md');
  const sentinel=await api('GET','/bots/'+bot.id+'/container/fs/read?path=%2Fdata%2Fpreserve-test.txt');
  if(!profile.display_name.includes('芙莉莲')||settings.chat_model_id!==model.id||!agents.content.includes('网页测试旅伴')||!agents.content.includes('旅行节奏：非常慢')||sentinel.content!=='preserve browser sentinel')throw new Error('Applied state differs from UI choice');
  // The public screenshot omits machine-specific IDs and backup paths.
  await evaluate(`document.querySelector('#result').textContent=${JSON.stringify('应用成功 · 人格与配置已回读验证\n原配置已备份，聊天模型与其他文件保留')};document.querySelector('#bot').selectedOptions[0].textContent='临时验证 Bot'`);
  const screenshot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync('verification/gallery-applied.png',Buffer.from(screenshot.data,'base64'));
  fs.writeFileSync('verification/browser-live.json',JSON.stringify({checked_at:new Date().toISOString(),template:'frieren',checks:['real UI connection','credential inputs cleared','dry-run button','single-click overwrite','custom parameters in AGENTS.md','model binding preserved','other workspace file preserved'],verified:true},null,2)+'\n');
  console.log('Browser live checks passed: one-click overwrite and customized persona');
}finally{
  if(bot)await api('DELETE','/bots/'+bot.id);
  const deadline=Date.now()+30000;let ids;
  do{ids=new Set((await api('GET','/bots')).items.map(b=>b.id));if(ids.size===botsBefore.size&&[...ids].every(id=>botsBefore.has(id)))break;await new Promise(r=>setTimeout(r,500));}while(Date.now()<deadline);
  socket.close();
  if(ids.size!==botsBefore.size||[...ids].some(id=>!botsBefore.has(id)))throw new Error('Disposable browser Bot cleanup incomplete');
}
