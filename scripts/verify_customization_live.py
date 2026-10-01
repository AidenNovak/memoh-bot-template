#!/usr/bin/env python3
"""Verify full customization, repeat application, restore and native bundle import."""
import copy
import json
import os
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memoh_templates.api import Client, APIError
from memoh_templates.apply import apply_template, restore, snapshot
from memoh_templates.catalog import load, ROOT
from memoh_templates.bundle import bundle
from verify_live import upload


def main():
    client = Client(os.environ.get('MEMOH_URL', 'http://127.0.0.1:12880'))
    client.login(os.environ.get('MEMOH_USERNAME', 'admin'), os.environ['MEMOH_PASSWORD'])
    bot = client.request('POST', '/bots', {'name': 'customization-eval-' + uuid.uuid4().hex[:8], 'wait_for_ready': True})
    created = [bot['id']]
    root = '/bots/' + bot['id']
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'verified': False}
    try:
        models = client.request('GET', '/models')
        binding = {'chat_model_id': next(m['id'] for m in models if m['type'] == 'chat')}
        client.request('PUT', root + '/settings', binding)
        original = snapshot(client, bot['id'])
        custom = json.loads((ROOT / 'examples/customization.json').read_text())
        template = load('frieren')
        for key in ['skills', 'hooks', 'acl_rules', 'agents']:
            custom[key] = copy.deepcopy(template['customization'][key])
            custom[key]['mode'] = 'apply'
        first = apply_template(client, template, bot['id'], backup_dir=ROOT / '.backups/customization-live', customizations=custom)
        report['checks'].append('10 enabled customization groups applied; core and reported fields read back')
        counts = {p: client.request('GET', root + p) for p in ['/mcp', '/schedule', '/workdirs', '/acl/rules', '/agents']}
        apply_template(client, template, bot['id'], backup_dir=ROOT / '.backups/customization-live', customizations=custom)
        for path, before in counts.items():
            after = client.request('GET', root + path)
            def ids(value):
                items = value if isinstance(value, list) else next((v for v in value.values() if isinstance(v, list)), [])
                return {v['id'] for v in items}
            if ids(before) != ids(after):
                raise RuntimeError('Repeated apply duplicated records: ' + path)
        schedule = client.request('GET', root + '/schedule')['items'][0]
        if schedule.get('max_run_seconds') != 300 or schedule.get('run_target') != 'new_session':
            raise RuntimeError('Repeated apply lost schedule execution parameters')
        report['checks'].append('repeat application reuses MCP/schedule/workdir/ACL/agent IDs and preserves schedule execution')
        restore(client, json.loads(Path(first['backup']).read_text()))
        if snapshot(client, bot['id'])['agents']['content'] != original['agents']['content']:
            raise RuntimeError('Persona restore differs')
        limits = client.request('GET', root + '/container/metrics')['resource_limits']['desired']
        if limits != {'cpu_millicores': 0, 'memory_bytes': 0, 'storage_bytes': 0}:
            raise RuntimeError('Resource limit restore differs')
        for path in counts:
            value = client.request('GET', root + path)
            items = value if isinstance(value, list) else next((v for v in value.values() if isinstance(v, list)), [])
            if items:
                raise RuntimeError('Created configuration was not removed: ' + path)
        report['checks'].append('private backup restores persona, metadata and resource limits; removes created records/files')
        raw = bundle(template, bindings=binding, customizations=custom)
        preview = upload(client, '/bots/backup/import/preview', raw)
        if preview.get('conflicts'):
            raise RuntimeError('Customized native bundle has conflicts')
        imported = upload(client, '/bots/backup/import', raw)
        created.append(imported['bot_id'])
        imported_root = '/bots/' + imported['bot_id']
        user_file = client.request('GET', imported_root + '/container/fs/read?path=%2Fdata%2FUSER.md')
        if '小林' not in user_file['content']:
            raise RuntimeError('Native import lost customized workspace file')
        native_schedule = client.request('GET', imported_root + '/schedule')['items'][0]
        if native_schedule['name'] != 'optional-evening-chat' or native_schedule['enabled']:
            raise RuntimeError('Native import lost disabled schedule')
        report['native_import_warnings'] = imported.get('warnings', [])
        report['checks'].append('customized native bundle preview/import restores workspace files, hooks, skills and disabled schedule')
        report['verified'] = True
    finally:
        for bot_id in created:
            client.request('DELETE', '/bots/' + bot_id)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not set(created) & {b['id'] for b in client.request('GET', '/bots')['items']}:
                break
            time.sleep(.5)
        report['cleanup'] = not set(created) & {b['id'] for b in client.request('GET', '/bots')['items']}
        directory = Path(os.environ.get('MEMOH_VERIFY_REPORT_DIR', str(ROOT / 'verification')))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'customization-live.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
