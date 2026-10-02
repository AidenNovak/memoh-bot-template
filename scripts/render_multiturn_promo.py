#!/usr/bin/env python3
"""Render a 1080p, two-minute film from verified, verbatim multi-turn chats.

Python standard library, FFmpeg/librsvg and WenQuanYi fonts only.
Encoding/rasterization belong on the limited Linux build host.
"""
import argparse
import base64
import hashlib
import html
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from memoh_templates.catalog import load
from memoh_templates.evidence import load_evidence
from render_promo import music

OUT = ROOT / 'promo'
WORK = OUT / '.render-multiturn'
WIDTH, HEIGHT, FPS = 1920, 1080, 30
PAPER, INK, GREEN, MUTED = '#f5f4ed', '#1e352c', '#537960', '#6d7e70'
COLORS = ['#dfeadb', '#e8e3d5', '#eae0eb', '#dee7e4']


def run(args):
    subprocess.run(args, check=True)


def wrap(text, columns):
    """CJK occupies one column; Latin uses a conservative fractional width."""
    lines = []
    for paragraph in text.replace('**', '').split('\n'):
        current, width = '', 0
        for char in paragraph:
            units = 1 if unicodedata.east_asian_width(char) in 'WF' else .62
            # Keep Chinese closing punctuation with the preceding phrase.
            if current and width + units > columns and char not in '，。！？：；、）】》”’」』,.!?;:)':
                lines.append(current)
                current, width = '', 0
            current += char
            width += units
        if current:
            lines.append(current)
    return lines


def short_quote(text, limit=55):
    """Only shorten a source prefix; the film labels these cards as excerpts."""
    if len(text) <= limit:
        return text
    boundaries = [m.end() for m in re.finditer(r'[。！？!?]', text[:limit])]
    return text[:max(boundaries, default=limit)]


class Canvas:
    def __init__(self):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
                      '<style>text{font-family:"WenQuanYi Zen Hei",sans-serif;font-weight:400}</style>']
        self.counter = 0
        self.text_blocks = []
        self.rect(0, 0, WIDTH, HEIGHT, PAPER)

    def rect(self, x, y, width, height, fill, radius=0, opacity=1):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" opacity="{opacity}"/>')

    def image(self, path, x, y, width, height, radius=0, opacity=1):
        self.counter += 1
        clip = 'clip' + str(self.counter)
        self.parts.append(f'<defs><clipPath id="{clip}"><rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}"/></clipPath></defs>')
        mime = 'image/jpeg' if str(path).endswith('.jpg') else 'image/png'
        uri = 'data:' + mime + ';base64,' + base64.b64encode(Path(path).read_bytes()).decode()
        self.parts.append(f'<image x="{x}" y="{y}" width="{width}" height="{height}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip})" opacity="{opacity}" xlink:href="{uri}"/>')

    def text(self, text, x, y, size=32, color=INK, columns=None, line_height=None, opacity=1):
        lines = wrap(text, columns) if columns else text.replace('**', '').split('\n')
        line_height = line_height or size * 1.36
        if y + len(lines) * line_height > HEIGHT - 8 or x < 0:
            raise ValueError('Text leaves the video canvas: ' + text[:30])
        self.text_blocks.append({'text': text, 'x': x, 'y': y, 'font_size': size, 'lines': len(lines)})
        spans = ''.join(f'<tspan x="{x}" y="{y + size + n * line_height}">{html.escape(line)}</tspan>' for n, line in enumerate(lines))
        self.parts.append(f'<text fill="{color}" font-size="{size}" opacity="{opacity}">{spans}</text>')
        return len(lines) * line_height

    def header(self, label):
        self.text('MEMOH / BOT TEMPLATE', 76, 45, 23, GREEN)
        self.text(label, 1278, 45, 23, MUTED)
        self.rect(76, 1003, 1768, 2, '#d3decd')
        self.text('真实回复节选 · 轮次保持原序 · 等待时间已压缩', 76, 1020, 21, MUTED)
        self.text('完整记录：GitHub / AidenNovak / memoh-bot-template', 1040, 1020, 21, MUTED)

    def save(self, name):
        svg, png = WORK / (name + '.svg'), WORK / (name + '.png')
        svg.write_text(''.join(self.parts) + '</svg>')
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-threads', '1',
             '-i', str(svg), '-frames:v', '1', str(png)])
        return png


def reply(canvas, turn, y, tint, previous=False):
    opacity = .70 if previous else 1
    label = f"第 {turn['turn']} 轮 / 8" + (' · 前一句' if previous else ' · 接着聊')
    canvas.text(label, 540, y, 23, GREEN, opacity=opacity)
    user_lines = wrap(turn['user'], 39)
    user_height = len(user_lines) * 38 + 30
    canvas.rect(665, y + 40, 1135, user_height, tint, 18, opacity=opacity)
    canvas.text(turn['user'], 695, y + 54, 28, columns=39, line_height=38, opacity=opacity)
    answer_y = y + 40 + user_height + 17
    answer_lines = wrap(turn['excerpt'], 32)
    answer_height = len(answer_lines) * 46 + 49
    canvas.rect(530, answer_y, 1270, answer_height, '#ffffff', 18, opacity=opacity)
    canvas.text('Bot' + (' · 节选' if turn['is_excerpt'] else ' · 完整回复'), 554, answer_y + 9, 18, MUTED, opacity=opacity)
    canvas.text(turn['excerpt'], 570, answer_y + 40, 35, columns=32, line_height=46, opacity=opacity)
    if answer_y + answer_height > y + 396:
        raise ValueError('Chat pair exceeds its display row; choose a shorter contiguous excerpt')


def chapter_frame(item, stage, number):
    case, chapter, turns = item['case'], item['chapter'], item['turns']
    template = load(case['template'])
    canvas = Canvas()
    canvas.header(f"{number:02d} / 04 · 同一会话，连续聊到第 8 轮")
    canvas.rect(62, 137, 398, 833, COLORS[number - 1], 24)
    canvas.image(ROOT / template['avatar']['path'], 158, 172, 206, 206, radius=103)
    canvas.text(template['name'].split(' · ')[0], 94, 409, 43, columns=8.5, line_height=56)
    canvas.text(chapter['title'], 94, 479, 25, GREEN)
    canvas.text(case['model'], 94, 524, 24, columns=13)
    canvas.text('开场 · 第1轮用户原文', 94, 594, 21, MUTED)
    context_height = canvas.text(case['turns'][0]['user'], 94, 635, 21, columns=15.8, line_height=28)
    if 635 + context_height > 823:
        raise ValueError('Opening context overlaps native UI proof')
    screenshot = ROOT / 'verification/multiturn-ui' / (case['id'] + '.png')
    canvas.image(screenshot, 94, 839, 334, 90, radius=10)
    canvas.text('Memoh 原生界面 · 同一段对话', 94, 937, 16, MUTED)
    canvas.text(chapter['focus'], 530, 132, 42)
    if stage:
        reply(canvas, turns[stage - 1], 206, COLORS[number - 1], previous=True)
        reply(canvas, turns[stage], 604, COLORS[number - 1])
    else:
        reply(canvas, turns[0], 206, COLORS[number - 1])
        canvas.text('继续聊下去，看它怎么接住改口和新话题。', 570, 740, 30, MUTED)
    return canvas


def intro(chapters):
    canvas = Canvas()
    canvas.image(OUT / 'assets/hero.png', 0, 0, WIDTH, HEIGHT)
    canvas.rect(0, 0, WIDTH, HEIGHT, PAPER, opacity=.70)
    canvas.header('多轮真实回复 / 02:00')
    canvas.text('这次，\n继续聊下去。', 82, 262, 84, line_height=108)
    canvas.text('4 个 Bot，4 段真实连续对话。', 86, 530, 34, GREEN)
    canvas.text('不只看第一句，\n也看改口以后、换话题以后。', 86, 602, 29, MUTED, line_height=48)
    for i, item in enumerate(chapters):
        case = item['case']
        t = load(case['template'])
        x, y = 958 + i % 2 * 438, 187 + i // 2 * 360
        canvas.rect(x, y, 406, 329, '#ffffff', 24, .92)
        canvas.image(ROOT / t['avatar']['path'], x + 24, y + 24, 74, 74, 37)
        canvas.text(t['name'].split(' · ')[0], x + 119, y + 40, 29)
        quote = short_quote(item['turns'][-1]['excerpt'])
        canvas.text(quote, x + 25, y + 127, 24, columns=14.5, line_height=34)
        canvas.text('第7轮节选 · ' + case['model'], x + 25, y + 285, 17, MUTED)
    return canvas


def overview(chapters, record):
    canvas = Canvas()
    canvas.header('第7轮 · 把前面的细节接回来')
    canvas.text('改口之后，还能接住哪些细节？', 80, 138, 62)
    canvas.text('下面是这四段对话第7轮的实际回答，完整上下文已公开。', 84, 235, 28, MUTED)
    for i, item in enumerate(chapters):
        x, y = 78 + i % 2 * 895, 320 + i // 2 * 315
        case = item['case']
        t = load(case['template'])
        canvas.rect(x, y, 862, 285, '#ffffff', 20)
        canvas.image(ROOT / t['avatar']['path'], x + 24, y + 24, 72, 72, 36)
        canvas.text(t['name'].split(' · ')[0], x + 117, y + 29, 31)
        canvas.text(case['model'], x + 117, y + 73, 21, MUTED)
        canvas.text(item['turns'][-1]['excerpt'], x + 28, y + 119, 27, columns=29, line_height=36)
    canvas.text('实测覆盖 6 个 Bot × 2 个模型 × 8 轮；修订后再复测视频中的 4 段。', 80, 961, 24, GREEN)
    return canvas


def closing():
    canvas = Canvas()
    canvas.image(OUT / 'assets/closing.png', 0, 0, WIDTH, HEIGHT)
    canvas.rect(0, 0, 1120, HEIGHT, PAPER, opacity=.83)
    canvas.header('从一句话开始，继续聊下去')
    canvas.text('选一个角色，\n聊聊你的下一句。', 87, 267, 76, line_height=104)
    canvas.text('56 个模板 · 原生导入 · 一键覆盖', 94, 535, 31, GREEN)
    canvas.text('性格、口吻、记忆约定与玩法，都可以自己改。', 94, 604, 27, MUTED)
    canvas.rect(77, 715, 840, 135, '#ffffff', 20, .94)
    canvas.text('GitHub / AidenNovak', 108, 740, 26, GREEN)
    canvas.text('memoh-bot-template', 108, 782, 43)
    canvas.text('角色为模板演绎，非本人或官方服务。', 92, 934, 22, MUTED)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-only', action='store_true')
    args = parser.parse_args()
    record, selection, chapters = load_evidence()
    WORK.mkdir(parents=True, exist_ok=True)
    frames = [(intro(chapters), '00-intro', 6.25)]
    for i, item in enumerate(chapters, 1):
        for stage in range(4):
            frames.append((chapter_frame(item, stage, i), f'{i:02d}-turn-{stage + 4}', 6.25))
    frames += [(overview(chapters, record), '05-overview', 10.25), (closing(), '06-closing', 8)]
    images = [canvas.save(name) for canvas, name, _ in frames]
    layout = {'width': WIDTH, 'height': HEIGHT, 'frames': [{'name': name, 'text_blocks': canvas.text_blocks} for canvas, name, _ in frames]}
    (WORK / 'layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
    if args.preview_only:
        print('Rendered 19 full-resolution preview frames; source excerpts verified')
        return
    clips = []
    for (canvas, name, duration), image in zip(frames, images):
        clip = WORK / (name + '.mp4')
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-threads', '1',
             '-loop', '1', '-framerate', str(FPS), '-i', str(image), '-t', str(duration), '-an',
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-threads', '4', '-pix_fmt', 'yuv420p', str(clip)])
        clips.append(clip)
        print('Encoded ' + name, flush=True)
    soundtrack = WORK / 'original-score.wav'
    music(soundtrack, duration=120)
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y']
    for clip in clips:
        command += ['-threads', '1', '-i', str(clip)]
    command += ['-i', str(soundtrack)]
    filters, previous, offset = [], '0:v', frames[0][2] - .25
    for i in range(1, len(clips)):
        label = 'fade' + str(i)
        filters.append(f'[{previous}][{i}:v]xfade=transition=fade:duration=0.25:offset={offset:.2f}[{label}]')
        previous = label
        offset += frames[i][2] - .25
    filters.append(f'[{len(clips)}:a]afade=t=in:d=0.5,afade=t=out:st=117:d=3,loudnorm=I=-22:TP=-2:LRA=7[audio]')
    target = OUT / 'memoh-bot-template-multiturn-120s.mp4'
    run(command + ['-filter_complex_threads', '2', '-filter_complex', ';'.join(filters), '-map', '[' + previous + ']',
                   '-map', '[audio]', '-t', '120', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-threads', '4',
                   '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-b:a', '160k', '-movflags', '+faststart', str(target)])
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-ss', '103.5', '-i', str(target),
         '-frames:v', '1', str(OUT / 'multiturn-poster.png')])
    moments = [90, 540, 1260, 1980, 2700, 3150]
    choice = "select='" + '+'.join('eq(n,' + str(n) + ')' for n in moments) + "',scale=640:360,tile=3x2"
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', str(target), '-vf', choice,
         '-frames:v', '1', str(OUT / 'multiturn-storyboard.png')])
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(target)]))
    report = {'duration_seconds': float(info['format']['duration']), 'video': {k: info['streams'][0][k] for k in ['codec_name', 'width', 'height', 'r_frame_rate', 'pix_fmt']},
              'audio': {k: info['streams'][1][k] for k in ['codec_name', 'sample_rate', 'channels']},
              'file_bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'source_sha256': selection['source_sha256'], 'bots_shown': 4, 'consecutive_turns_per_bot': [4, 5, 6, 7],
              'reply_excerpts': 16, 'conversation_screen_seconds': 96, 'excerpt_fonts_px': 35,
              'editing': 'Verbatim persisted replies; contiguous excerpts; original turn order; waiting time compressed',
              'illustrations': 'Existing built-in image_gen hero/closing and attributed Bot avatars',
              'music': 'Original procedural arpeggio; no synthetic character voices'}
    (OUT / 'multiturn-render-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
