#!/usr/bin/env python3
"""Leave four dedicated demo bots in the isolated evaluation deployment."""
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deploy_eval import private_env
from memoh_templates.api import Client
from memoh_templates.apply import apply_template
from memoh_templates.catalog import load
from chat_transport import answer


def main():
    client=Client('http://127.0.0.1:12880')
    client.login('admin',private_env('/opt/memoh-template-eval/eval.env')['MEMOH_ADMIN_PASSWORD'])
    models={m['model_id']:m for m in client.request('GET','/models')}
    bots={b['name']:b for b in client.request('GET','/bots')['items']}
    demos=[('frieren','deepseek-v4-flash','窗外下雨，茶凉了，今天不想做任何任务。陪我坐一会儿吧。'),
           ('elon-musk','deepseek-v4-flash','我想做个给袜子配对的怪机器，先不谈创业，像朋友聊聊这个点子。'),
           ('anya-forger','k3','明天要认识新朋友，我有点紧张。别布置任务，陪我聊两句就好。'),
           ('trpg-gm','deepseek-v4-flash','开一个十分钟的小冒险。我是带着一串响钥匙的邮差，想给会走路的灯塔送信。')]
    for slug,model_id,text in demos:
        name='template-demo-'+slug
        bot=bots.get(name) or client.request('POST','/bots',{'name':name,'wait_for_ready':True})
        model=models[model_id]
        apply_template(client,load(slug),bot['id'],bindings={'chat_model_id':model['id']},backup_dir=Path(__file__).resolve().parents[1]/'.backups/demos',
                       customizations={'resource_limits':{'mode':'apply','requests':[{'resource_limits':{'cpu_millicores':500,'memory_bytes':536870912,'storage_bytes':5368709120}}]}})
        if not client.request('GET','/bots/'+bot['id']+'/sessions')['items']:
            response,_=answer(client,bot['id'],text,1)
            print(slug+': demo reply received ('+str(len(response))+' characters)')
    print('Demo bots ready: '+', '.join(slug for slug,_,_ in demos))


if __name__=='__main__':main()
