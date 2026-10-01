#!/usr/bin/env python3
"""Deploy an independent, loopback-only Memoh evaluation stack on a Linux host.

Run on vultr-sg after building the pinned upstream images.
Private configuration is generated outside the repository with mode 600.
"""
import json
import os
import re
import secrets
import shlex
import subprocess
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(os.environ.get('MEMOH_EVAL_ROOT','/opt/memoh-template-eval'))
COMMIT='1bfb42154e09efacd34f68898ceaab78c10c85f3'
IMAGE=os.environ.get('MEMOH_EVAL_IMAGE','memoh-template-eval/upstream:1bfb421')
WEB_IMAGE=os.environ.get('MEMOH_EVAL_WEB_IMAGE','memoh-template-eval/web:1bfb421')


def private_env(path):
    result={}
    for line in Path(path).read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1)
            parsed=shlex.split(value)
            result[key]=parsed[0] if parsed else ''
    return result


def write_private(path,text):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:stream.write(text)
    os.chmod(path,0o600)


def main():
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    env_path=ROOT/'eval.env'
    if env_path.exists():
        values=private_env(env_path)
    else:
        password=os.environ.get('MEMOH_EVAL_ADMIN_PASSWORD')
        if not password:
            password=private_env('/opt/memoh-dev/secrets/memoh-dev.env')['MEMOH_ADMIN_PASSWORD']
        values={'MEMOH_ADMIN_PASSWORD':password,'POSTGRES_PASSWORD':secrets.token_hex(24),
                'PGVECTOR_PASSWORD':secrets.token_hex(24),'MEMOH_INTERNAL_RPC_SHARED_SECRET':secrets.token_hex(32),
                'MEMOH_JWT_SECRET':secrets.token_hex(32)}
        write_private(env_path,''.join(k+'='+shlex.quote(v)+'\n' for k,v in values.items()))
    with urlopen(f'https://raw.githubusercontent.com/felinics/Memoh/{COMMIT}/conf/app.docker.toml') as response:
        config=response.read().decode()
    def setting(section,key,value):
        nonlocal config
        pattern=r'(\['+re.escape(section)+r'\][\s\S]*?^'+re.escape(key)+r'\s*=\s*).*$'
        config,count=re.subn(pattern,lambda m:m[1]+json.dumps(value),config,count=1,flags=re.M)
        if count!=1:raise RuntimeError('Missing public configuration field: '+section+'.'+key)
    for section,key,value in [('server','addr',':8080'),('admin','password',values['MEMOH_ADMIN_PASSWORD']),
        ('auth','jwt_secret',values['MEMOH_JWT_SECRET']),('postgres','password',values['POSTGRES_PASSWORD']),
        ('pgvector','password',values['PGVECTOR_PASSWORD']),('containerd','namespace','template-eval')]:setting(section,key,value)
    write_private(ROOT/'config.toml',config)
    common={'restart':'unless-stopped','networks':['evaluation']}
    def db(database,password):return {**common,'image':'postgres:18-alpine' if database=='memoh' else 'pgvector/pgvector:pg18',
        'mem_limit':'512m','cpus':1,'environment':{'POSTGRES_DB':database,'POSTGRES_USER':'memoh','POSTGRES_PASSWORD':password},
        'volumes':[('postgres_data' if database=='memoh' else 'pgvector_data')+':/var/lib/postgresql'],
        'healthcheck':{'test':['CMD-SHELL','pg_isready -U memoh -d '+database],'interval':'5s','timeout':'3s','retries':20}}
    config_mount=str(ROOT/'config.toml')+':/app/config.toml:ro'
    rpc={'MEMOH_INTERNAL_RPC_SHARED_SECRET':values['MEMOH_INTERNAL_RPC_SHARED_SECRET'],
         'MEMOH_INTERNAL_RPC_SERVER_TARGET':'server:9090','MEMOH_INTERNAL_RPC_CHANNEL_TARGET':'channel:9091'}
    services={'postgres':db('memoh',values['POSTGRES_PASSWORD']),'pgvector':db('memoh_vector',values['PGVECTOR_PASSWORD'])}
    services['migrate']={'image':IMAGE,'entrypoint':['/app/memoh-server','migrate','up'],'networks':['evaluation'],
        'volumes':[config_mount,'memoh_data:/opt/memoh/data'],'depends_on':{'postgres':{'condition':'service_healthy'}}}
    services['server']={**common,'image':IMAGE,'entrypoint':['sh','/entrypoint.sh'],'privileged':True,'pid':'host','mem_limit':'2g','cpus':2,
        'environment':{**rpc,'GOMEMLIMIT':'1536MiB'},'extra_hosts':['host.docker.internal:host-gateway'],
        'volumes':[config_mount,'containerd_data:/var/lib/containerd','cni_state:/var/lib/cni','memoh_data:/opt/memoh/data'],
        'ports':['127.0.0.1:12880:8080'],
        'depends_on':{'migrate':{'condition':'service_completed_successfully'},'pgvector':{'condition':'service_healthy'}},
        'healthcheck':{'test':['CMD','wget','--quiet','--spider','http://127.0.0.1:8080/health'],'interval':'5s','timeout':'3s','start_period':'30s','retries':30}}
    services['channel']={**common,'image':IMAGE,'entrypoint':['/app/memoh-channel','serve'],'mem_limit':'768m','cpus':1,
        'environment':rpc,'volumes':[config_mount,'memoh_data:/opt/memoh/data'],
        'depends_on':{'server':{'condition':'service_healthy'}},
        'healthcheck':{'test':['CMD','wget','--quiet','--spider','http://127.0.0.1:8081/health'],'interval':'5s','timeout':'3s','retries':30}}
    services['web']={**common,'image':WEB_IMAGE,'mem_limit':'192m','cpus':0.5,
        'environment':{'MEMOH_SERVER_UPSTREAM':'server:8080','MEMOH_CHANNEL_UPSTREAM':'channel:8081'},
        'ports':['127.0.0.1:12882:8082'],'depends_on':{'channel':{'condition':'service_healthy'}}}
    volumes={key:{} for key in ['postgres_data','pgvector_data','containerd_data','cni_state','memoh_data']}
    # Main database migrations are canonical; use a fresh isolated DB when
    # moving from the cached release to this newer source snapshot.
    if IMAGE.startswith('memoh-template-eval/upstream:'):
        for service,key in [('postgres','postgres_data'),('pgvector','pgvector_data')]:
            services[service]['volumes']=[key+'_source:/var/lib/postgresql']
            volumes[key+'_source']={}
    compose={'name':'memoh-template-eval','services':services,'networks':{'evaluation':{}},'volumes':volumes}
    write_private(ROOT/'compose.json',json.dumps(compose,indent=2)+'\n')
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.json'),'up','-d'],check=True)
    print('Evaluation stack: API 127.0.0.1:12880, Web 127.0.0.1:12882; private config remains on server')


if __name__=='__main__':main()
