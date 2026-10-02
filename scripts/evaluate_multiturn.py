#!/usr/bin/env python3
"""Collect fixed eight-turn conversations through Memoh's native runtime.

Creates only its own disposable Bots. --retain-capture keeps four task-created
Bots temporarily for native Web screenshots; --cleanup removes those afterward.
Credentials and the capture registry remain on the evaluation server.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from memoh_templates.api import APIError, Client
from memoh_templates.apply import apply_template
from memoh_templates.catalog import load, render
from chat_transport import ChatConversation

CAPTURE = {('frieren', 'deepseek-v4-flash'), ('frieren', 'k3'), ('elon-musk', 'deepseek-v4-flash'),
           ('anya-forger', 'k3'), ('trpg-gm', 'deepseek-v4-flash')}


def write(path, value, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if private:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def delete(client, bot_id):
    client.request('DELETE', '/bots/' + bot_id)
    deadline = time.monotonic() + 30
    while True:
        if time.monotonic() > deadline:
            raise RuntimeError('Disposable Bot deletion did not finish')
        try:
            if not any(b['id'] == bot_id for b in client.request('GET', '/bots')['items']):
                return
        except APIError as exc:
            # Native list hydration can briefly fail while a workspace is being
            # removed. Retry only this read; never resend a mutation blindly.
            if exc.status != 500:
                raise
        time.sleep(.4)


def source_commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', default='deepseek-v4-flash,k3')
    parser.add_argument('--templates', default='')
    parser.add_argument('--pairs', default='', help='Optional comma-separated template--model pairs')
    parser.add_argument('--retain-capture', action='store_true')
    parser.add_argument('--retry-empty-cases', action='store_true')
    parser.add_argument('--source-note', default='Current checkout defaults; exact rendered prompt hashes recorded')
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--report', type=Path, default=ROOT / 'verification/model-replies/multiturn.json')
    parser.add_argument('--registry', type=Path, default=ROOT / '.backups/multiturn-capture.json')
    args = parser.parse_args()
    client = Client(os.environ.get('MEMOH_URL', 'http://127.0.0.1:12880'), os.environ.get('MEMOH_TOKEN', ''), timeout=240)
    if not client.token:
        client.login(os.environ.get('MEMOH_USERNAME', 'admin'), os.environ['MEMOH_PASSWORD'])
    if args.cleanup:
        registry = json.loads(args.registry.read_text())
        existing = {b['id']: b for b in client.request('GET', '/bots')['items']}
        for entry in registry:
            if entry['bot_id'] not in existing:
                continue
            if existing[entry['bot_id']]['name'] != entry['bot_name'] or not entry['bot_name'].startswith('multiturn-'):
                raise RuntimeError('Refusing to delete a Bot outside this evaluation')
            delete(client, entry['bot_id'])
        report = json.loads(args.report.read_text())
        report['cleanup'] = True
        report['retained_for_capture'] = 0
        write(args.report, report)
        write(args.registry, [], private=True)
        print('Evaluation Bots removed; existing demo Bots preserved')
        return
    if not args.retry_empty_cases and (args.report.exists() or args.registry.exists()):
        raise RuntimeError('Use a fresh report/registry path; previous evaluations are never overwritten')
    fixtures = json.loads((ROOT / 'catalog/multiturn-cases.json').read_text())
    cases = [c for c in fixtures['cases'] if not args.templates or c['template'] in args.templates.split(',')]
    configured = {m['model_id']: m for m in client.request('GET', '/models') if m.get('type') == 'chat' and m.get('enable', True)}
    models = [configured[name] for name in args.models.split(',')]
    planned = [c['template'] + '--' + m['model_id'] for m in models for c in cases
               if not args.pairs or c['template'] + '--' + m['model_id'] in args.pairs.split(',')]
    if not planned or args.pairs and set(planned) != set(args.pairs.split(',')):
        raise ValueError('Unknown or empty evaluation case selection')
    run = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    report = {'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'upstream_commit': '1bfb42154e09efacd34f68898ceaab78c10c85f3',
              'template_source_commit': source_commit(),
              'template_source_state': args.source_note,
              'fixtures_sha256': hashlib.sha256((ROOT / 'catalog/multiturn-cases.json').read_bytes()).hexdigest(),
              'transport': 'Memoh authenticated WebSocket; one explicit session; matching completed invocation; persisted user/assistant readback',
              'parameters': 'Unmodified template defaults; no reply length overrides',
              'turns_per_conversation': 8, 'cases': [], 'cleanup': False, 'retained_for_capture': 0}
    report['planned_cases'] = planned
    registry = []
    retry_index = {}
    if args.retry_empty_cases:
        report = json.loads(args.report.read_text())
        registry = json.loads(args.registry.read_text())
        retry_index = {c['id']: c for c in report['cases'] if c.get('error') and not c['turns'] and 'HTTP 500' in c['error']}
        if not retry_index:
            raise RuntimeError('No pre-chat HTTP 500 setup failures to retry')
    failures = []
    write(args.report, report)
    for model in models:
        for fixture in cases:
            slug = fixture['template']
            case_id = slug + '--' + model['model_id']
            if case_id not in planned:
                continue
            if args.retry_empty_cases and case_id not in retry_index:
                continue
            name = 'multiturn-' + run + '-' + slug + '-' + model['model_id']
            bot = client.request('POST', '/bots', {'name': name, 'wait_for_ready': True})
            bot_id = bot['id']
            entry = {'bot_id': bot_id, 'bot_name': name, 'template': slug, 'model_id': model['model_id']}
            registry.append(entry)
            write(args.registry, registry, private=True)
            case = {'id': case_id, 'template': slug, 'bot_name': name,
                    'model': model['name'], 'model_id': model['model_id'], 'focus': fixture['focus'],
                    'model_config': model.get('config', {}),
                    'parameters': {}, 'turns': [], 'session_verified': False}
            if case_id in retry_index:
                old = retry_index[case_id]
                case['setup_attempts'] = old.get('setup_attempts', []) + [{'error': old['error'], 'reply_count': 0}]
                report['cases'][report['cases'].index(old)] = case
            else:
                report['cases'].append(case)
            conversation = None
            succeeded = False
            try:
                template = load(slug)
                apply_template(client, template, bot_id, bindings={'chat_model_id': model['id']},
                    backup_dir=ROOT / '.backups/multiturn-eval',
                    customizations={'resource_limits': {'mode': 'apply', 'requests': [{'resource_limits':
                        {'cpu_millicores': 500, 'memory_bytes': 536870912, 'storage_bytes': 5368709120}}]}})
                case['prompt_sha256'] = hashlib.sha256(render(template).encode()).hexdigest()
                conversation = ChatConversation(client, bot_id)
                for text in fixture['turns']:
                    receipt = conversation.send(text)
                    for secret in [os.environ.get('MEMOH_PASSWORD', ''), client.token]:
                        if secret and secret in receipt['assistant']:
                            raise RuntimeError('Reply unexpectedly contained authentication material')
                    case['turns'].append(receipt)
                    write(args.report, report)
                    print(f"{model['name']} / {slug} / {receipt['turn']}/8 / {receipt['characters']} characters / session fixed", flush=True)
                case['session_verified'] = conversation.verify()
                case['literal_probe_indicators'] = []
                for probe in fixture['probes']:
                    text = case['turns'][probe['turn'] - 1]['assistant']
                    case['literal_probe_indicators'].append({
                        'turn': probe['turn'], 'label': probe['label'],
                        'mentions': {term: term in text for term in probe['must_mention']},
                        'forbidden_mentions': {term: term in text for term in probe['must_not_mention']},
                        'note': 'Substring indicators only; semantic judgment requires reading the full conversation'})
                succeeded = True
            except Exception as exc:
                case['error'] = type(exc).__name__ + ': ' + str(exc)
                failures.append(case['id'])
                print('Case failed: ' + case['id'] + ' (' + type(exc).__name__ + ')', flush=True)
            finally:
                if conversation:
                    conversation.close()
                if not (succeeded and args.retain_capture and (slug, model['model_id']) in CAPTURE):
                    delete(client, bot_id)
                    registry.remove(entry)
                write(args.registry, registry, private=True)
                report['retained_for_capture'] = len(registry)
                write(args.report, report)
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    report['successful_conversations'] = sum(c['session_verified'] for c in report['cases'])
    report['reply_count'] = sum(len(c['turns']) for c in report['cases'])
    report['cleanup'] = not registry
    write(args.report, report)
    print(f"Collected {report['reply_count']} persisted replies; {report['successful_conversations']} complete conversations", flush=True)
    if failures:
        raise RuntimeError('Incomplete cases retained in report: ' + ', '.join(failures))


if __name__ == '__main__':
    main()
