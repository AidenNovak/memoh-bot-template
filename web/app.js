const $ = (selector) => document.querySelector(selector);
const categories = {all:'全部', 'public-figures':'国际名人','chinese-celebrities':'华语艺人','historical':'历史人物','anime':'动漫角色','games':'游戏角色','original':'原创玩法'};
let catalog = [], selected = null, category = 'all', bots = [], busy = false;
function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').className = error ? 'error' : ''; $('#notice').hidden = false; clearTimeout(notice.timer); notice.timer = setTimeout(() => $('#notice').hidden = true, 6500); }
async function api(path, data) { const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); const result = await response.json(); if (!response.ok) throw new Error(result.error || '请求未完成'); return result; }
function draw() {
  const query = $('#search').value.trim().toLowerCase();
  const items = catalog.filter(t => (category === 'all' || t.category === category) && `${t.id} ${t.name} ${t.description}`.toLowerCase().includes(query));
  $('#cards').replaceChildren(); $('#count').textContent = `${items.length} 个角色 / 选择一个，看看怎么玩`; $('#empty').hidden = items.length !== 0;
  for (const item of items) {
    const card = el('button', undefined, 'card'); card.dataset.id = item.id;
    card.append(el('span',item.icon,'icon'),el('span',categories[item.category],'category'),el('h2',item.name),el('p',item.description),el('span','认识一下 ↗','open'));
    card.addEventListener('click',() => openDetail(item.id).catch(e=>notice(e.message,true))); $('#cards').append(card);
  }
}
function setBots(items) { bots = items; const previous = $('#bot').value; $('#bot').replaceChildren(el('option','选择要覆盖的 Bot')); $('#bot').firstChild.value = ''; for (const bot of bots) { const option = el('option',bot.display_name || bot.name || bot.id); option.value = bot.id; $('#bot').append(option); } if (bots.some(b=>b.id === previous)) $('#bot').value = previous; updateActions(); }
function updateActions() { $('#apply').disabled = busy || !$('#bot').value; $('#preview').disabled = busy || !$('#bot').value; $('#download').disabled = busy; }
function contentSection(title, text, target) { target.append(el('h3',title),el('p',text)); }
async function openDetail(id) {
  selected = await api('/api/template/'+id); $('#detail-category').textContent = categories[selected.category]; $('#detail-title').replaceChildren(el('span',selected.icon,'icon'),el('h2',selected.name)); $('#detail-description').textContent = selected.description;
  const play = $('#tab-play'); play.replaceChildren(); play.className = 'content'; play.append(el('div',selected.persona.greeting,'greeting')); contentSection('性格',selected.persona.personality,play);
  play.append(el('h3','互动流程')); const list = el('ol'); selected.persona.workflow.forEach(step=>list.append(el('li',step))); play.append(list);
  contentSection('试着这样开始',selected.persona.examples[0].user,play); contentSection('角色可能这样回应',selected.persona.examples[0].assistant,play); contentSection('设置取舍',selected.setting_rationale,play);
  $('#parameters').replaceChildren();
  for (const [key,spec] of Object.entries(selected.parameters)) { const label = el('label',spec.label); let input;
    if (spec.enum) { input = el('select'); spec.enum.forEach(value=>{ const option = el('option',value); option.value=value; input.append(option); }); }
    else { input = el('input'); input.type=spec.type === 'integer' ? 'number':'text'; if(spec.minimum!==undefined) input.min=spec.minimum; if(spec.maximum!==undefined) input.max=spec.maximum; }
    input.value=spec.default; input.dataset.parameter=key; label.append(input); $('#parameters').append(label);
  }
  $('#settings').value=JSON.stringify(selected.settings,null,2); $('#customization').value=JSON.stringify(selected.customization,null,2); const sources=$('#tab-sources'); sources.replaceChildren(); sources.className='content';
  sources.append(el('p','公开资料提供背景；互动场景、对白与调参为本库创作。作品奖项用于解释选材覆盖，不代表每个角色的人气排名。'));
  selected.sources.forEach(source=>{ const link=el('a',source.title); link.href=source.url; link.target='_blank'; link.rel='noopener'; sources.append(link,el('p',source.note)); });
  $('#result').hidden=true; showTab('play'); updateActions(); $('#detail').showModal();
}
function showTab(name) { for (const tab of ['play','tune','sources']) $('#tab-'+tab).hidden=tab!==name; document.querySelectorAll('[data-tab]').forEach(button=>button.classList.toggle('active',button.dataset.tab===name)); }
function payload() { const parameters={}; for(const input of document.querySelectorAll('[data-parameter]')) { const spec=selected.parameters[input.dataset.parameter]; if(!input.checkValidity()) throw new Error('请检查参数范围：'+spec.label); parameters[input.dataset.parameter]=spec.type==='integer'?Number(input.value):input.value; } const raw=JSON.parse($('#settings').value); const settings={}; for (const [key,value] of Object.entries(raw)) if (!(value && typeof value==='object' && value.binding==='inherit') && JSON.stringify(value)!==JSON.stringify(selected.settings[key])) settings[key]=value; return {template:selected.id,bot_id:$('#bot').value,parameters,settings,customization:JSON.parse($('#customization').value)}; }
async function apply(dryRun) { if(!$('#bot').value) return; busy=true; updateActions(); try { const data=payload(); data.dry_run=dryRun; const result=await api('/api/apply',data); $('#result').textContent=JSON.stringify(result,null,2); $('#result').hidden=false; notice(dryRun?'覆盖预览已生成，尚未修改 Bot':'应用成功：人格和设置已回读验证，原配置已备份'); } catch(e) { $('#result').textContent=e.message; $('#result').hidden=false; notice(e.message,true); } finally { busy=false; updateActions(); } }
$('#search').addEventListener('input',draw); $('#close').addEventListener('click',()=>$('#detail').close()); $('#detail').addEventListener('click',event=>{if(event.target===$('#detail')) $('#detail').close();}); document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>showTab(button.dataset.tab))); $('#bot').addEventListener('change',updateActions); $('#apply').addEventListener('click',()=>apply(false)); $('#preview').addEventListener('click',()=>apply(true));
$('#connect-form').addEventListener('submit',async event=>{event.preventDefault(); const button=event.target.querySelector('button'); button.disabled=true; try { const result=await api('/api/connect',{url:$('#url').value,username:$('#username').value,password:$('#password').value,token:$('#token').value}); $('#password').value=''; $('#token').value=''; setBots(result.items||result.data||[]); notice(`已连接，找到 ${bots.length} 个 Bot`); } catch(e) { notice(e.message,true); } finally {button.disabled=false;} });
$('#download').addEventListener('click',async()=>{busy=true;updateActions();try { const response=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});if(!response.ok){const result=await response.json();throw new Error(result.error);} const url=URL.createObjectURL(await response.blob());const link=el('a');link.href=url;link.download=selected.id+'.memoh.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('导入包已下载；在 Memoh 中选择导入并新建 Bot。');}catch(e){notice(e.message,true);}finally{busy=false;updateActions();}});
for (const [key,label] of Object.entries(categories)) { const button=el('button',label);button.classList.toggle('active',key==='all');button.addEventListener('click',()=>{category=key;$('#categories').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===button));draw();});$('#categories').append(button); }
fetch('/catalog.json').then(response=>response.json()).then(items=>{catalog=items;draw();}).catch(e=>notice(e.message,true));
