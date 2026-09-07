"""离线验证派发行为；假 BB 边界不创建真实线程。"""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).with_name('bb-dispatch')
loader = importlib.machinery.SourceFileLoader('dispatch', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'config.yaml'
        self.config.write_text('''version: 1
permission_mode: accept-edits
defaults: {simple: primary, medium: primary, complex: specialist, debug: specialist}
agents:
  primary: {provider: primary, model: fast-model, reasoning: max}
  specialist: {provider: specialist, model: deep-model, reasoning: {simple: low, medium: medium, complex: medium}}
environments:
  env_other:
    agents:
      specialist: {provider: remote-provider, model: remote-model, reasoning: medium}
''')
        self.calls = []
        self.providers = [{'id': name, 'available': True, 'capabilities': {'permissionModes': ['accept-edits']}} for name in ['primary', 'specialist', 'remote-provider']]

    def fake(self, *args):
        self.calls.append(args)
        if args == ('status',):
            return {'project': {'id': 'proj'}, 'thread': {'id': 'parent', 'environment': {'display': {'id': 'env'}}}}
        if args[:2] == ('environment', 'show'):
            return {'id': args[2], 'projectId': 'proj'}
        if args[:2] == ('provider', 'list'):
            return self.providers
        if args[:2] == ('provider', 'models'):
            model = {'primary': 'fast-model', 'specialist': 'deep-model', 'remote-provider': 'remote-model'}[args[2]]
            return [{'id': model, 'supportedReasoningEfforts': [{'reasoningEffort': x} for x in ['low', 'medium', 'max']]}]
        if args[:2] == ('thread', 'spawn'):
            return {'thread': {'id': 'created', 'status': 'queued'}}
        raise AssertionError(args)

    def args(self, *extra):
        return m.parser().parse_args(['--config', str(self.config), '--difficulty', 'simple', '--task', 'literal $(touch nope) "text"', *extra])

    def test_dry_run_never_spawns_and_preserves_task(self):
        result = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'primary')
        self.assertIn('literal $(touch nope) "text"', result['argv'])
        self.assertIn('parent', result['argv'])
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_simple_debug_uses_specialist_low_and_spawns_once(self):
        result = m.dispatch(self.args('--kind', 'debug'), self.fake)
        self.assertEqual(result['selection']['provider'], 'specialist')
        self.assertEqual(result['selection']['reasoning'], 'low')
        self.assertEqual(result['result']['thread']['status'], 'queued')
        self.assertEqual(sum(c[:2] == ('thread', 'spawn') for c in self.calls), 1)

    def test_environment_alias_override(self):
        result = m.dispatch(self.args('--environment', 'env_other', '--kind', 'debug', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['provider'], 'remote-provider')
        self.assertEqual(result['selection']['model'], 'remote-model')
        self.assertNotIn('--parent-thread', result['argv'])

    def test_explicit_alias_overrides_debug(self):
        result = m.dispatch(self.args('--kind', 'debug', '--agent', 'primary', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'primary')

    def test_unknown_provider_rejected_before_model_query(self):
        self.providers = []
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('provider', 'models') for c in self.calls))

    def test_permission_mismatch_does_not_escalate(self):
        self.providers[0]['capabilities']['permissionModes'] = ['full']
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))
        result = m.dispatch(self.args('--permission-mode', 'full', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['permission_mode'], 'full')

    def test_invalid_model_reasoning_and_project_do_not_spawn(self):
        for extra in [('--reasoning', 'high'), ('--project', 'wrong')]:
            with self.assertRaises(m.DispatchError):
                m.dispatch(self.args(*extra), self.fake)
        self.config.write_text(self.config.read_text().replace('model: fast-model', 'model: missing'))
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_provider_without_reasoning_uses_default(self):
        self.config.write_text(self.config.read_text().replace(', reasoning: max', ''))
        def no_levels(*args):
            if args[:2] == ('provider', 'models'):
                return [{'id': 'fast-model'}]
            return self.fake(*args)
        result = m.dispatch(self.args('--dry-run'), no_levels)
        self.assertIsNone(result['selection']['reasoning'])
        self.assertNotIn('--reasoning-level', result['argv'])
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args('--reasoning', 'max'), no_levels)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_missing_config_does_not_call_bb(self):
        self.config.unlink()
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertEqual(self.calls, [])

    def test_partial_reasoning_map_uses_default(self):
        self.config.write_text(self.config.read_text().replace('simple: low, ', ''))
        result = m.dispatch(self.args('--kind', 'debug', '--dry-run'), self.fake)
        self.assertIsNone(result['selection']['reasoning'])
        self.assertNotIn('--reasoning-level', result['argv'])

    def test_spawn_failure_is_not_retried(self):
        def failing(*args):
            if args[:2] == ('thread', 'spawn'):
                self.calls.append(args)
                raise m.DispatchError('创建结果未知')
            return self.fake(*args)
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), failing)
        self.assertEqual(sum(c[:2] == ('thread', 'spawn') for c in self.calls), 1)


if __name__ == '__main__':
    unittest.main()
