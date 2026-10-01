import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from memoh_templates.api import APIError
from memoh_templates.apply import apply_template, restore
from memoh_templates.catalog import CONTRACT, load, render


class FakeMemoh:
    def __init__(self):
        self.profile={'display_name':'Default','avatar_url':'avatar.png','timezone':'UTC','is_active':True,'metadata':{'secret':'untouched'}}
        self.settings={'chat_runtime':'model','chat_model_id':'model-123','memory_provider_id':'memory-123','reasoning_effort':'medium','compaction_target_percent':None}
        self.file={'content':'original persona','revision':'rev-before'}
        self.channels={'secret':'channel-token'}
        self.history=['keep this message']
        self.calls=[]
        self.fail_write=False
        self.conflict=False

    def contract(self): return copy.deepcopy(CONTRACT)
    def request(self, method, path, data=None):
        self.calls.append((method,path,copy.deepcopy(data)))
        if path=='/models':return [{'id':'model-123','reasoning':{'supported':True,'can_disable':False,'efforts':['medium','high'],'default_effort':'medium'}}]
        route=urlsplit(path).path
        if route.endswith('/settings'):
            if method=='PUT':self.settings.update(data)
            return copy.deepcopy(self.settings)
        if route.endswith('/fs/read'):
            if self.file is None:raise APIError(404,'missing')
            return copy.deepcopy(self.file)
        if route.endswith('/fs/list'):return {'entries':[]}
        if route.endswith('/fs/delete'):self.file=None;return {}
        if route.endswith('/fs/write'):
            if self.fail_write:self.fail_write=False;raise APIError(500,'disk write failure')
            if self.conflict and 'expectedRevision' in data:
                self.file={'content':'concurrent user edit','revision':'rev-other'}
                raise APIError(409,'file changed')
            self.file={'content':data['content'],'revision':'rev-after'}
            return {'ok':True,'revision':'rev-after'}
        if method=='PUT':self.profile.update(data)
        result=copy.deepcopy(self.profile)
        if not result.get('avatar_url'):result.pop('avatar_url',None)
        return result


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client=FakeMemoh()
        self.template=load('frieren')

    def apply(self,**kwargs): return apply_template(self.client,self.template,'bot-123',backup_dir=self.tmp.name,**kwargs)

    def test_overwrites_defaults_preserving_ids_metadata_channels_and_history(self):
        result=self.apply()
        self.assertTrue(result['verified'])
        self.assertEqual(self.client.file['content'],render(self.template))
        self.assertEqual(self.client.profile['display_name'],self.template['name'])
        self.assertEqual(self.client.settings['chat_model_id'],'model-123')
        self.assertEqual(self.client.settings['memory_provider_id'],'memory-123')
        self.assertEqual(self.client.profile['metadata']['secret'],'untouched')
        self.assertEqual(self.client.channels['secret'],'channel-token')
        self.assertEqual(self.client.history,['keep this message'])
        backup=json.loads(Path(result['backup']).read_text())
        self.assertNotIn('secret',json.dumps(backup))
        self.assertEqual(Path(result['backup']).stat().st_mode&0o777,0o600)
        self.assertTrue(any(data and data.get('expectedRevision')=='rev-before' for method,path,data in self.client.calls))

    def test_dry_run_performs_no_writes_and_no_backup(self):
        result=self.apply(dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertTrue(all(method=='GET' for method,path,data in self.client.calls))
        self.assertEqual(list(Path(self.tmp.name).iterdir()),[])

    def test_write_failure_restores_original_persona_and_profile(self):
        self.client.fail_write=True
        with self.assertRaisesRegex(RuntimeError,'已恢复'):
            self.apply()
        self.assertEqual(self.client.profile['display_name'],'Default')
        self.assertEqual(self.client.file['content'],'original persona')
        self.assertEqual(self.client.settings['reasoning_effort'],'medium')

    def test_revision_conflict_preserves_concurrent_user_edit(self):
        self.client.conflict=True
        with self.assertRaises(RuntimeError):self.apply()
        self.assertEqual(self.client.file['content'],'concurrent user edit')
        self.assertEqual(self.client.profile['display_name'],'Default')

    def test_settings_failure_does_not_touch_persona_or_profile(self):
        request=self.client.request
        def fail(method,path,data=None):
            if method=='PUT' and path.endswith('/settings') and 'tool_approval_config' in data:
                self.client.file={'content':'new user edit','revision':'rev-new'}
                raise APIError(500,'settings failed')
            return request(method,path,data)
        self.client.request=fail
        with self.assertRaises(RuntimeError):self.apply()
        self.assertEqual(self.client.file['content'],'new user edit')
        self.assertFalse(any(method=='POST' or method=='PUT' and not path.endswith('/settings') for method,path,data in self.client.calls))

    def test_readback_failure_preserves_later_user_edit(self):
        request=self.client.request
        written=False
        def fail(method,path,data=None):
            nonlocal written
            response=request(method,path,data)
            if method=='POST' and path.endswith('/fs/write'):
                written=True
            elif written and method=='GET' and path.endswith('/settings'):
                written=False
                self.client.file={'content':'edit after apply','revision':'rev-new'}
                raise APIError(500,'readback failed')
            return response
        self.client.request=fail
        with self.assertRaises(RuntimeError):self.apply()
        self.assertEqual(self.client.file['content'],'edit after apply')
        self.assertEqual(self.client.profile['display_name'],'Default')

    def test_missing_original_file_can_be_created_and_restore_removes_it(self):
        self.client.file=None
        result=self.apply()
        state=json.loads(Path(result['backup']).read_text())
        self.assertIsNone(state['agents'])
        restore(self.client,state)
        self.assertIsNone(self.client.file)

    def test_restore_clears_optional_binding_added_during_apply(self):
        self.assertNotIn('compaction_model_id',self.client.settings)
        result=self.apply(bindings={'compaction_model_id':'new-compaction-model'})
        self.assertEqual(self.client.settings['compaction_model_id'],'new-compaction-model')
        restore(self.client,json.loads(Path(result['backup']).read_text()))
        self.assertEqual(self.client.settings['compaction_model_id'],'')

    def test_incompatible_server_and_bad_bindings_fail_before_mutation(self):
        contract=copy.deepcopy(CONTRACT)
        del contract['definitions']['settings.UpsertRequest']['properties']['tool_approval_config']
        self.client.contract=lambda:contract
        with self.assertRaisesRegex(ValueError,'不兼容'):self.apply()
        self.assertEqual(self.client.calls,[])
        with self.assertRaises(ValueError):self.apply(bindings={'compaction_enabled':'true'})

    def test_external_runtime_requires_explicit_choice(self):
        self.client.settings['chat_runtime']='codex'
        with self.assertRaisesRegex(ValueError,'外部 Agent'):self.apply()
        self.assertTrue(all(method=='GET' for method,path,data in self.client.calls))

    def test_reasoning_preference_adapts_to_actual_model_options(self):
        result=self.apply()
        self.assertEqual(self.client.settings['reasoning_effort'],'medium')
        self.assertTrue(result['warnings'])

    def test_invalid_render_parameter_does_not_connect(self):
        with self.assertRaises(ValueError):self.apply(parameters={'response_length':0})
        self.assertEqual(self.client.calls,[])
