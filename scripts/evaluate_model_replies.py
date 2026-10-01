#!/usr/bin/env python3
"""Collect actual Memoh replies on disposable bots, without a separate LLM client."""
import argparse
import json
import os
import re
import sys
import time
import uuid
import hashlib
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memoh_templates.api import Client
from memoh_templates.apply import apply_template
from memoh_templates.catalog import load,render
from chat_transport import answer

CASES={
 'elon-musk':['我想做一台能把袜子自动配对的小机器，但朋友都觉得我想太多了。','先别给我商业计划，就当两个朋友聊这件怪点子。','其实最烦的是洗完衣服只剩一只袜子，你说第一步怎么试最省钱？'],
 'donald-trump':['我跟室友都想坐靠窗的位置，谁也不肯让步。你会怎么谈？','别演讲，帮我想一句开玩笑又不惹人烦的话。','如果他还是不同意呢？'],
 'chiang-kai-shek':['我们来玩一个不涉及真实战事的虚构幕僚场景：仓库缺粮、船期又延误了，我这个新人先看什么？','别训我，也别每轮都让我交报告，像平常交谈一样带我想。','有人建议把困难瞒着，你怎么看？'],
 'jay-chou':['下雨天等公交，我想起学生时代放学买的那杯奶茶。你脑中会出现什么画面？','不要写歌词，也别让我完成创作任务，随便聊聊。','我记得塑料吸管插歪了，珍珠卡在半路，特别狼狈。'],
 'stephen-chow':['我今天加班到十点，回家只剩一包泡面，还忘了买鸡蛋。','别像演小品，轻轻吐槽一句就好。','算了，我去煎一片午餐肉，算不算有排面？'],
 'frieren':['今天下班只想躺着，感觉自己把一天浪费了。你陪我聊两句吧。','我正看窗外下雨，茶已经凉了。','不要给我小任务，就陪我坐一会儿。'],
 'maomao':['我们在虚构茶馆里，一桌客人没喝茶就走了，杯口留着一个指印，你觉得哪里有意思？','先别下结论，我看到店里所有杯子的缺口都朝同一个方向。','把推理强度降一点，来句有点损的吐槽吧。'],
 'anya-forger':['明天要去一个陌生地方认识新朋友，我现在有点紧张。','我怕一开口就讲错话。','你怎么知道我紧张？你真的会读心吗？'],
 'zhongli':['我花了一下午挑杯子，最后什么也没买，是不是挺无聊的？','少讲道理，像逛完街坐下聊天那样就好。','有一只青色杯子我还记着，可是价格有点贵。'],
 'trpg-gm':['开一局十分钟的奇幻小冒险。我是总丢钥匙的见习邮差，想把一封信送到会走路的灯塔。','我先问路边卖糖的老太太，灯塔今天去哪了。','我不想战斗，能用我那串响得很烦的钥匙做点什么吗？'],
 'locked-room':['我们玩公平的小密室。我想从一间钟表店出去，你先给我一个能观察的东西。','我只看柜台下方的灰尘，不碰别的。','先别给答案，也别突然添一把万能钥匙。'],
 'ghost-roommate':['我明明把耳机放桌上了，回来却不见了。你这个室友有没有看见？','你别像客服一样问一堆排查问题，先承认是不是你拿的。','那你陪我一起找，顺便讲讲你怎么会怕吸尘器。'],
}


def legacy_rest_answer(client,bot_id,text,expected):
    started=time.monotonic()
    client.request('POST','/bots/'+bot_id+'/web/messages',{'message':{'text':text,'id':str(uuid.uuid4())}})
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        sessions=client.request('GET','/bots/'+bot_id+'/sessions').get('items',[])
        if sessions:
            history=client.request('GET','/bots/'+bot_id+'/messages?session_id='+sessions[0]['id']+'&limit=100')['items']
            turns=[t for t in history if t.get('role')=='assistant']
            if len(turns)>=expected:
                latest=max(turns,key=lambda t:t.get('turn_position',t.get('timestamp','')))
                content=latest.get('text') or '\n'.join(m.get('content','') for m in latest.get('messages',[]) if m.get('type')=='text')
                if content:return content,round(time.monotonic()-started,2)
        time.sleep(.3)
    raise RuntimeError('No persisted assistant answer within 180 seconds')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',default='before');parser.add_argument('--templates',default=','.join(CASES));parser.add_argument('--models',default='');parser.add_argument('--turns',type=int,default=3);parser.add_argument('--roleplay-intensity',type=int);args=parser.parse_args()
    client=Client(os.environ.get('MEMOH_URL','http://127.0.0.1:12880'),os.environ.get('MEMOH_TOKEN',''),timeout=240)
    if not client.token:client.login(os.environ.get('MEMOH_USERNAME','admin'),os.environ['MEMOH_PASSWORD'])
    models=[m for m in client.request('GET','/models') if m.get('type')=='chat' and (not args.models or m['model_id'] in args.models.split(','))]
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'phase':args.phase,'upstream_commit':'1bfb42154e09efacd34f68898ceaab78c10c85f3','transport':'Memoh authenticated WebSocket -> native runtime -> configured provider; persisted chat readback','cases':[]}
    directory=Path(__file__).resolve().parents[1]/'verification/model-replies';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(args.phase+'.json')
    for model in models:
        for slug in args.templates.split(','):
            bot=client.request('POST','/bots',{'name':'reply-eval-'+uuid.uuid4().hex[:8],'wait_for_ready':True})
            bot_id=bot['id']
            case={'template':slug,'model':model['name'],'model_id':model['model_id'],'turns':[]}
            report['cases'].append(case)
            try:
                client.request('PUT','/bots/'+bot_id+'/settings',{'chat_model_id':model['id']})
                if slug!='default':
                    parameters={'roleplay_intensity':args.roleplay_intensity} if args.roleplay_intensity is not None else {}
                    template=load(slug)
                    apply_template(client,template,bot_id,parameters=parameters,backup_dir='.backups/reply-eval')
                    case['parameters']=parameters
                    case['prompt_sha256']=hashlib.sha256(render(template,parameters).encode()).hexdigest()
                inputs=CASES.get(slug,CASES['frieren'])[:args.turns]
                for index,text in enumerate(inputs,1):
                    response,elapsed=answer(client,bot_id,text,index)
                    password=os.environ.get('MEMOH_PASSWORD','')
                    if password:response=response.replace(password,'[redacted]')
                    case['turns'].append({'user':text,'assistant':response,'seconds':elapsed,'characters':len(response)})
                    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                    print(model['name']+' / '+slug+' / turn '+str(index)+' / '+str(len(response))+' chars',flush=True)
            except Exception as exc:
                case['error']=str(exc)
                path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                print(model['name']+' / '+slug+' / failed: '+str(exc),flush=True)
            finally:
                client.request('DELETE','/bots/'+bot_id)
                deadline=time.monotonic()+30
                while any(b['id']==bot_id for b in client.request('GET','/bots')['items']) and time.monotonic()<deadline:
                    time.sleep(.5)
    print('Saved actual replies: '+str(path))


if __name__=='__main__':main()
