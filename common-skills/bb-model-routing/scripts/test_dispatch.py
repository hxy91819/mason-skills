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
        self.config.write_text('''version: 2
permission_mode: accept-edits
defaults: {simple: primary, medium: primary, complex: specialist, debug: specialist, test: primary, judge: specialist}
agents:
  primary:
    provider: primary
    routes:
      simple: {model: fast-model, reasoning: max}
      medium: {model: medium-model, reasoning: high}
      test: {model: validator-model, reasoning: high}
  specialist:
    provider: specialist
    routes:
      simple: {model: deep-model, reasoning: low}
      medium: {model: deep-model, reasoning: medium}
      complex: {model: deep-model, reasoning: medium}
      judge: {model: deep-model, reasoning: max}
environments:
  env_other:
    agents:
      specialist:
        provider: remote-provider
        routes:
          default: {model: remote-model, reasoning: medium}
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
            models = {
                'primary': ['fast-model', 'medium-model', 'validator-model'],
                'specialist': ['deep-model'],
                'remote-provider': ['remote-model'],
            }[args[2]]
            return [{'id': model, 'supportedReasoningEfforts': [
                {'reasoningEffort': x} for x in ['low', 'medium', 'high', 'xhigh', 'max']
            ]} for model in models]
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

    def test_kind_test_uses_test_default_and_spawns_once(self):
        result = m.dispatch(self.args('--kind', 'test'), self.fake)
        self.assertEqual(result['selection']['agent'], 'primary')
        self.assertEqual(result['selection']['model'], 'validator-model')
        self.assertEqual(result['selection']['reasoning'], 'high')
        self.assertEqual(result['selection']['kind'], 'test')
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

    def test_judge_uses_independent_reasoning_from_complex_worker(self):
        for dry_run in (False, True):
            extra = ['--dry-run'] if dry_run else []
            worker = m.dispatch(self.args('--difficulty', 'complex', *extra), self.fake)
            judge = m.dispatch(self.args('--difficulty', 'complex', '--kind', 'judge', *extra), self.fake)
            self.assertEqual(worker['selection']['model'], judge['selection']['model'])
            self.assertEqual(worker['selection']['reasoning'], 'medium')
            self.assertEqual(judge['selection']['reasoning'], 'max')
            self.assertEqual(judge['selection']['kind'], 'judge')
            command = judge['argv'] if dry_run else self.calls[-1]
            self.assertEqual(command[command.index('--prompt') + 1], self.args().task)

    def test_routes_use_role_then_difficulty_then_default(self):
        primary = m.yaml.safe_load(self.config.read_text())['agents']['primary']['routes']
        primary['default'] = {'model': 'fast-model', 'reasoning': 'low'}
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['primary']['routes'] = primary
        self.config.write_text(m.yaml.safe_dump(config))
        medium = m.dispatch(self.args('--difficulty', 'medium', '--dry-run'), self.fake)
        self.assertEqual((medium['selection']['model'], medium['selection']['reasoning']), ('medium-model', 'high'))
        debug = m.dispatch(self.args('--kind', 'debug', '--agent', 'primary', '--dry-run'), self.fake)
        self.assertEqual((debug['selection']['model'], debug['selection']['reasoning']), ('fast-model', 'max'))
        fallback = m.dispatch(self.args('--difficulty', 'complex', '--agent', 'primary', '--dry-run'), self.fake)
        self.assertEqual((fallback['selection']['model'], fallback['selection']['reasoning']), ('fast-model', 'low'))

    def test_judge_environment_and_explicit_alias_take_precedence(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['defaults']['judge'] = 'specialist'
        config['agents']['primary']['routes']['default'] = {'model': 'fast-model', 'reasoning': 'max'}
        config['environments']['env_other']['defaults'] = {'judge': 'primary'}
        self.config.write_text(m.yaml.safe_dump(config))
        result = m.dispatch(self.args('--kind', 'judge', '--environment', 'env_other', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'primary')
        result = m.dispatch(self.args('--kind', 'judge', '--environment', 'env_other',
                                      '--agent', 'specialist', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['provider'], 'remote-provider')

    def test_invalid_explicit_judge_route_does_not_fall_back_or_spawn(self):
        config = m.yaml.safe_load(self.config.read_text())
        for alias in (None, '', 'missing'):
            with self.subTest(alias=alias):
                config['defaults']['judge'] = alias
                self.config.write_text(m.yaml.safe_dump(config))
                with self.assertRaises(m.DispatchError):
                    m.dispatch(self.args('--difficulty', 'complex', '--kind', 'judge'), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

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
        for extra in [('--reasoning', 'ultra'), ('--project', 'wrong')]:
            with self.assertRaises(m.DispatchError):
                m.dispatch(self.args(*extra), self.fake)
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['primary']['routes']['simple']['model'] = 'missing'
        self.config.write_text(m.yaml.safe_dump(config))
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_provider_without_reasoning_uses_default(self):
        config = m.yaml.safe_load(self.config.read_text())
        del config['agents']['primary']['routes']['simple']['reasoning']
        self.config.write_text(m.yaml.safe_dump(config))
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

    def test_invalid_or_missing_routes_do_not_spawn(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['primary']['model'] = 'fast-model'
        self.config.write_text(m.yaml.safe_dump(config))
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        config['agents']['primary'].pop('model')
        config['agents']['primary']['routes'].pop('simple')
        self.config.write_text(m.yaml.safe_dump(config))
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_version_one_config_is_rejected_before_calling_bb(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['version'] = 1
        self.config.write_text(m.yaml.safe_dump(config))
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertEqual(self.calls, [])

    def test_titles_are_prefixed_in_preview_and_spawn(self):
        cases = [(None, '[Agent] literal $(touch nope) "text"'),
                 ('修复登录', '[Agent] 修复登录'),
                 ('  [Agent] [Agent] 修复\n登录 ', '[Agent] 修复 登录'),
                 ('[Agent]', '[Agent] 任务'),
                 ('文' * 100, '[Agent] ' + '文' * 79 + '…')]
        for supplied, expected in cases:
            for dry_run in (False, True):
                with self.subTest(title=supplied, dry_run=dry_run):
                    extra = ['--title', supplied] if supplied is not None else []
                    if dry_run:
                        extra += ['--dry-run']
                    result = m.dispatch(self.args(*extra), self.fake)
                    command = result['argv'] if dry_run else self.calls[-1]
                    self.assertEqual(command[command.index('--title') + 1], expected)
                    self.assertEqual(result['selection']['title'], expected)

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
