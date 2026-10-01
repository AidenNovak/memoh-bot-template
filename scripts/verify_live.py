#!/usr/bin/env python3
"""Exercise presets against a real Memoh server using disposable bots only.

Set MEMOH_URL/MEMOH_TOKEN (or MEMOH_USERNAME/MEMOH_PASSWORD) before running.
This script never modifies existing bots or global provider configuration.
"""
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from memoh_templates.api import Client
from memoh_templates.apply import apply_template, restore, snapshot
from memoh_templates.bundle import bundle
from memoh_templates.catalog import load, render, templates


def upload(client, path, raw, mode='create'):
    boundary='memoh-template-'+uuid.uuid4().hex
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="mode"\r\n\r\n{mode}\r\n'
          f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="template.memoh.zip"\r\nContent-Type: application/zip\r\n\r\n').encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
    request=Request(client.base_url+path,data=body,headers={'Authorization':'Bearer '+client.token,'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
    with client.opener.open(request,timeout=180) as response:
        return json.load(response)


def main():
    client=Client(os.environ.get('MEMOH_URL','http://127.0.0.1:18080'),os.environ.get('MEMOH_TOKEN',''))
    if not client.token:client.login(os.environ.get('MEMOH_USERNAME','admin'),os.environ['MEMOH_PASSWORD'])
    response=client.request('GET','/models')
    models=response if isinstance(response,list) else response.get('items',[])
    model=next((m for m in models if m.get('type')=='chat' and m.get('enable',True)),None)
    if not model:raise RuntimeError('A configured chat model is required for live verification')
    before_ids={b['id'] for b in client.request('GET','/bots').get('items',[])}
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'instance':'Memoh dev (loopback API on vultr-sg)',
            'upstream_commit':'1bfb42154e09efacd34f68898ceaab78c10c85f3','applied':[], 'native_previews':[], 'restored':False,'native_imported':False,'cleanup':False}
    created_ids=[]
    try:
        bot=client.request('POST','/bots',{'name':'template-verification-'+uuid.uuid4().hex[:8],'display_name':'Template verification','wait_for_ready':True})
        bot_id=bot['id'];created_ids.append(bot_id)
        client.request('PUT','/bots/'+bot_id+'/settings',{'chat_model_id':model['id']})
        for file in ['/data/MEMORY.md','/data/PROFILES.md','/data/preserve-test.txt']:
            client.request('POST','/bots/'+bot_id+'/container/fs/write',{'path':file,'content':'verification sentinel: preserve '+file})
        original=snapshot(client,bot_id)
        first_backup=None
        for template in templates():
            result=apply_template(client,template,bot_id,backup_dir=ROOT/'.backups/live-verification')
            first_backup=first_backup or result['backup']
            if not result['verified']:raise RuntimeError('Apply did not verify')
            report['applied'].append(template['id'])
            for file in ['/data/MEMORY.md','/data/PROFILES.md','/data/preserve-test.txt']:
                actual=client.request('GET','/bots/'+bot_id+'/container/fs/read?'+urlencode({'path':file}))['content']
                if actual!='verification sentinel: preserve '+file:raise RuntimeError('User file changed')
            preview=upload(client,'/bots/backup/import/preview',bundle(template))
            if preview.get('conflicts'):raise RuntimeError('Native preview conflicts: '+template['id'])
            if not preview.get('restore_plan',{}).get('will_restore_workspace'):raise RuntimeError('Native preview omitted workspace')
            report['native_previews'].append(template['id'])
            print('verified '+template['id'],flush=True)
        restore(client,json.loads(Path(first_backup).read_text()))
        restored=snapshot(client,bot_id)
        if restored['profile']!=original['profile'] or restored['agents']['content']!=original['agents']['content']:
            raise RuntimeError('Restore differs from original')
        report['restored']=True
        client.request('DELETE','/bots/'+bot_id);created_ids.remove(bot_id)
        native=load('frieren')
        imported=upload(client,'/bots/backup/import',bundle(native))
        imported_id=imported['bot_id'];created_ids.append(imported_id)
        if any('failed' in w or 'skipped' in w for w in imported.get('warnings',[])):raise RuntimeError('Native import section failed')
        actual=client.request('GET','/bots/'+imported_id+'/container/fs/read?'+urlencode({'path':'/data/AGENTS.md'}))['content']
        if actual!=render(native):raise RuntimeError('Native import did not install actual AGENTS.md')
        report['native_imported']=True
    finally:
        cleanup_errors=[]
        for bot_id in created_ids:
            try:client.request('DELETE','/bots/'+bot_id)
            except Exception:cleanup_errors.append(bot_id)
        # Container-backed deletion can return before the bot disappears from lists.
        deadline=time.monotonic()+30
        while True:
            after_ids={b['id'] for b in client.request('GET','/bots').get('items',[])}
            if after_ids==before_ids or time.monotonic()>=deadline:break
            time.sleep(0.5)
        report['cleanup']=not cleanup_errors and before_ids==after_ids
        directory=ROOT/'verification'
        directory.mkdir(exist_ok=True)
        (directory/'live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        if cleanup_errors:print('Cleanup required for disposable bots: '+','.join(cleanup_errors),file=sys.stderr)
    if not report['cleanup']:raise RuntimeError('Disposable bot cleanup incomplete')
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in report.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
