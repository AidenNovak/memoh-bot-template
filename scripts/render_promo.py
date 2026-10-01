#!/usr/bin/env python3
"""Render a 30-second promo from generated art, real UI, code and original music.

Requires FFmpeg and a Chinese font. Run encoding on the Linux build host.
MEMOH_PROMO_FONT may override the existing WenQuanYi font path.
"""
import array
import json
import math
import os
import subprocess
import wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'promo'
WORK=OUT/'.render'
FONT=os.environ.get('MEMOH_PROMO_FONT','/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')
DURATIONS=[5.5,6.5,5.5,6.5,4.5,4.0]
FPS=30
WIDTH,HEIGHT=1280,720
INK='0x20372e'
PAPER='0xf6f3ec'
GREEN='0x547961'


def run(arguments):
    subprocess.run(arguments,check=True)


def music(path):
    """Write an original soft arpeggio; no external recordings or dependencies."""
    rate=44100
    chords=[(261.63,329.63,392.00,493.88),(293.66,349.23,440.00,523.25),
            (261.63,349.23,440.00,523.25),(246.94,293.66,392.00,440.00),
            (261.63,329.63,392.00,523.25),(261.63,329.63,392.00,493.88)]
    notes=[]
    for step in range(60):
        chord=chords[min(5,int(step*.5/5))]
        notes.append((step*.5,chord[[0,2,1,3,2,1,3,2][step%8]],.07 if step%4==0 else .046))
    with wave.open(str(path),'wb') as output:
        output.setparams((1,2,rate,0,'NONE','not compressed'))
        for second in range(30):
            pcm=array.array('h')
            active=[note for note in notes if second-2<=note[0]<=second+1]
            for index in range(rate):
                t=second+index/rate
                sample=0.0
                for start,freq,volume in active:
                    age=t-start
                    if 0<=age<2:
                        envelope=min(1,age/.018)*math.exp(-age*2.9)
                        sample+=volume*envelope*(math.sin(2*math.pi*freq*age)+.25*math.sin(4*math.pi*freq*age))
                sample*=min(1,t/.5,(30-t)/1.5)
                pcm.append(round(max(-1,min(1,sample))*32767))
            output.writeframes(pcm.tobytes())


class Scene:
    def __init__(self,index,image=None,screenshot=None):
        self.index=index
        self.inputs=[]
        self.filters=[]
        self.count=0
        self.label='base'
        if image:
            self.inputs=['-loop','1','-framerate',str(FPS),'-i',str(image)]
            self.filters.append("[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1,"
                                "zoompan=z='min(pzoom+0.00018,1.035)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1280x720:fps=30,format=yuv420p[base]")
        else:
            self.inputs=['-f','lavfi','-i',f'color=c={PAPER}:s=1280x720:r=30']
            self.filters.append('[0:v]setsar=1,format=yuv420p[base]')
        if screenshot:
            self.inputs+=['-loop','1','-framerate',str(FPS),'-i',str(screenshot)]
            self.box(488,100,760,570,'0x172d23@0.07')
            self.filters.append('[1:v]scale=740:554:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=740:556:(ow-iw)/2:(oh-ih)/2:white,setsar=1[shot]')
            self.effect('overlay=500:108',other='shot')

    def effect(self,filter,other=None):
        self.count+=1
        label='v'+str(self.count)
        self.filters.append('['+self.label+']'+('['+other+']' if other else '')+filter+'['+label+']')
        self.label=label

    def box(self,x,y,width,height,color):
        self.effect(f'drawbox=x={x}:y={y}:w={width}:h={height}:color={color}:t=fill')

    def text(self,text,x,y,size=30,color=INK,delay=.15,line_spacing=12):
        path=WORK/f'text-{self.index}-{self.count}.txt'
        path.write_text(text)
        alpha=f'min(1,max(0,(t-{delay})*4))'.replace(',','\\,')
        self.effect(f"drawtext=fontfile={FONT}:textfile={path}:fontsize={size}:fontcolor={color}:"
                    f"x={x}:y='{y}+10*exp(-6*t)':alpha='{alpha}':line_spacing={line_spacing}")

    def header(self):
        self.text('MEMOH  /  BOT TEMPLATE',64,48,19,GREEN,delay=0)
        self.text(f'{self.index+1:02d} / 06',1144,48,18,GREEN,delay=0)
        self.box(64,685,1152,2,'0x547961@0.25')

    def render(self):
        target=WORK/f'scene-{self.index}.mp4'
        run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',*self.inputs,
             '-filter_complex_threads','2','-filter_complex',';'.join(self.filters),'-map','['+self.label+']',
             '-t',str(DURATIONS[self.index]),'-r','30','-an','-c:v','libx264','-preset','fast','-crf','19',
             '-threads','4','-pix_fmt','yuv420p','-movflags','+faststart',str(target)])
        return target


def main():
    if not Path(FONT).exists():raise RuntimeError('Chinese font missing; set MEMOH_PROMO_FONT')
    WORK.mkdir(parents=True,exist_ok=True)
    hero=OUT/'assets/hero.png';closing=OUT/'assets/closing.png'
    for path in [hero,closing,ROOT/'verification/gallery-desktop.png',ROOT/'verification/gallery-detail.png',ROOT/'verification/memoh-chat.png']:
        if not path.exists():raise RuntimeError('Missing promo asset: '+str(path))
    scenes=[]
    s=Scene(0,image=hero);s.header()
    s.text('给 Bot\n一点自己的性格。',64,190,54,line_spacing=18)
    s.text('56 个角色，聊点不一样的。',64,370,25,delay=.55)
    s.box(64,462,333,49,'0xf6f3ec@0.85');s.text('开源  ·  可定制  ·  原生导入',80,476,19,GREEN,delay=.8)
    scenes.append(s.render())
    s=Scene(1,screenshot=ROOT/'verification/gallery-desktop.png');s.header()
    s.text('选个角色，\n一键换上。',64,187,48)
    s.text('名人演绎 · 动漫 · 游戏\n还有原创互动玩法',64,351,23,delay=.5)
    s.text('应用前自动备份\n保留已有模型绑定',64,491,22,GREEN,delay=1)
    scenes.append(s.render())
    s=Scene(2,screenshot=ROOT/'verification/gallery-detail.png');s.header()
    s.text('口吻也能\n由你来定。',64,187,48)
    s.text('13 个人格旋钮\n自然聊天 / 按需分析\n想认真时再展开',64,350,23,delay=.5)
    s.text('称呼、温度、幽默、剧情强度…',64,519,19,GREEN,delay=.9)
    scenes.append(s.render())
    s=Scene(3,screenshot=ROOT/'verification/memoh-chat.png');s.header()
    s.text('真实对话，\n不必每句都开会。',64,167,42)
    s.text('今天不想做任务，陪我坐一会儿。',64,314,21,GREEN,delay=.4)
    # This excerpt is from the actual model run, reproduced verbatim.
    s.text('“雨不急，我们也不急。\n你什么时候想说话都可以，\n不想说也行。”',64,383,25,delay=.7)
    s.text('芙莉莲模板 · DeepSeek V4 Flash\n截图来自实际部署的 Memoh',64,541,17,GREEN,delay=1.2)
    scenes.append(s.render())
    s=Scene(4,image=closing);s.box(0,0,780,720,'0xf6f3ec@0.93');s.header()
    s.text('人设之外，玩法也开放。',64,149,40)
    s.text('58 个配置面，放进可编辑的模板。',64,215,24,GREEN,delay=.3)
    labels=['人设与口吻','模型与渠道','技能与 MCP','记忆与任务','文件与工作区','权限与 Hooks']
    for i,label in enumerate(labels):
        x=64+(i%2)*303;y=293+(i//2)*103
        s.box(x,y,280,76,'0xffffff@0.88');s.text(label,x+18,y+24,23,delay=.25+i*.12)
    s.text('默认沿用现有绑定；授权内容按对应入口配置。',64,633,17,GREEN,delay=1)
    scenes.append(s.render())
    s=Scene(5,image=closing);s.header()
    s.text('挑个角色。\n从一句话开始。',64,190,50,line_spacing=18)
    s.text('56 种角色 · 开源可定制',64,363,25,GREEN,delay=.3)
    s.box(56,459,518,99,'0xf6f3ec@0.89')
    s.text('GitHub / AidenNovak',74,476,20,GREEN,delay=.5)
    s.text('memoh-bot-template',74,508,28,delay=.7)
    s.text('人物与作品角色均为原创演绎 · 非官方',64,639,17,GREEN,delay=1)
    scenes.append(s.render())
    soundtrack=WORK/'original-score.wav';music(soundtrack)
    arguments=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y']
    for path in scenes:arguments+=['-i',str(path)]
    arguments+=['-i',str(soundtrack)]
    filters=[];previous='0:v';offset=DURATIONS[0]-.4
    for index in range(1,len(scenes)):
        label='fade'+str(index)
        filters.append(f'[{previous}][{index}:v]xfade=transition=fade:duration=0.4:offset={offset:.2f}[{label}]')
        previous=label;offset+=DURATIONS[index]-.4
    filters.append('[6:a]afade=t=in:d=0.3,afade=t=out:st=28:d=2,loudnorm=I=-20:TP=-2:LRA=7[audio]')
    target=OUT/'memoh-bot-template-30s.mp4'
    run(arguments+['-filter_complex_threads','2','-filter_complex',';'.join(filters),'-map','['+previous+']','-map','[audio]',
                   '-t','30','-c:v','libx264','-preset','fast','-crf','19','-threads','4','-pix_fmt','yuv420p',
                   '-c:a','aac','-ar','48000','-b:a','160k','-movflags','+faststart',str(target)])
    run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-ss','1.8','-i',str(target),'-frames:v','1',str(OUT/'poster.png')])
    selection="select='eq(n,75)+eq(n,240)+eq(n,420)+eq(n,585)+eq(n,735)+eq(n,855)',scale=640:360,tile=3x2"
    run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(target),'-vf',selection,'-frames:v','1',str(OUT/'storyboard.png')])
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]))
    report={'duration_seconds':float(info['format']['duration']),'video':{k:info['streams'][0][k] for k in ['codec_name','width','height','r_frame_rate','pix_fmt']},
            'audio':{k:info['streams'][1][k] for k in ['codec_name','sample_rate','channels']},'assets':'2 built-in image_gen illustrations + actual UI screenshots',
            'music':'original procedural arpeggio','file_bytes':target.stat().st_size}
    (OUT/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
