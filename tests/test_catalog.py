import hashlib
import io
import json
import tarfile
import unittest
import zipfile
from memoh_templates import catalog
from memoh_templates.bundle import bundle


class CatalogTests(unittest.TestCase):
    def test_every_template_covers_actual_settings_and_has_original_content(self):
        items = catalog.templates()
        self.assertEqual(len(items), 56)
        self.assertEqual(len({t['category'] for t in items}), 6)
        self.assertEqual(len({t['id'] for t in items}), 56)
        self.assertEqual(len({t['persona']['greeting'] for t in items}), 56)
        self.assertEqual(len({tuple(t['persona']['workflow']) for t in items}), 56)
        self.assertEqual(len({t['persona']['examples'][0]['assistant'] for t in items}), 56)
        for template in items:
            with self.subTest(template=template['id']):
                catalog.validate(template)
                for source in template['sources']:
                    self.assertTrue(source['url'].startswith('https://'))
                self.assertEqual((catalog.ROOT/'templates'/template['id']/'AGENTS.md').read_text(), catalog.render(template))

    def test_parameters_change_real_prompt_and_bad_parameters_fail(self):
        template = catalog.load('frieren')
        changed = catalog.render(template, {'user_name':'小林','journey_pace':'很慢','response_length':90})
        self.assertIn('小林', changed)
        self.assertIn('旅行节奏：很慢', changed)
        self.assertIn('每轮目标汉字数（软目标）：90', changed)
        for value in ({'unknown':1},{'response_length':1},{'response_length':'90'},{'language':'unknown'}):
            with self.assertRaises(ValueError): catalog.render(template,value)

    def test_inherit_never_leaks_into_native_payload(self):
        settings=catalog.resolved_settings(catalog.load('elon-musk'))
        self.assertNotIn('chat_model_id',settings)
        self.assertNotIn('display_enabled',settings)
        self.assertIn('compaction_threshold',settings)
        with self.assertRaises(ValueError): catalog.resolved_settings(catalog.load('elon-musk'), {'secret':'x'})

    def test_zero_intensity_really_removes_role_identity_and_examples(self):
        template=catalog.load('frieren')
        for parameters in [{'roleplay_intensity':0},{'interaction_mode':'退出角色'}]:
            prompt=catalog.render(template,parameters)
            self.assertNotIn(template['persona']['identity'],prompt)
            self.assertNotIn(template['persona']['greeting'],prompt)
            self.assertIn('当前已退出角色演绎',prompt)

    def test_bundles_checksums_profile_and_workspace(self):
        for template in catalog.templates():
            with self.subTest(template=template['id']):
                raw=bundle(template)
                self.assertEqual(raw,bundle(template))
                committed=(catalog.ROOT/'templates'/template['id']/(template['id']+'.memoh.zip')).read_bytes()
                self.assertEqual(raw,committed)
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    self.assertEqual(set(archive.namelist()),{'manifest.json','bot/profile.json','bot/settings.json','workspace/data.tar.gz'})
                    manifest=json.loads(archive.read('manifest.json'))
                    self.assertEqual(manifest['schema_version'],1)
                    for path,digest in manifest['checksums'].items():
                        self.assertEqual(hashlib.sha256(archive.read(path)).hexdigest(),digest)
                    profile=json.loads(archive.read('bot/profile.json'))
                    self.assertEqual(profile['display_name'],template['name'])
                    with tarfile.open(fileobj=io.BytesIO(archive.read('workspace/data.tar.gz')),mode='r:gz') as tar:
                        self.assertEqual(tar.getnames(),['AGENTS.md','.memoh/template/customization.json'])
                        self.assertEqual(json.load(tar.extractfile('.memoh/template/customization.json')),template['customization'])
                        self.assertEqual(tar.extractfile('AGENTS.md').read().decode(),catalog.render(template))

    def test_slug_cannot_read_arbitrary_files(self):
        for slug in ('../README','/tmp/test','UPPER','foo%2fbar'):
            with self.assertRaises(ValueError): catalog.load(slug)

    def test_nested_approval_settings_reject_invalid_types_and_modes(self):
        for config in ('invalid',{'enabled':'true'},{'exec':{'mode':'maybe'}},{'write':{'bypass_globs':[3]}}):
            with self.assertRaises(ValueError):
                catalog.resolved_settings(catalog.load('frieren'), {'tool_approval_config':config})
