#!/usr/bin/env python3
"""Extract all persistent Bot customization request shapes from pinned OpenAPI."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SURFACES={
 'profile':('/bots/{id}','put'),
 'creation':('/bots','post'),
 'acl_rules':('/bots/{bot_id}/acl/rules','post'),
 'acl_default_effect':('/bots/{bot_id}/acl/default-effect','put'),
 'acl_rule_update':('/bots/{bot_id}/acl/rules/{rule_id}','put'),
 'channels':('/bots/{id}/channel/{platform}','put'),
 'channel_status':('/bots/{id}/channel/{platform}/status','patch'),
 'mcp':('/bots/{bot_id}/mcp','post'),
 'mcp_update':('/bots/{bot_id}/mcp/{id}','put'),
 'schedules':('/bots/{bot_id}/schedule','post'),
 'schedule_update':('/bots/{bot_id}/schedule/{id}','put'),
 'agents':('/bots/{bot_id}/agents','post'),
 'agent_update':('/bots/{bot_id}/agents/{id}','patch'),
 'agent_credentials':('/bots/{bot_id}/agents/{id}/credential','put'),
 'mcp_stdio':('/bots/{bot_id}/mcp-stdio','post'),
 'container_creation':('/bots/{bot_id}/container','post'),
 'dependency_install':('/bots/{bot_id}/dependencies/{dep_id}/install','post'),
 'dependency_update':('/bots/{bot_id}/dependencies/{dep_id}/update','post'),
 'workdir_git_branch':('/bots/{bot_id}/workdirs/{workdir_id}/git-branch','post'),
 'channel_webhook':('/bots/{id}/channel/{platform}/webhook-endpoint','post'),
 'acp_runtime':('/bots/{bot_id}/acp-runtimes','post'),
 'acp_mode':('/bots/{bot_id}/acp-runtimes/{runtime_id}/mode','patch'),
 'acp_model':('/bots/{bot_id}/acp-runtimes/{runtime_id}/model','patch'),
 'acp_reasoning':('/bots/{bot_id}/acp-runtimes/{runtime_id}/reasoning','patch'),
 'workdirs':('/bots/{bot_id}/workdirs','post'),
 'workdir_update':('/bots/{bot_id}/workdirs/{workdir_id}','patch'),
 'resource_limits':('/bots/{bot_id}/container/metrics','put'),
 'skills':('/bots/{bot_id}/container/skills','post'),
 'skill_actions':('/bots/{bot_id}/container/skills/actions','post'),
 'workspace_files':('/bots/{bot_id}/container/fs/write','post'),
 'memory':('/bots/{bot_id}/memory','post'),
 'memory_update':('/bots/{bot_id}/memory/{memory_id}','put'),
 'user_access':('/bots/{bot_id}/user-access','post'),
 'user_access_update':('/bots/{bot_id}/user-access/{grant_id}','put'),
 'channel_managers':('/bots/{bot_id}/channel-managers','post'),
 'owner':('/bots/{id}/owner','put'),
 'workspace_primary':('/bots/{bot_id}/workspace-targets/primary','put'),
 'workspace_remote':('/bots/{bot_id}/workspace-targets/remotes/{runtime_id}','put'),
 'workspace_tool_approval':('/bots/{bot_id}/workspace-targets/{target_id}/tool-approval','put'),
 'packages':('/bots/{bot_id}/supermarket/install-package','post'),
 'apps':('/bots/{bot_id}/apps','post'),
 'app_update':('/bots/{bot_id}/apps/update','post'),
 'app_connector_credentials':('/bots/{bot_id}/apps/{installation_id}/connectors/{connector_type}/api-key','post'),
 'app_connector_oauth':('/bots/{bot_id}/apps/{installation_id}/connectors/{connector_type}/oauth','post'),
 'connector_enabled':('/bots/{bot_id}/connectors/{connection_id}','patch'),
 'tts_defaults':('/bots/{bot_id}/tts/synthesize','post'),
}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('swagger');args=parser.parse_args()
    source=json.loads(Path(args.swagger).read_text())
    definitions={};surfaces={}
    def collect(schema):
        if isinstance(schema,dict):
            ref=schema.get('$ref')
            if ref:
                name=ref.rsplit('/',1)[-1]
                if name not in definitions:
                    definitions[name]=source['definitions'][name]
                    collect(definitions[name])
            for item in schema.values():collect(item)
        elif isinstance(schema,list):
            for item in schema:collect(item)
    for name,(path,method) in SURFACES.items():
        operation=source['paths'].get(path,{}).get(method)
        if not operation:continue
        schemas=[p['schema'] for p in operation.get('parameters',[]) if p.get('in')=='body' and 'schema' in p]
        schema=schemas[0] if schemas else {'type':'object','additionalProperties':{}}
        collect(schema)
        params=[p['name'] for p in operation.get('parameters',[]) if p.get('in')=='path' and p['name'] not in ['bot_id']]
        if path=='/bots/{id}' or path.startswith('/bots/{id}/'):params=[p for p in params if p!='id']
        surfaces[name]={'path':path,'method':method.upper(),'schema':schema,'path_parameters':params,
                        'summary':operation.get('summary',''),'apply_supported':name not in ['creation','tts_defaults','app_connector_oauth','container_creation','dependency_install','dependency_update','workdir_git_branch','mcp_stdio','acp_runtime','acp_mode','acp_model','acp_reasoning','channel_webhook']}
    # These handlers accept small local DTOs without complete Swagger bodies.
    surfaces['memory']['schema']={'type':'object','properties':{'message':{'type':'string'},'messages':{'type':'array','items':{'type':'object','properties':{'role':{'type':'string'},'content':{'type':'string'}}}},'namespace':{'type':'string'},'run_id':{'type':'string'},'metadata':{'type':'object'},'filters':{'type':'object'},'infer':{'type':'boolean'},'embedding_enabled':{'type':'boolean'}}}
    surfaces['memory_update']['schema']={'type':'object','required':['memory'],'properties':{'memory':{'type':'string'}}}
    channels=json.loads((ROOT/'docs/research/channel-schemas.json').read_text())['channels']
    for channel in channels:
        name='channel_'+channel['type']
        surfaces[name]={**surfaces['channels'],'platform':channel['type'],'channel_schema':channel.get('config_schema'),
                        'routing_schema':channel.get('user_config_schema'),'target_spec':channel.get('target_spec')}
    result={'upstream_commit':'1bfb42154e09efacd34f68898ceaab78c10c85f3','surfaces':surfaces,'definitions':definitions}
    (ROOT/'docs/research/configuration-contract.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Configuration surfaces:',len(surfaces),'request definitions:',len(definitions))


if __name__=='__main__':main()
