"""Complete, explicit Bot customization requests, scoped to the selected Bot."""
import copy
import json
import os
import posixpath
import re
from pathlib import Path
from urllib.parse import quote,urlencode
from .api import APIError

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'docs/research/configuration-contract.json').read_text())
INHERIT={'binding':'inherit'}


def schema_for(schema):
    if '$ref' in schema:return schema_for(CONFIG['definitions'][schema['$ref'].rsplit('/',1)[-1]])
    if 'allOf' in schema:
        result={k:v for k,v in schema.items() if k!='allOf'}
        for child in schema['allOf']:
            value=schema_for(child)
            result.update({k:v for k,v in value.items() if k not in ['properties','required']})
            result.setdefault('properties',{}).update(value.get('properties',{}))
            result['required']=list(set(result.get('required',[])+value.get('required',[])))
        return result
    return schema


def form(schema):
    if schema.get('$ref','').endswith('schedule.NullableInt'):return 7
    schema=schema_for(schema)
    if 'enum' in schema:return schema['enum'][0]
    kind=schema.get('type')
    if kind=='object':return {k:form(v) for k,v in schema.get('properties',{}).items()}
    if kind=='array':return []
    if kind=='integer' or kind=='number':return 0
    if kind=='boolean':return False
    return ''


def defaults(template):
    sections={}
    for key,spec in CONFIG['surfaces'].items():
        request=form(spec['schema'])
        if key=='profile':request.update(template['profile'],name=template['id'],metadata={})
        if key=='creation':request.update(template['profile'],name=template['id'],wait_for_ready=True,acl_preset='personal')
        if key in ['profile','creation']:request['avatar_url']=copy.deepcopy(INHERIT)
        if key in ['mcp','mcp_update']:request.update(name=template['id']+'-optional-mcp',transport='streamable-http',url='https://example.invalid/mcp',is_active=False)
        if key in ['schedules','schedule_update']:
            request.update(name=template['id']+'-daily',pattern='0 21 * * *',command='用当前角色口吻询问今天一件小事。',enabled=False,max_calls=7)
            execution=request if key=='schedules' else request['execution']
            execution.update(max_run_seconds=300,run_target='new_session')
        if key=='workdirs':request.update(name=template['id']+'-notes',path='/data/notes')
        if key=='resource_limits':request['resource_limits']={'cpu_millicores':500,'memory_bytes':536870912,'storage_bytes':5368709120}
        if key in ['agents','agent_update']:request.update(name=template['id']+'-optional-agent',enabled=False)
        if key=='agents':request['runtime']='codex'
        if key in ['acl_rules','acl_rule_update']:request.update(description=template['id']+'-optional-rule',enabled=False,effect='allow')
        if key=='skills':request['skills']=[f"---\nname: {template['id']}-interaction\ndescription: 用户明确要求本角色的互动玩法时使用\n---\n\n# 互动参考\n\n"+'\n'.join('- '+s for s in template['persona']['workflow'])+'\n\n不逐轮执行；日常聊天先接住用户的话题。\n']
        if key=='workspace_files':request.update(path='/data/USER.md',content='用户主动提供并同意保留的偏好写在这里。')
        if key=='memory':request.update(message='这里放用户明确同意保存的偏好或虚构剧情状态。',namespace='bot',infer=False,embedding_enabled=False,metadata={'template_id':template['id']})
        if key=='channels':request.update(disabled=True)
        sections[key]={'mode':'inherit','path_parameters':{p:'' for p in spec['path_parameters']},'requests':[request]}
        if key.startswith('channel_') and 'platform' in spec:
            platform=spec['platform']
            sections[key]['path_parameters']['platform']=platform
            request['disabled']=True
            def channel_fields(schema,credentials=False):
                fields={}
                for name,field in ((schema or {}).get('fields') or {}).items():
                    if credentials and field.get('type')=='secret':fields[name]={'env':'MEMOH_'+platform.upper()+'_'+re.sub(r'(?<!^)(?=[A-Z])','_',name).upper()}
                    elif field.get('enum'):fields[name]=field['enum'][0]
                    elif field.get('type')=='bool':fields[name]=False
                    elif field.get('type')=='number':fields[name]=field.get('example',0)
                    else:fields[name]=''
                return fields
            request['credentials']=channel_fields(spec.get('channel_schema'),True)
            request['routing']=channel_fields(spec.get('routing_schema'))
            sections[key]['target_spec']=spec.get('target_spec')
        sections[key]['apply_supported']=spec['apply_supported']
    sections['hooks']={'mode':'inherit','path_parameters':{},'requests':[{'version':1,'enabled':False,'env':{},'defaults':{'timeout':'5s','on_error':'ignore','max_output_bytes':8192,'trigger_nested_hooks':False},
        'hooks':[{'name':template['id']+'-optional-hook','event':'TurnEnd','matcher':'','enabled':False,'priority':0,'conditions':[{'expr':'false'}],
                  'actions':[{'type':'command','command':"printf '{}'",'tool':'','server':'','input':{},'timeout':'5s','on_error':'ignore','work_dir':'/data','trigger_nested_hooks':False}]}]}]}
    sections['connector_bindings']={'mode':'inherit','connection_id':INHERIT,'connector_type':INHERIT,'auth_method':INHERIT,'credential_fields':{},'oauth_scopes':[],
        'binding_note':'最新版通过 App 的 app_connector_credentials / app_connector_oauth 入口授权，再通过 connector_enabled 调整开关。OAuth 需用户在 Memoh 完成。'}
    sections['hooks']['supported_events']=['PreToolUse','PostToolUse','ToolError','SessionStart','UserMessageReceived','BeforePromptBuild','AfterPromptBuild','BeforeModelCall','AfterModelCall','TurnEnd','TurnError','BeforeMemorySearch','AfterMemorySearch','BeforeMemoryWrite','AfterMemoryWrite','MemoryExtracted','WorkspaceStart','WorkspaceStop','BeforeWorkspaceCommand','AfterWorkspaceCommand','BeforeFileWrite','AfterFileWrite','BeforeApprovalCreate','ApprovalRequested','ApprovalResolved','ApprovalTimeout','InboundMessageNormalized','BeforeOutboundMessage','AfterOutboundMessage','ChannelDeliveryFailed','PreCompact','PostCompact','SubagentStart','SubagentStop']
    sections['model_sampling']={'mode':'inherit','request_defaults':{'temperature':INHERIT,'top_p':INHERIT,'max_tokens':INHERIT},'binding_note':'当前 Bot Settings 无这些字段；由所选模型的 Provider 配置决定，不能通过 Bot API 写入。'}
    return sections


def resolve(value):
    if isinstance(value,dict):
        if set(value)=={'literal'}:return value['literal']
        if set(value)=={'env'}:
            name=value['env']
            if name not in os.environ:raise ValueError('缺少实例环境绑定：'+name)
            return os.environ[name]
        return {k:resolve(v) for k,v in value.items() if v!=INHERIT and not (isinstance(v,str) and v=='')}
    if isinstance(value,list):return [resolve(v) for v in value]
    return value


def validate_body(value,schema,label):
    if schema.get('$ref','').endswith('schedule.NullableInt'):
        if value is None or type(value) is int:return
        raise ValueError(label+': max_calls 需要整数或 null')
    schema=schema_for(schema);kind=schema.get('type')
    valid={'string':isinstance(value,str),'boolean':type(value) is bool,'integer':type(value) is int,
           'number':type(value) in (int,float),'object':isinstance(value,dict),'array':isinstance(value,list)}
    if kind and not valid.get(kind,True):raise ValueError(label+': 请求字段类型错误')
    if 'enum' in schema and value not in schema['enum']:raise ValueError(label+': 不支持的选项')
    if kind=='object':
        for key in schema.get('required',[]):
            if key not in value or value[key]=='':raise ValueError(label+': 缺少 '+key)
        for key,item in value.items():
            child=schema.get('properties',{}).get(key)
            if child is None:
                if 'properties' in schema and 'additionalProperties' not in schema:raise ValueError(label+': 未知字段 '+key)
                child=schema.get('additionalProperties',{})
            if isinstance(child,dict):validate_body(item,child,label+'.'+key)
    elif kind=='array':
        for item in value:validate_body(item,schema.get('items',{}),label+'[]')


def plan(template,overrides,bot_id,contract):
    sections=copy.deepcopy(template.get('customization',{}))
    for key,value in (overrides or {}).items():
        if key not in sections:raise ValueError('未知定制面：'+key)
        sections[key]=value
    actions=[]
    for key,section in sections.items():
        if section.get('mode','inherit')=='inherit':continue
        if section.get('mode')!='apply':raise ValueError(key+': mode 必须是 inherit 或 apply')
        if key in ['model_sampling','connector_bindings'] or key in CONFIG['surfaces'] and not CONFIG['surfaces'][key]['apply_supported']:
            raise ValueError(key+' 不属于可持久写入的 Bot 配置；请使用其声明的宿主配置/授权入口')
        if key=='hooks':
            spec={'path':'/bots/{bot_id}/container/fs/write','method':'POST','path_parameters':[]}
        else:spec=CONFIG['surfaces'][key]
        if spec['path'] not in contract['paths']:raise ValueError('实例不支持定制接口：'+key)
        if spec['method'].lower() not in contract['paths'][spec['path']]:raise ValueError('实例不支持定制方法：'+key)
        params=section.get('path_parameters',{})
        path=spec['path'].replace('/bots/{id}','/bots/'+quote(bot_id,safe=''),1).replace('/bots/{bot_id}','/bots/'+quote(bot_id,safe=''),1)
        for name in spec.get('path_parameters',[]):
            if not params.get(name):raise ValueError(key+': 缺少路径参数 '+name)
            path=path.replace('{'+name+'}',quote(str(params[name]),safe=''))
        for raw in section.get('requests',[]):
            body=resolve(raw)
            if key!='hooks':validate_body(body,spec['schema'],key)
            if key=='hooks':body={'path':'/data/.memoh/hooks.json','content':json.dumps(body,ensure_ascii=False,indent=2)+'\n'}
            if key=='workspace_files':
                body['path']=posixpath.normpath(body.get('path',''))
                if not body['path'].startswith('/data/'):raise ValueError('模板工作区文件必须位于 /data/')
                if body['path']=='/data/AGENTS.md':raise ValueError('AGENTS.md 请通过人格参数修改')
            actions.append({'section':key,'method':spec['method'],'path':path,'body':body})
    # Ownership changes happen after the remaining configuration is verified.
    actions.sort(key=lambda a:2 if a['section']=='owner' else 0 if a['section'] in ['workspace_files','hooks','skills'] else 1)
    return actions


def safe_plan(actions):
    return [{'section':a['section'],'method':a['method'],'path':a['path'],'fields':list(a['body'])} for a in actions]


def mcp_body(connection):
    return {'name':connection.get('name',''),'is_active':connection.get('is_active',True),'auth_type':connection.get('auth_type',''),
            'transport':'sse' if connection.get('type')=='sse' else 'streamable-http',
            'command':'','args':[],'env':{},'cwd':'','url':'','headers':{},**connection.get('config',{})}


def snapshot_actions(client,actions):
    snapshots=[]
    for action in actions:
        path=action['path'];body=action['body'];section=action['section']
        read_path=path
        if section in ['workspace_files','hooks']:
            read_path=path.rsplit('/',1)[0]+'/read?'+urlencode({'path':body['path']})
        elif section=='skills':read_path=path
        elif section in ['owner','profile']:read_path=path.rsplit('/owner',1)[0]
        elif section=='packages':read_path=path.rsplit('/install-package',1)[0]+'/packages'
        elif section=='skill_actions':read_path=path.rsplit('/actions',1)[0]
        elif section=='app_connector_credentials':read_path='/'.join(path.split('/')[:3])+'/connectors'
        try:before=client.request('GET',read_path)
        except APIError as exc:
            if exc.status!=404:raise
            before=None
            if section not in ['workspace_files','hooks']:
                parent=read_path.rsplit('/',1)[0]
                try:
                    collection=client.request('GET',parent)
                    items=collection if isinstance(collection,list) else next((v for v in collection.values() if isinstance(v,list)),[])
                    before=next((i for i in items if isinstance(i,dict) and i.get('id')==read_path.rsplit('/',1)[-1]),collection)
                    read_path=parent
                except APIError as parent_error:
                    if parent_error.status!=404:raise
        state={'action':copy.deepcopy(action),'before':before,'read_path':read_path}
        if section=='profile' and isinstance(before,dict):before.setdefault('metadata',{})
        items=before if isinstance(before,list) else next((v for v in (before or {}).values() if isinstance(v,list)),[]) if isinstance(before,dict) else []
        items=[v for v in items if isinstance(v,dict)]
        updates={'mcp':('mcp_update','name'),'schedules':('schedule_update','name'),'agents':('agent_update','name'),
                 'workdirs':('workdir_update','name'),'acl_rules':('acl_rule_update','description')}
        if section in updates:
            update,key=updates[section]
            match=next((i for i in items if body.get(key) and i.get(key)==body[key]),None)
            if match:
                if section=='schedules':match.setdefault('max_calls',None)
                state['before']=mcp_body(match) if section=='mcp' else match
                state['action']['method']=CONFIG['surfaces'][update]['method']
                state['action']['path']=path+'/'+quote(match['id'],safe='')
                properties=schema_for(CONFIG['surfaces'][update]['schema']).get('properties',{})
                state['action']['body']={k:v for k,v in body.items() if k in properties}
                if section=='schedules':
                    execution=schema_for(properties['execution']).get('properties',{})
                    state['action']['body']['execution']={k:v for k,v in body.items() if k in execution}
        if section=='mcp_update' and isinstance(state['before'],dict) and 'config' in state['before']:state['before']=mcp_body(state['before'])
        if section in ['workspace_files','hooks'] and before and before.get('revision'):
            state['action']['body'].setdefault('expectedRevision',before['revision'])
        if section=='skills':
            files=[]
            for raw in body.get('skills',[]):
                match=re.search(r'^name:\s*[\"\']?([a-z0-9_-]+)[\"\']?\s*$',raw,re.M)
                if not match:raise ValueError('技能需要简单的 frontmatter name')
                file_path=body.get('source_path') or '/data/skills/user/personal/'+match[1]+'/SKILL.md'
                if not posixpath.normpath(file_path).startswith('/data/'):raise ValueError('技能必须位于 /data/')
                read=path.rsplit('/skills',1)[0]+'/fs/read?'+urlencode({'path':file_path})
                try:original=client.request('GET',read)
                except APIError as exc:
                    if exc.status!=404:raise
                    original=None
                files.append({'path':file_path,'before':original,'content':raw.strip()+'\n','read_path':read})
            state['skill_files']=files
        snapshots.append(state)
    return snapshots


def verify_readback(client,state,receipt):
    action=state['action'];body=action['body'];section=action['section'];identifier=receipt.get('response_id')
    read=state['read_path']+'/'+quote(identifier,safe='') if section=='app_connector_credentials' and identifier else state['read_path']
    try:actual=client.request('GET',read)
    except APIError as exc:
        if exc.status!=404 or not identifier:raise
        actual=client.request('GET',action['path'].rsplit('/',1)[0]+'/'+quote(identifier,safe=''))
    items=actual if isinstance(actual,list) else next((v for v in actual.values() if isinstance(v,list)),[]) if isinstance(actual,dict) else []
    items=[v for v in items if isinstance(v,dict)]
    if items:
        actual=next((v for v in items if identifier and v.get('id')==identifier),None) or next((v for v in items if body.get('name') and v.get('name')==body['name']),actual)
    if section=='skills':
        for file in state.get('skill_files',[]):
            if client.request('GET',file['read_path']).get('content')!=file['content']:raise ValueError('技能文件回读不一致')
        return ['skills']
    if section=='resource_limits':actual={'resource_limits':actual.get('resource_limits',{}).get('desired',{})}
    if section in ['mcp','mcp_update'] and isinstance(actual,dict) and 'config' in actual:actual=mcp_body(actual)
    expected=body
    if section in ['workspace_files','hooks']:expected={'path':body['path'],'content':body['content']}
    if section=='schedules' and 'execution' in body:expected={**body,**body['execution']};expected.pop('execution')
    verified=[]
    # Credential read APIs deliberately mask secrets. Report fields actually
    # compared, rather than claiming credentials or opaque metadata were verified.
    ignored={'credentials','fields','metadata','expectedRevision','source_path','transport'}
    if isinstance(actual,dict):
        for key,value in expected.items():
            if key in ignored or key not in actual:continue
            if actual[key]!=value:raise ValueError(section+': 回读不一致：'+key)
            verified.append(key)
    return verified


def execute(client,snapshots,record=None):
    receipts=[]
    for state in snapshots:
        action=state['action']
        response=client.request(action['method'],action['path'],action['body'])
        entity=response
        if isinstance(entity,dict):
            for key in ['item','installation','app','connection','grant']:
                if isinstance(entity.get(key),dict):entity=entity[key];break
        identifier=next((entity.get(k) for k in ['id','installation_id','connection_id','channel_identity_id'] if entity.get(k)),None) if isinstance(entity,dict) else None
        receipt={'section':action['section'],'path':action['path'],'response_id':identifier,'state_index':len(receipts)}
        receipts.append(receipt)
        if record:record(receipts)
        receipt['verified_fields']=verify_readback(client,state,receipt)
        if record:record(receipts)
    return receipts


def undo(client,snapshots,receipts):
    errors=[]
    for receipt in reversed(receipts):
        state=snapshots[receipt['state_index']];action=state['action'];before=state['before'];body=action['body'];path=action['path'];section=action['section']
        try:
            if section in ['workspace_files','hooks']:
                latest=client.request('GET',state['read_path'])
                if latest.get('content')!=body['content']:continue
                if before is None:client.request('POST',path.rsplit('/',1)[0]+'/delete',{'path':body['path']})
                else:client.request('POST',path,{'path':body['path'],'content':before['content'],'expectedRevision':latest.get('revision','')})
            elif section=='owner':client.request('PUT',path,{'owner_user_id':before['owner_user_id']})
            elif section=='skills':
                fs_root=path.rsplit('/skills',1)[0]+'/fs'
                for file in state.get('skill_files',[]):
                    latest=client.request('GET',file['read_path'])
                    if latest.get('content')!=file['content']:continue
                    if file['before'] is None:client.request('POST',fs_root+'/delete',{'path':file['path']})
                    else:client.request('POST',fs_root+'/write',{'path':file['path'],'content':file['before']['content'],'expectedRevision':latest.get('revision','')})
            elif action['method'] in ['PUT','PATCH']:
                previous={k:before[k] for k in body if isinstance(before,dict) and k in before}
                if section=='resource_limits':previous={'resource_limits':before['resource_limits']['desired']}
                if section=='schedules' and 'execution' in body:
                    keys=schema_for(schema_for(CONFIG['surfaces']['schedule_update']['schema'])['properties']['execution'])['properties']
                    previous['execution']={k:before.get(k,0 if k=='max_run_seconds' else '') for k in keys}
                if not previous:
                    errors.append(section+': 无可恢复的原状态，请按备份在 Memoh 检查并恢复')
                    continue
                client.request(action['method'],path,previous)
            elif receipt.get('response_id') and section not in ['memory','skill_actions','packages','channel_managers']:
                delete_path='/'.join(path.split('/')[:3])+'/connectors/'+quote(receipt['response_id'],safe='') if section=='app_connector_credentials' else path+'/'+quote(receipt['response_id'],safe='')
                client.request('DELETE',delete_path)
            else:
                errors.append(section+': 扩展 API 未提供通用恢复操作，请按备份中的 before 状态在 Memoh 恢复')
        except APIError as exc:
            if exc.status!=404:errors.append(section+': '+str(exc))
        except Exception as exc:errors.append(section+': '+str(exc))
    return errors
