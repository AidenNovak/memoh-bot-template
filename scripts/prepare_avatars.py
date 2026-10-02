#!/usr/bin/env python3
"""Fetch selected portraits and prepare small, self-contained Bot avatars.

Maintenance command only: requires FFmpeg/FFprobe, runs on the Linux build host.
Runtime and catalog generation continue to use Python's standard library alone.
Generated originals must already be in --source-dir as <template-id>.image.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, path):
    for attempt in range(4):
        try:
            request = Request(url, headers={'User-Agent': 'MemohBotTemplate/1.1 (https://github.com/AidenNovak/memoh-bot-template)'})
            with urlopen(request, timeout=45) as response:
                raw = response.read(15 * 1024 * 1024)
                if not response.headers.get('Content-Type', '').startswith('image/'):
                    raise ValueError('Expected image content: ' + url)
            path.write_bytes(raw)
            return
        except (HTTPError, URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(min(6, 1 + attempt * 2))


def prepare(source, target, crop):
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(source)]))['streams'][0]
    width, height = info['width'], info['height']
    size = int(min(width, height) / crop.get('zoom', 1))
    x = int(max(0, min(width - size, width * crop.get('x', .5) - size / 2)))
    y = int(max(0, min(height - size, height * crop.get('y', .5) - size / 2)))
    filters = f'color=c=0xf3f5f0:s=384x384:r=1[bg];[0:v]crop={size}:{size}:{x}:{y},scale=384:384:flags=lanczos[fg];[bg][fg]overlay=shortest=1,format=yuvj420p[out]'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-threads', '1', '-i', str(source),
                    '-filter_complex_threads', '1', '-filter_complex', filters, '-map', '[out]', '-frames:v', '1',
                    '-c:v', 'mjpeg', '-threads', '1', '-q:v', '3', str(target)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'assets/avatars/.source')
    parser.add_argument('--only', nargs='*')
    args = parser.parse_args()
    records_path = ROOT / 'catalog/avatars.json'
    records = json.loads(records_path.read_text())
    args.source_dir.mkdir(parents=True, exist_ok=True)
    for slug, record in records.items():
        if args.only and slug not in args.only:
            continue
        source = args.source_dir / (slug + '.image')
        target = ROOT / record['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            if record['kind'] == 'generated-original':
                raise RuntimeError('Upload the generated source first: ' + slug)
            fetch(record['source_url'], source)
        prepare(source, target, record['crop'])
        record['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        record['bytes'] = target.stat().st_size
        record['width'] = record['height'] = 384
        records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
        print('Prepared ' + slug, flush=True)


if __name__ == '__main__':
    main()
