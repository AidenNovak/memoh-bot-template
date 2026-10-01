#!/usr/bin/env python3
"""Copy model bindings into the independent evaluation instance, server-side only."""
import copy
import sys
import json
import subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memoh_templates.api import Client
from deploy_eval import private_env


def main():
    password=private_env('/opt/memoh-template-eval/eval.env')['MEMOH_ADMIN_PASSWORD']
    source=Client('http://127.0.0.1:18080');source.login('admin',password)
    target=Client('http://127.0.0.1:12880');target.login('admin',password)
    providers={p['id']:p for p in source.request('GET','/providers')}
    # Provider API reads intentionally mask secrets. Read the existing dev DB
    # on this server into memory; never copy it to the Mac, output, or Git.
    raw=subprocess.run(['docker','exec','memoh-postgres','psql','-U','memoh','-d','memoh','-Atc',
        'SELECT json_object_agg(id, config) FROM providers'],capture_output=True,text=True,check=True)
    configs=json.loads(raw.stdout)
    for identifier,provider in providers.items():
        provider['config']=configs[identifier]
    copied={}
    existing={m['model_id']:m for m in target.request('GET','/models')}
    for model in source.request('GET','/models'):
        if model['type']!='chat' or not model.get('enable',True):continue
        provider=providers[model['provider_id']]
        if model['model_id'] in existing:
            target.request('PUT','/providers/'+existing[model['model_id']]['provider_id'],{'config':copy.deepcopy(provider['config'])})
            continue
        if provider['id'] not in copied:
            config=copy.deepcopy(provider['config'])
            result=target.request('POST','/providers',{'name':'Template evaluation '+provider['name'],
                'client_type':provider['client_type'],'config':config})
            copied[provider['id']]=result['id']
        payload={k:model[k] for k in ['name','model_id','type','enable','config'] if k in model}
        payload['provider_id']=copied[provider['id']]
        target.request('POST','/models',payload)
    print('Evaluation chat models: '+', '.join(m['name'] for m in target.request('GET','/models')))


if __name__=='__main__':main()
