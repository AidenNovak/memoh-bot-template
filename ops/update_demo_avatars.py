#!/usr/bin/env python3
"""Update only the four evaluation demos' avatars, preserving chat/settings."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memoh_templates.api import Client
from memoh_templates.catalog import load
from deploy_eval import private_env


def main():
    client = Client('http://127.0.0.1:12880')
    client.login('admin', private_env('/opt/memoh-template-eval/eval.env')['MEMOH_ADMIN_PASSWORD'])
    wanted = {'template-demo-' + slug: slug for slug in ['frieren', 'elon-musk', 'anya-forger', 'trpg-gm']}
    bots = [bot for bot in client.request('GET', '/bots')['items'] if bot['name'] in wanted]
    if len(bots) != len(wanted):
        raise RuntimeError('Expected the four existing evaluation demos')
    backup = Path('/opt/memoh-template-eval/avatar-backups')
    backup.mkdir(mode=0o700, exist_ok=True)
    path = backup / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump([{'bot_id': b['id'], 'name': b['name'], 'avatar_url': b.get('avatar_url', '')} for b in bots], stream)
    for bot in bots:
        image = load(wanted[bot['name']])['profile']['avatar_url']
        client.request('PUT', '/bots/' + bot['id'], {'avatar_url': image})
        if client.request('GET', '/bots/' + bot['id'])['avatar_url'] != image:
            raise RuntimeError('Avatar readback differs')
        print('Updated avatar: ' + wanted[bot['name']])


if __name__ == '__main__':
    main()
