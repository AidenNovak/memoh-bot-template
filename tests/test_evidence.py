import copy
import hashlib
import json
import unittest

from memoh_templates.evidence import ROOT, load_evidence, validate_record, validate_selection
from memoh_templates.catalog import load, render


class ConversationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = json.loads((ROOT / 'catalog/multiturn-cases.json').read_text())
        cls.baseline = json.loads((ROOT / 'verification/model-replies/multiturn.json').read_text())
        cls.raw = (ROOT / 'verification/model-replies/multiturn-followup.json').read_bytes()
        cls.followup = json.loads(cls.raw)
        cls.selection = json.loads((ROOT / 'promo/multiturn-selection.json').read_text())

    def test_published_sessions_have_complete_matching_receipts(self):
        self.assertEqual(len(validate_record(self.baseline, self.fixtures)), 12)
        self.assertEqual(len(validate_record(self.followup, self.fixtures)), 4)
        self.assertEqual(self.baseline['reply_count'], 96)
        self.assertEqual(len(load_evidence()[2]), 4)
        for case in self.followup['cases']:
            self.assertEqual(case['prompt_sha256'], hashlib.sha256(render(load(case['template'])).encode()).hexdigest())
        film = json.loads((ROOT / 'promo/multiturn-render-report.json').read_text())
        self.assertEqual(film['source_sha256'], self.selection['source_sha256'])
        self.assertEqual(film['sha256'], hashlib.sha256((ROOT / 'promo/memoh-bot-template-multiturn-120s.mp4').read_bytes()).hexdigest())
        self.assertAlmostEqual(film['duration_seconds'], 120, places=1)
        # Negative replies remain visible in the baseline instead of being hidden.
        leaked = [(c['id'], t['turn']) for c in self.baseline['cases']
                  for t in c['turns'] if 'DSML' in t['assistant']]
        self.assertEqual(leaked, [('frieren--deepseek-v4-flash', 5), ('anya-forger--deepseek-v4-flash', 8)])

    def test_receipts_reject_cross_session_unfinished_and_rewritten_turns(self):
        for field, value in [('session_sha256', 'a' * 64), ('runtime_completed', False),
                             ('assistant', '编造的模型回复'), ('persisted_assistant_turns', 1), ('turn', 1)]:
            with self.subTest(field=field):
                record = copy.deepcopy(self.followup)
                record['cases'][0]['turns'][1][field] = value
                with self.assertRaises(ValueError):
                    validate_record(record, self.fixtures)

    def test_film_quotes_reject_rewriting_skipped_turns_and_changed_source(self):
        for kind in ['rewritten', 'skipped', 'changed_source']:
            with self.subTest(kind=kind):
                selection = copy.deepcopy(self.selection)
                if kind == 'rewritten':
                    selection['chapters'][0]['excerpts'][0]['text'] += '编造'
                elif kind == 'skipped':
                    selection['chapters'][0]['excerpts'][0]['turn'] = 2
                else:
                    selection['source_sha256'] = '0' * 64
                with self.assertRaises(ValueError):
                    validate_selection(selection, self.followup, self.raw)

    def test_tool_markup_cannot_be_concealed_by_a_clean_prefix(self):
        record, selection = copy.deepcopy(self.followup), copy.deepcopy(self.selection)
        case_id = selection['chapters'][0]['case_id']
        case = next(c for c in record['cases'] if c['id'] == case_id)
        case['turns'][3]['assistant'] += '\n<DSML calls>内部工具标签</DSML>'
        raw = json.dumps(record, ensure_ascii=False).encode()
        selection['source_sha256'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):
            validate_selection(selection, record, raw)

    def test_native_ui_captures_match_conversations_and_image_bytes(self):
        ui = json.loads((ROOT / 'verification/multiturn-ui.json').read_text())
        self.assertTrue(ui['verified'])
        self.assertEqual(ui['messages_sent'], 0)
        index = {c['id']: c for c in self.followup['cases']}
        self.assertEqual({c['case_id'] for c in ui['cases']},
                         {c['case_id'] for c in self.selection['chapters']})
        for receipt in ui['cases']:
            self.assertTrue(receipt['rendered'])
            self.assertEqual(receipt['pairs'], 8)
            self.assertEqual(receipt['session_sha256'], index[receipt['case_id']]['turns'][0]['session_sha256'])
            self.assertEqual(receipt['screenshot_sha256'],
                             hashlib.sha256((ROOT / receipt['screenshot']).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
