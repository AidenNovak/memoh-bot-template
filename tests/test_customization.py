import copy
import io
import json
import os
import tarfile
import unittest
import zipfile
from unittest.mock import patch
from memoh_templates import catalog
from memoh_templates.bundle import bundle
from memoh_templates.customization import CONFIG, plan, safe_plan, snapshot_actions, execute, undo, schema_for


class CustomizationTests(unittest.TestCase):
    def setUp(self):
        self.template = catalog.load('frieren')
        self.contract = copy.deepcopy(catalog.CONTRACT)
        for surface in CONFIG['surfaces'].values():
            self.contract['paths'].setdefault(surface['path'], {})[surface['method'].lower()] = {}

    def test_every_template_has_every_pinned_configuration_surface(self):
        for template in catalog.templates():
            self.assertEqual(set(template['customization']), set(CONFIG['surfaces']) | {'hooks', 'connector_bindings', 'model_sampling'})
            self.assertEqual(plan(template, {}, 'bot', self.contract), [])
            self.assertEqual(len(template['parameters']), 13)
            for key, surface in CONFIG['surfaces'].items():
                properties = schema_for(surface['schema']).get('properties', {})
                for request in template['customization'][key]['requests']:
                    self.assertEqual(set(request) - set(properties), set(), key)
        for platform in ['telegram', 'discord', 'feishu', 'qq', 'weixin', 'web']:
            self.assertIn('channel_' + platform, self.template['customization'])

    def test_missing_credentials_fail_before_any_requests_and_preview_hides_values(self):
        overrides = {'mcp': {'mode': 'apply', 'requests': [{'name': 'demo', 'transport': 'streamable-http', 'url': 'https://example.invalid/mcp', 'headers': {'Authorization': {'env': 'TEST_MCP_TOKEN'}}}]}}
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'TEST_MCP_TOKEN'):
                plan(self.template, overrides, 'bot', self.contract)
        with patch.dict(os.environ, {'TEST_MCP_TOKEN': 'private-placeholder'}):
            actions = plan(self.template, overrides, 'bot', self.contract)
        self.assertEqual(actions[0]['body']['headers']['Authorization'], 'private-placeholder')
        self.assertNotIn('private-placeholder', json.dumps(safe_plan(actions)))

    def test_path_escape_and_disguised_persona_write_are_rejected(self):
        for path in ['/etc/passwd', '/data/../tmp/foo', '/data/x/../AGENTS.md']:
            with self.assertRaises(ValueError):
                plan(self.template, {'workspace_files': {'mode': 'apply', 'requests': [{'path': path, 'content': 'x'}]}}, 'bot', self.contract)

    def test_unknown_body_fields_and_reference_only_actions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '未知字段'):
            plan(self.template, {'profile': {'mode': 'apply', 'requests': [{'system_secret': 'x'}]}}, 'bot', self.contract)
        for key in ['container_creation', 'app_connector_oauth', 'model_sampling', 'acp_runtime']:
            with self.assertRaises(ValueError):
                plan(self.template, {key: {'mode': 'apply', 'requests': [{}]}}, 'bot', self.contract)

    def test_disabled_schedule_is_idempotent_and_keeps_execution_options(self):
        body = {'name': 'same', 'pattern': '0 21 * * *', 'command': 'hello', 'enabled': False, 'max_calls': 7,
                'max_run_seconds': 300, 'run_target': 'new_session', 'reasoning_effort': 'medium'}
        original = {**body, 'id': 'existing', 'max_run_seconds': 600}
        class Client:
            def request(self, method, path, data=None):
                return {'items': [original]}
        actions = plan(self.template, {'schedules': {'mode': 'apply', 'requests': [body]}}, 'bot', self.contract)
        state = snapshot_actions(Client(), actions)[0]
        self.assertEqual(state['action']['method'], 'PUT')
        self.assertTrue(state['action']['path'].endswith('/existing'))
        self.assertEqual(state['action']['body']['execution']['max_run_seconds'], 300)
        self.assertEqual(state['before']['max_run_seconds'], 600)

    def test_readback_mismatch_is_detected_after_receipt_is_saved(self):
        class Client:
            def request(self, method, path, data=None):
                return {'display_name': 'wrong'}
        action = {'section': 'profile', 'method': 'PUT', 'path': '/bots/bot', 'body': {'display_name': 'right'}}
        states = [{'action': action, 'before': {'display_name': 'old'}, 'read_path': '/bots/bot'}]
        recorded = []
        with self.assertRaisesRegex(ValueError, '回读不一致'):
            execute(Client(), states, lambda receipts: recorded.append(copy.deepcopy(receipts)))
        self.assertEqual(recorded[0][0]['section'], 'profile')

    def test_undo_restores_desired_limits_not_metrics_payload(self):
        calls = []
        class Client:
            def request(self, method, path, data=None): calls.append((method, path, data)); return {}
        old = {'cpu_millicores': 0, 'memory_bytes': 0, 'storage_bytes': 0}
        states = [{'action': {'section': 'resource_limits', 'method': 'PUT', 'path': '/bots/bot/container/metrics', 'body': {'resource_limits': {'cpu_millicores': 500}}},
                   'before': {'resource_limits': {'desired': old, 'observed': {'memory_usage_bytes': 123}}}}]
        self.assertEqual(undo(Client(), states, [{'state_index': 0}]), [])
        self.assertEqual(calls[0][2], {'resource_limits': old})
        calls.clear()
        missing = [{'action': {'section': 'channel_status', 'method': 'PUT', 'path': '/bots/bot/channel/missing', 'body': {'enabled': False}}, 'before': None}]
        self.assertTrue(undo(Client(), missing, [{'state_index': 0}]))
        self.assertEqual(calls, [])

    def test_bundle_exports_native_resources_and_extra_files(self):
        custom = {'workspace_files': {'mode': 'apply', 'requests': [{'path': '/data/USER.md', 'content': 'preferred name: 小林'}]},
                  'schedules': {'mode': 'apply', 'requests': [{'name': 'test', 'enabled': False, 'pattern': '0 21 * * *', 'command': 'hello'}]}}
        with zipfile.ZipFile(io.BytesIO(bundle(self.template, bindings={'chat_model_id':'model-123'}, customizations=custom))) as archive:
            self.assertEqual(json.loads(archive.read('bot/schedules.json'))[0]['enabled'], False)
            with tarfile.open(fileobj=io.BytesIO(archive.read('workspace/data.tar.gz')), mode='r:gz') as tar:
                self.assertEqual(tar.extractfile('USER.md').read().decode(), 'preferred name: 小林')
                recipe = json.load(tar.extractfile('.memoh/template/customization.json'))
                self.assertEqual(recipe['workspace_files'], custom['workspace_files'])

    def test_bundle_keeps_env_reference_without_materializing_secret(self):
        custom = {'mcp': {'mode': 'apply', 'requests': [{'name': 'demo', 'headers': {'Authorization': {'env': 'TEST_MCP_TOKEN'}}}]}}
        with patch.dict(os.environ, {'TEST_MCP_TOKEN': 'must-not-be-exported'}):
            raw = bundle(self.template, customizations=custom)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertNotIn('bot/mcp_connections.json', archive.namelist())
            for name in archive.namelist():
                self.assertNotIn(b'must-not-be-exported', archive.read(name))
            with tarfile.open(fileobj=io.BytesIO(archive.read('workspace/data.tar.gz')),mode='r:gz') as tar:
                recipe=json.load(tar.extractfile('.memoh/template/customization.json'))
                self.assertEqual(recipe['mcp']['requests'][0]['headers']['Authorization'],{'env':'TEST_MCP_TOKEN'})
                self.assertNotIn('must-not-be-exported',json.dumps(recipe))

    def test_mcp_backup_restores_url_stored_in_nested_connection_config(self):
        old={'id':'existing','name':'same','type':'http','is_active':False,'config':{'url':'https://old.invalid/mcp','headers':{'X-Test':'old'}}}
        calls=[]
        class Client:
            def request(self,method,path,data=None):
                calls.append((method,path,data))
                return {'items':[old]}
        actions=plan(self.template,{'mcp':{'mode':'apply','requests':[{'name':'same','url':'https://new.invalid/mcp','is_active':False}]}},'bot',self.contract)
        states=snapshot_actions(Client(),actions)
        self.assertEqual(states[0]['action']['method'],'PUT')
        self.assertEqual(undo(Client(),states,[{'state_index':0}]),[])
        self.assertEqual(calls[-1][2]['url'],'https://old.invalid/mcp')

    def test_nested_schedule_execution_fields_are_type_checked(self):
        with self.assertRaises(ValueError):
            plan(self.template,{'schedule_update':{'mode':'apply','path_parameters':{'id':'existing'},'requests':[{'execution':{'max_run_seconds':'wrong'}}]}},'bot',self.contract)


if __name__ == '__main__':
    unittest.main()
