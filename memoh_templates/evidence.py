"""Check that published conversations and film excerpts retain their sources."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def validate_record(record, fixtures, capture_pending=False):
    fixture_bytes = (ROOT / 'catalog/multiturn-cases.json').read_bytes()
    if record.get('fixtures_sha256') != hashlib.sha256(fixture_bytes).hexdigest():
        raise ValueError('Conversation fixtures differ from the recorded experiment')
    if not record.get('cleanup') and not capture_pending:
        raise ValueError('Disposable evaluation Bots have not been cleaned up')
    cases = record['cases']
    specs = {c['template']: c for c in fixtures['cases']}
    full = {slug + '--' + model for slug in specs for model in ['deepseek-v4-flash', 'k3']}
    expected = set(record.get('planned_cases', full))
    if not expected or not expected <= full or {c['id'] for c in cases} != expected or len(cases) != len(expected):
        raise ValueError('Conversation coverage differs from the planned experiment')
    index = {}
    for case in cases:
        if case.get('error') or not case.get('session_verified') or case.get('parameters') != {}:
            raise ValueError('Incomplete or non-default conversation: ' + case['id'])
        turns = case['turns']
        if len(turns) != 8 or [t['user'] for t in turns] != specs[case['template']]['turns']:
            raise ValueError('Conversation is not the fixed eight-turn sequence')
        session = turns[0]['session_sha256']
        if not re.fullmatch(r'[a-f0-9]{64}', session):
            raise ValueError('Invalid session receipt')
        for number, turn in enumerate(turns, 1):
            if turn['turn'] != number or turn['persisted_user_turns'] != number or turn['persisted_assistant_turns'] != number:
                raise ValueError('Missing, repeated or reordered conversation turn')
            if turn['session_sha256'] != session or turn['runtime_completed'] is not True:
                raise ValueError('Conversation switched session or contains an unfinished reply')
            if digest(turn['user']) != turn['user_sha256'] or digest(turn['assistant']) != turn['assistant_sha256']:
                raise ValueError('Published text differs from its persisted receipt')
            if not turn['assistant'] or turn['characters'] != len(turn['assistant']):
                raise ValueError('Empty or inconsistent reply')
        if case['id'] in index:
            raise ValueError('Duplicate conversation ID')
        index[case['id']] = case
    if record.get('reply_count') != len(expected) * 8 or record.get('successful_conversations') != len(expected):
        raise ValueError('Conversation totals differ from the actual records')
    return index


def validate_selection(selection, record, raw_record):
    if selection.get('source_sha256') != hashlib.sha256(raw_record).hexdigest():
        raise ValueError('Film selection refers to a different source record')
    index = {c['id']: c for c in record['cases']}
    chapters = selection['chapters']
    if len(chapters) != 4 or len({c['case_id'] for c in chapters}) != 4:
        raise ValueError('Expected four different Bot conversations in the film')
    materialized = []
    for chapter in chapters:
        case = index[chapter['case_id']]
        numbers = [e['turn'] for e in chapter['excerpts']]
        if numbers != [4, 5, 6, 7]:
            raise ValueError('Film chapter must preserve four consecutive turns, 4 through 7')
        excerpts = []
        for excerpt in chapter['excerpts']:
            turn = case['turns'][excerpt['turn'] - 1]
            if 'DSML' in turn['assistant'] or '<tool_call' in turn['assistant']:
                raise ValueError('A raw tool protocol response cannot be presented as a clean chat excerpt')
            start, end = excerpt['start'], excerpt['end']
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(turn['assistant']):
                raise ValueError('Invalid source excerpt range')
            text = turn['assistant'][start:end]
            if text != excerpt['text']:
                raise ValueError('Film excerpt rewrites the real model output')
            excerpts.append({**turn, 'excerpt': text, 'is_excerpt': start != 0 or end != len(turn['assistant'])})
        materialized.append({'case': case, 'chapter': chapter, 'turns': excerpts})
    return materialized


def load_evidence():
    path = ROOT / 'verification/model-replies/multiturn-followup.json'
    raw = path.read_bytes()
    record = json.loads(raw)
    fixtures = json.loads((ROOT / 'catalog/multiturn-cases.json').read_text())
    validate_record(record, fixtures)
    selection = json.loads((ROOT / 'promo/multiturn-selection.json').read_text())
    chapters = validate_selection(selection, record, raw)
    return record, selection, chapters
