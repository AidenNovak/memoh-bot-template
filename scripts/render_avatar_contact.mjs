// Create an avatar review sheet using the local gallery and dedicated Chrome.
import fs from 'node:fs';
const catalog=JSON.parse(fs.readFileSync('web/catalog.json','utf8'));
const target=await(await fetch('http://127.0.0.1:9228/json/new?about:blank',{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let sequence=0;const pending=new Map();
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.id){const p=pending.get(data.id);pending.delete(data.id);data.error?p.reject(new Error('CDP command failed')):p.resolve(data.result);}};
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const escape=text=>text.replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
try{
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1540,deviceScaleFactor:1,mobile:false});
  const frameId=(await call('Page.getFrameTree')).frameTree.frame.id;
  const html='<style>body{margin:24px;background:#f6f7f3;font-family:system-ui}main{display:grid;grid-template-columns:repeat(8,1fr);gap:14px}figure{margin:0;text-align:center}img{width:154px;height:154px;object-fit:cover;border-radius:16px}figcaption{font-size:13px;height:39px;margin-top:5px;color:#20372e}small{display:block;font-size:10px;color:#687469}</style><main>'+catalog.map(t=>'<figure><img src="http://127.0.0.1:8765/'+t.avatar.path+'"><figcaption>'+escape(t.name.split(' · ')[0])+'<small>'+t.id+'</small></figcaption></figure>').join('')+'</main>';
  await call('Page.setDocumentContent',{frameId,html});
  const decoded=await call('Runtime.evaluate',{expression:'Promise.all(Array.from(document.images).map(i=>i.decode())).then(()=>document.images.length)',awaitPromise:true,returnByValue:true});
  if(decoded.exceptionDetails||decoded.result.value!==56)throw new Error('Avatar image decode failed');
  const shot=await call('Page.captureScreenshot',{format:'png'});
  fs.writeFileSync('verification/avatars-contact.png',Buffer.from(shot.data,'base64'));
  console.log('All 56 avatar images decoded; contact sheet saved');
}finally{
  socket.close();
  await fetch('http://127.0.0.1:9228/json/close/'+target.id);
}
