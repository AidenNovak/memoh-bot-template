#!/usr/bin/env python3
"""Select traceable verbatim excerpts; never compose a fictional Bot reply."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from memoh_templates.evidence import validate_record, validate_selection

CASES = [('frieren--deepseek-v4-flash', '窗边陪伴', '改口之后，茶也跟着记住'),
         ('elon-musk--deepseek-v4-flash', '怪点子车间', '预算记住了，笑话接偏了一次'),
         ('anya-forger--k3', '悄悄话搭子', '换了目的地，还是接着聊'),
         ('trpg-gm--deepseek-v4-flash', '会走路的灯塔', '信还没送，饼干已经没了')]


def excerpt(text, limit=80):
    """Keep a contiguous source prefix, ending at a sentence when possible."""
    if len(text) <= limit:
        return 0, len(text)
    boundaries = [m.end() for m in re.finditer(r'[。！？!?](?:[”」』])?|\n\n', text[:limit])]
    end = max(boundaries, default=limit)
    return 0, end


def main():
    source = ROOT / 'verification/model-replies/multiturn-followup.json'
    raw = source.read_bytes()
    record = json.loads(raw)
    fixtures = json.loads((ROOT / 'catalog/multiturn-cases.json').read_text())
    index = validate_record(record, fixtures)
    selection = {'schema_version': 1, 'source': 'verification/model-replies/multiturn-followup.json',
                 'source_sha256': hashlib.sha256(raw).hexdigest(), 'duration_seconds': 120,
                 'method': 'Four different Bots; original user messages and verbatim contiguous reply excerpts; turns 4-7 remain in order; all eight turns are public.',
                 'chapters': []}
    for case_id, title, focus in CASES:
        case = index[case_id]
        chapter = {'case_id': case_id, 'title': title, 'focus': focus, 'excerpts': []}
        for turn in case['turns'][3:7]:
            start, end = excerpt(turn['assistant'])
            # Inventory is later in this long narrative reply. This is one
            # contiguous original paragraph/line, with full text in the record.
            if case_id == 'trpg-gm--deepseek-v4-flash' and turn['turn'] == 4:
                start = turn['assistant'].index('现在你手里是：')
                end = turn['assistant'].index('\n\n', start)
            elif case_id == 'trpg-gm--deepseek-v4-flash' and turn['turn'] == 7:
                start = turn['assistant'].index('- 身上还剩：')
                end = turn['assistant'].index('\n', start)
            chapter['excerpts'].append({'turn': turn['turn'], 'start': start, 'end': end,
                                       'text': turn['assistant'][start:end]})
        selection['chapters'].append(chapter)
    validate_selection(selection, record, raw)
    (ROOT / 'promo/multiturn-selection.json').write_text(json.dumps(selection, ensure_ascii=False, indent=2) + '\n')
    print('Selected 16 real reply excerpts from four consecutive-turn conversations')


if __name__ == '__main__':
    main()
