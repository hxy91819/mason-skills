"""离线验证派发行为；假 BB 边界不创建真实线程。"""
import importlib.machinery
import importlib.util
import os
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
        self.ledger = Path(self.temp.name) / 'ledger.json'
        self.config.write_text('''version: 2
permission_mode: accept-edits
defaults: {simple: primary, medium: primary, complex: specialist}
agents:
  primary:
    provider: primary
    routes:
      simple: {model: fast-model, reasoning: max}
      medium: {model: medium-model, reasoning: high}
  specialist:
    provider: specialist
    routes:
      simple: {model: deep-model, reasoning: low}
      medium: {model: deep-model, reasoning: medium}
      complex: {model: deep-model, reasoning: medium}
environments:
  env_other:
    agents:
      specialist:
        provider: remote-provider
        routes:
          default: {model: remote-model, reasoning: medium}
''')
        self.calls = []
        self.spawn_counter = 0
        self.threads = []
        self.pending_retries = {}
        self.retry_diagnostics = {}
        self.retry_fails = False
        self.providers =[{'id': name, 'available': True, 'capabilities': {'permissionModes': ['accept-edits']}} for name in ['primary', 'specialist', 'remote-provider']]

    def fake(self, *args):
        self.calls.append(args)
        if args == ('status',):
            return {'project': {'id': 'proj'}, 'thread': {'id': 'parent', 'environment': {'display': {'id': 'env'}}}}
        if args[:2] == ('environment', 'show'):
            return {'id': args[2], 'projectId': 'proj'}
        if args[:2] == ('thread', 'show'):
            known = next((t for t in self.threads if t.get('id') == args[2]), {})
            return {'thread': {'id': args[2], 'projectId': 'proj', 'status': 'error', **known}}
        if args == ('thread', 'list'):
            return self.threads
        if args[:2] == ('provider-retry', 'status'):
            return {'retries': self.pending_retries.get(args[2], [])}
        if args[:2] == ('provider-retry', 'explain'):
            return {'threadId': args[2], 'diagnostic': self.retry_diagnostics.get(args[2])}
        if args[:2] == ('thread', 'retry'):
            if self.retry_fails:
                raise m.DispatchError('no failed turn to retry')
            return {'ok': True}
        if args[:2] == ('provider', 'list'):
            return self.providers
        if args[:2] == ('provider', 'models'):
            models = {
                'primary': ['fast-model', 'medium-model'],
                'specialist': ['deep-model'],
                'remote-provider': ['remote-model'],
            }[args[2]]
            return [{'id': model, 'supportedReasoningEfforts': [
                {'reasoningEffort': x} for x in ['low', 'medium', 'high', 'xhigh', 'max']
            ]} for model in models]
        if args[:2] == ('thread', 'spawn'):
            self.spawn_counter += 1
            return {'thread': {'id': f'created_{self.spawn_counter}', 'status': 'queued'}}
        raise AssertionError(args)

    def args(self, *extra):
        return m.parser().parse_args([
            '--config', str(self.config),
            '--ledger', str(self.ledger),
            '--difficulty', 'simple',
            '--task', 'literal $(touch nope) "text"',
            *extra,
        ])

    def test_dry_run_never_spawns_and_preserves_task(self):
        result = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'primary')
        prompt = result['argv'][result['argv'].index('--prompt') + 1]
        self.assertTrue(prompt.startswith(self.args().task + m.REPORT_PROTOCOL_ANCHOR))
        self.assertIn('--parent-thread', result['argv'])
        self.assertIn('parent', result['argv'])
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_linked_child_gets_report_protocol_once_and_copied_task_redispatches_identically(self):
        self.load_balance_config()

        def prompt(result):
            return result['argv'][result['argv'].index('--prompt') + 1]

        for index in range(8):
            task = f'linked task {index}'
            first = m.dispatch(self.args('--task', task, '--dry-run'), self.fake)
            self.assertEqual(prompt(first), task + m.REPORT_PROTOCOL_ANCHOR + m.REPORT_PROTOCOL)
            # 续派时从子线程首条消息复制任务文本：不重复附加，候选顺序与标题不变。
            copied = m.dispatch(self.args('--task', prompt(first), '--dry-run'), self.fake)
            self.assertEqual(prompt(copied), prompt(first))
            self.assertEqual(copied['selection']['candidates'], first['selection']['candidates'])
            self.assertEqual(copied['selection']['title'], first['selection']['title'])

    def test_kind_option_is_removed(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.args('--kind', 'debug')

    def test_environment_alias_override(self):
        result = m.dispatch(self.args('--environment', 'env_other', '--difficulty', 'complex', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['provider'], 'remote-provider')
        self.assertEqual(result['selection']['model'], 'remote-model')
        self.assertEqual(result['selection']['validation_environment'], 'env_other')
        self.assertIn('--parent-thread', result['argv'])

    def test_workspace_path_uses_proxy_validation_without_environment_show(self):
        workspace = Path(self.temp.name) / 'env_other'
        workspace.mkdir()
        result = m.dispatch(self.args('--environment', str(workspace), '--difficulty', 'complex', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['environment'], str(workspace.resolve()))
        self.assertEqual(result['selection']['validation_environment'], 'env')
        self.assertEqual(result['selection']['provider'], 'specialist')
        self.assertIn(str(workspace.resolve()), result['argv'])
        self.assertFalse(any(c[:2] == ('environment', 'show') for c in self.calls))
        self.assertIn(('provider', 'list', '--environment', 'env'), self.calls)
        self.assertIn(
            ('provider', 'models', 'specialist', '--environment', 'env', '--selected-model', 'deep-model'),
            self.calls,
        )

    def test_model_catalog_includes_configured_selected_model(self):
        m.dispatch(self.args('--dry-run'), self.fake)
        self.assertIn(
            ('provider', 'models', 'primary', '--environment', 'env', '--selected-model', 'fast-model'),
            self.calls,
        )

    def test_relative_workspace_path_is_resolved(self):
        workspace = Path(self.temp.name) / 'workspace'
        workspace.mkdir()
        relative = Path(os.path.relpath(workspace, Path.cwd()))
        result = m.dispatch(self.args('--environment', str(relative), '--dry-run'), self.fake)
        self.assertEqual(result['selection']['environment'], str(workspace.resolve()))
        self.assertEqual(result['argv'][result['argv'].index('--environment') + 1], str(workspace.resolve()))

    def test_workspace_path_requires_project(self):
        workspace = Path(self.temp.name) / 'workspace'
        workspace.mkdir()

        def status_without_project(*args):
            if args == ('status',):
                return {'thread': {'id': 'parent', 'environment': {'display': {'id': 'env'}}}}
            return self.fake(*args)

        with self.assertRaisesRegex(m.DispatchError, '--project'):
            m.dispatch(self.args('--environment', str(workspace), '--dry-run'), status_without_project)
        self.assertFalse(any(c[:2] == ('provider', 'list') for c in self.calls))

    def test_workspace_path_requires_proxy_environment(self):
        workspace = Path(self.temp.name) / 'workspace'
        workspace.mkdir()

        def status_without_environment(*args):
            if args == ('status',):
                return {'project': {'id': 'proj'}, 'thread': {'id': 'parent'}}
            return self.fake(*args)

        with self.assertRaisesRegex(m.DispatchError, '代理环境'):
            m.dispatch(self.args('--environment', str(workspace), '--dry-run'), status_without_environment)
        self.assertFalse(any(c[:2] == ('provider', 'list') for c in self.calls))

    def test_workspace_path_in_another_project_does_not_link_parent(self):
        workspace = Path(self.temp.name) / 'workspace'
        workspace.mkdir()
        result = m.dispatch(self.args('--project', 'other', '--environment', str(workspace), '--dry-run'), self.fake)
        self.assertNotIn('--parent-thread', result['argv'])
        self.assertEqual(result['argv'][result['argv'].index('--prompt') + 1], self.args().task)

    def test_agent_override_is_rejected_before_calling_bb(self):
        import contextlib
        import io

        for flags in (('--agent', 'primary'), ('--agent', 'primary', '--fallback-from', 'specialist')):
            with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    m.dispatch(self.args(*flags), self.fake)
                self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.calls, [])

    def test_routes_use_exact_route_then_default(self):
        primary = m.yaml.safe_load(self.config.read_text())['agents']['primary']['routes']
        primary['default'] = {'model': 'fast-model', 'reasoning': 'low'}
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['primary']['routes'] = primary
        config['defaults']['complex'] = 'primary'
        self.config.write_text(m.yaml.safe_dump(config))
        medium = m.dispatch(self.args('--difficulty', 'medium', '--dry-run'), self.fake)
        self.assertEqual((medium['selection']['model'], medium['selection']['reasoning']), ('medium-model', 'high'))
        fallback = m.dispatch(self.args('--difficulty', 'complex', '--dry-run'), self.fake)
        self.assertEqual((fallback['selection']['model'], fallback['selection']['reasoning']), ('fast-model', 'low'))

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
        cases = [(None, 'literal $(touch nope) "text"'),
                 ('  ', 'literal $(touch nope) "text"'),
                 ('修复登录', '修复登录'),
                 ('  [Agent] [Agent] 修复\n登录 ', '修复 登录'),
                 ('🟢 🟡 🔴 [Agent] 修复登录', '修复登录'),
                 ('[Agent]', '任务'),
                 ('🟢', '任务'),
                 ('文' * 100, '文' * 79 + '…')]
        for supplied, expected in cases:
            for difficulty, prefix in [('simple', '🟢'), ('medium', '🟡'), ('complex', '🔴')]:
                for dry_run in (False, True):
                    with self.subTest(title=supplied, difficulty=difficulty, dry_run=dry_run):
                        extra = ['--difficulty', difficulty]
                        if supplied is not None:
                            extra += ['--title', supplied]
                        if dry_run:
                            extra += ['--dry-run']
                        result = m.dispatch(self.args(*extra), self.fake)
                        command = result['argv'] if dry_run else self.calls[-1]
                        self.assertEqual(command[command.index('--title') + 1], prefix + ' ' + expected)
                        self.assertEqual(result['selection']['title'], prefix + ' ' + expected)

    def test_spawn_failure_is_not_retried(self):
        def failing(*args):
            if args[:2] == ('thread', 'spawn'):
                self.calls.append(args)
                raise m.DispatchError('创建结果未知')
            return self.fake(*args)
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), failing)
        self.assertEqual(sum(c[:2] == ('thread', 'spawn') for c in self.calls), 1)

    def chain_config(self, chain):
        config = m.yaml.safe_load(self.config.read_text())
        config['defaults']['simple'] = chain
        self.config.write_text(m.yaml.safe_dump(config))

    def load_balance_config(self):
        self.chain_config({'mode': 'load-balance', 'candidates': ['primary', 'specialist']})

    def weighted_load_balance_config(self):
        self.chain_config({'mode': 'weighted-load-balance',
                           'candidates': {'primary': 2, 'specialist': 1}})

    def test_defaults_list_falls_back_when_provider_unavailable(self):
        self.chain_config(['primary', 'specialist'])
        self.providers[0]['available'] = False
        result = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'specialist')
        self.assertEqual(result['selection']['provider'], 'specialist')
        self.assertEqual((result['selection']['model'], result['selection']['reasoning']), ('deep-model', 'low'))
        self.assertEqual(result['selection']['candidates'], ['primary', 'specialist'])
        self.assertEqual(result['selection']['fallbacks'], [])
        self.assertEqual([a['agent'] for a in result['selection']['attempts']], ['primary'])

    def test_healthy_primary_keeps_fallbacks_untried(self):
        self.chain_config(['primary', 'specialist'])
        result = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'primary')
        self.assertEqual(result['selection']['routing_mode'], 'fallback')
        self.assertEqual(result['selection']['fallbacks'], ['specialist'])
        self.assertEqual(result['selection']['attempts'], [])
        self.assertFalse(any(c[:2] == ('provider', 'models', 'specialist') for c in self.calls))

    def test_load_balance_is_stable_per_task_and_spreads_independent_tasks(self):
        self.load_balance_config()
        selections = {}
        for index in range(32):
            task = f'independent task {index}'
            first = m.dispatch(self.args('--task', task, '--dry-run'), self.fake)['selection']
            second = m.dispatch(self.args('--task', task, '--dry-run'), self.fake)['selection']
            self.assertEqual((first['agent'], first['candidates']), (second['agent'], second['candidates']))
            self.assertEqual(first['routing_mode'], 'load-balance')
            selections[task] = first['agent']
        self.assertEqual(set(selections.values()), {'primary', 'specialist'})

    def test_load_balance_skips_unavailable_preferred_candidate(self):
        self.load_balance_config()
        args = self.args('--task', 'stable unavailable candidate', '--dry-run')
        preferred = m.dispatch(args, self.fake)['selection']['agent']
        next(provider for provider in self.providers if provider['id'] == preferred)['available'] = False
        result = m.dispatch(args, self.fake)['selection']
        self.assertNotEqual(result['agent'], preferred)
        self.assertEqual(result['attempts'][0]['agent'], preferred)

    def test_weighted_load_balance_is_stable_and_follows_relative_weights(self):
        self.weighted_load_balance_config()
        counts = {'primary': 0, 'specialist': 0}
        for index in range(180):
            args = self.args('--task', f'weighted task {index}', '--dry-run')
            first = m.dispatch(args, self.fake)['selection']
            if index < 8:
                second = m.dispatch(args, self.fake)['selection']
                self.assertEqual(first['candidates'], second['candidates'])
                self.assertEqual(first['candidate_weights'], second['candidate_weights'])
            self.assertEqual(first['routing_mode'], 'weighted-load-balance')
            counts[first['agent']] += 1
        ratio = counts['primary'] / counts['specialist']
        self.assertGreater(ratio, 1.5)
        self.assertLess(ratio, 2.6)

    def test_zero_weight_candidate_is_excluded_from_selection_and_fallback(self):
        for disabled in ('primary', 'specialist'):
            active = 'specialist' if disabled == 'primary' else 'primary'
            self.chain_config({'mode': 'weighted-load-balance',
                               'candidates': {disabled: 0, active: 1}})
            for index in range(8):
                self.calls.clear()
                result = m.dispatch(self.args('--task', f'paused task {index}', '--dry-run'), self.fake)['selection']
                self.assertEqual(result['agent'], active)
                self.assertEqual(result['candidates'], [active])
                self.assertEqual(result['candidate_weights'], {active: 1})
                self.assertEqual(result['fallbacks'], [])
                self.assertFalse(any(c[:3] == ('provider', 'models', disabled) for c in self.calls))
            with self.assertRaises(m.DispatchError):
                m.dispatch(self.args('--fallback-from', disabled, '--dry-run'), self.fake)

    def test_zero_weight_candidate_is_not_used_when_active_candidate_fails(self):
        self.chain_config({'mode': 'weighted-load-balance',
                           'candidates': {'primary': 1, 'specialist': 0}})
        self.providers[0]['available'] = False
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:3] == ('provider', 'models', 'specialist') for c in self.calls))
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_all_zero_weights_fail_before_provider_validation(self):
        self.chain_config({'mode': 'weighted-load-balance',
                           'candidates': {'primary': 0, 'specialist': 0.0}})
        with self.assertRaisesRegex(m.DispatchError, '至少需要一个权重大于 0'):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] in (('provider', 'list'), ('thread', 'spawn')) for c in self.calls))

    def test_paused_candidate_can_be_restored_with_positive_weight(self):
        self.chain_config({'mode': 'weighted-load-balance',
                           'candidates': {'primary': 0, 'specialist': 1}})
        paused = m.dispatch(self.args('--dry-run'), self.fake)['selection']
        self.assertEqual(paused['candidates'], ['specialist'])
        self.weighted_load_balance_config()
        restored = m.dispatch(self.args('--dry-run'), self.fake)['selection']
        self.assertEqual(set(restored['candidates']), {'primary', 'specialist'})
        self.assertEqual(restored['candidate_weights'], {'primary': 2, 'specialist': 1})

    def test_candidate_without_matching_route_counts_as_failed(self):
        self.chain_config(['primary', 'missing', 'specialist'])
        original = self.fake

        def sparse(*a):
            if a[:2] == ('provider', 'models') and a[2] == 'primary':
                return [entry for entry in original(*a) if entry['id'] != 'fast-model']
            return original(*a)

        result = m.dispatch(self.args('--dry-run'), sparse)
        self.assertEqual(result['selection']['agent'], 'specialist')
        self.assertEqual([a['agent'] for a in result['selection']['attempts']], ['primary', 'missing'])

    def test_all_candidates_failed_reports_each_and_never_spawns(self):
        self.chain_config(['primary', 'specialist'])
        for provider in self.providers:
            provider['available'] = False
        with self.assertRaisesRegex(m.DispatchError, 'primary.*specialist'):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_invalid_chain_values_rejected_before_calling_bb(self):
        config = m.yaml.safe_load(self.config.read_text())
        for value in ([], 5, ['primary', ''], ['primary', 'primary'],
                      {'mode': 'round-robin', 'candidates': ['primary']},
                      {'mode': 'load-balance', 'candidates': []},
                      {'mode': 'weighted-load-balance', 'candidates': []},
                      {'mode': 'weighted-load-balance', 'candidates': {'primary': 0}},
                      {'mode': 'weighted-load-balance', 'candidates': {'primary': -1}},
                      {'mode': 'weighted-load-balance', 'candidates': {'primary': float('nan')}},
                      {'mode': 'weighted-load-balance', 'candidates': {'primary': float('inf')}},
                      {'mode': 'weighted-load-balance', 'candidates': {'primary': True}},
                      {'mode': 'weighted-load-balance', 'candidates': {'primary': '.nan'}}):
            with self.subTest(value=value):
                config['defaults']['simple'] = value
                self.config.write_text(m.yaml.safe_dump(config))
                with self.assertRaises(m.DispatchError):
                    m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('provider', 'list') for c in self.calls))

    def test_fallback_from_resumes_chain_at_alias(self):
        self.chain_config(['primary', 'specialist'])
        result = m.dispatch(self.args('--fallback-from', 'specialist', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['provider'], 'specialist')
        self.assertEqual(result['selection']['candidates'], ['specialist'])
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args('--fallback-from', 'missing'), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_spawn_failure_is_not_retried_but_names_next_candidate(self):
        self.chain_config(['primary', 'specialist'])
        original = self.fake

        def flaky(*a):
            if a[:2] == ('thread', 'spawn'):
                self.calls.append(a)
                raise m.DispatchError('quota exhausted')
            return original(*a)

        with self.assertRaisesRegex(m.DispatchError, '--fallback-from specialist'):
            m.dispatch(self.args(), flaky)
        self.assertEqual(sum(c[:2] == ('thread', 'spawn') for c in self.calls), 1)

    def test_environment_defaults_override_accepts_chain(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['environments']['env_other']['defaults'] = {'complex': ['missing', 'specialist']}
        self.config.write_text(m.yaml.safe_dump(config))
        result = m.dispatch(self.args('--environment', 'env_other', '--difficulty', 'complex', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'specialist')
        self.assertEqual(result['selection']['provider'], 'remote-provider')

    def test_closed_scope_requires_simple_unless_escalated(self):
        with self.assertRaisesRegex(m.DispatchError, '--closed-scope.*--difficulty simple'):
            m.dispatch(self.args('--difficulty', 'medium', '--closed-scope', '--dry-run'), self.fake)
        self.assertEqual(self.calls, [])
        ok_simple = m.dispatch(self.args('--difficulty', 'simple', '--closed-scope', '--dry-run'), self.fake)
        self.assertEqual(ok_simple['selection']['difficulty'], 'simple')
        ok_escalated = m.dispatch(
            self.args('--difficulty', 'medium', '--closed-scope', '--escalate-from', 'thr_prev_failed', '--dry-run'),
            self.fake,
        )
        self.assertEqual(ok_escalated['selection']['escalated_from'], 'thr_prev_failed')
        self.assertIn(('thread', 'show', 'thr_prev_failed'), self.calls)

    def test_overlong_task_rejected_for_medium_and_complex_but_allowed_for_simple_or_review(self):
        long_task = '细化步骤' * 700  # 2800 chars > 2500
        for diff in ('medium', 'complex'):
            with self.assertRaisesRegex(m.DispatchError, '说明父线程已完成细化'):
                m.dispatch(self.args('--difficulty', diff, '--task', long_task, '--dry-run'), self.fake)
        # simple 允许长任务书
        simple_ok = m.dispatch(self.args('--difficulty', 'simple', '--task', long_task, '--dry-run'), self.fake)
        self.assertEqual(simple_ok['selection']['difficulty'], 'simple')
        # autoreview 附加的审查提示词不计入有效任务指导长度
        review_task = '只读审查 commit abc123\n\n# Review agent 提示词\n' + ('标准正文' * 800)
        review_ok = m.dispatch(self.args('--difficulty', 'medium', '--task', review_task, '--dry-run'), self.fake)
        self.assertEqual(review_ok['selection']['difficulty'], 'medium')
        # ask-oracle 的 Verified context 证据块与 large-task-orchestrator 的执行包/报告协议块不计入有效指导长度
        oracle_task = (
            '你是本次咨询的 Oracle。\n\n# Goal\n评估方案\n\n# Verified context\n'
            + ('证据行\n' * 900)
            + '\n# Question for the oracle\n架构是否可行？\n\n# Expected response\n给出结论'
        )
        oracle_ok = m.dispatch(self.args('--difficulty', 'complex', '--task', oracle_task, '--dry-run'), self.fake)
        self.assertEqual(oracle_ok['selection']['difficulty'], 'complex')
        driver_worker_task = (
            '实现 Story STORY-01，一次只处理这一张 Story。\n\n执行包：\n```json\n'
            + ('{"k": "v"}\n' * 300)
            + '```\n\n完成工作后必须提交结构化报告。\n'
        )
        driver_ok = m.dispatch(self.args('--difficulty', 'medium', '--task', driver_worker_task, '--dry-run'), self.fake)
        self.assertEqual(driver_ok['selection']['difficulty'], 'medium')
        # 显式传入 --escalate-from 允许豁免
        esc_ok = m.dispatch(
            self.args('--difficulty', 'medium', '--task', long_task, '--escalate-from', 'thr_prev', '--dry-run'),
            self.fake,
        )
        self.assertEqual(esc_ok['selection']['escalated_from'], 'thr_prev')

    def test_ledger_records_minimal_facts_and_overwrites_on_repeat_decision(self):
        res = m.dispatch(self.args('--task', 'SENSITIVE_SECRET_TOKEN_123'), self.fake, now=1000)
        tid = res['result']['thread']['id']
        raw_ledger = self.ledger.read_text()
        self.assertNotIn('SENSITIVE_SECRET_TOKEN_123', raw_ledger)
        # 未知 ID 拒绝
        with self.assertRaisesRegex(m.DispatchError, '拒绝回写未知 ID'):
            m.record_decision_command(
                m.parser().parse_args(['--ledger', str(self.ledger), '--record-decision', 'thr_unknown', '--decision', 'accepted']),
                now=1010,
            )
        # 首次回写与重复回写同一 ID 覆盖而非追加
        m.record_decision_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-decision', tid, '--outcome', 'completed', '--decision', 'rejected']),
            now=1010,
        )
        m.record_decision_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-decision', tid, '--decision', 'accepted']),
            now=1020,
        )
        ledger_data = m.load_ledger(self.ledger, strict=True)
        self.assertEqual(len(ledger_data['entries']), 1)
        self.assertEqual(ledger_data['entries'][0]['decision'], 'accepted')
        self.assertEqual(ledger_data['entries'][0]['outcome'], 'completed')
        summary = m.summarize_ledger(ledger_data, now=1020)
        self.assertEqual(summary['total_dispatches'], 1)
        self.assertEqual(summary['by_agent']['primary']['decided'], 1)
        self.assertEqual(summary['by_agent']['primary']['accepted'], 1)

    def test_ledger_rollover_never_double_counts(self):
        ledger = m.empty_ledger()
        for idx in range(205):
            m.append_ledger_entry(ledger, {
                'id': f'thr_{idx}',
                'ts': 1000 + idx,
                'difficulty': 'simple' if idx % 2 == 0 else 'medium',
                'agent': 'primary',
                'provider': 'primary',
                'model': 'fast-model',
                'reasoning': 'max',
                'outcome': 'completed',
                'decision': 'accepted',
            }, max_live=200)
        self.assertEqual(len(ledger['entries']), 200)
        summary = m.summarize_ledger(ledger, now=2000)
        self.assertEqual(summary['live_entries'], 200)
        self.assertEqual(summary['rolled_up_entries'], 5)
        self.assertEqual(summary['total_dispatches'], 205)
        self.assertEqual(summary['by_agent']['primary']['total'], 205)
        self.assertEqual(summary['by_agent']['primary']['accepted'], 205)

    def test_circuit_breaker_skips_cooled_down_candidate_and_recovers(self):
        self.chain_config(['primary', 'specialist'])
        first = m.dispatch(self.args(), self.fake, now=1000)
        self.assertEqual(first['selection']['agent'], 'primary')
        tid = first['result']['thread']['id']
        # 旧版手动回写的失败类型照样计入，但不再按类型定时长。
        m.record_decision_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-decision', tid, '--outcome', 'failed_quota']),
            now=1010,
        )
        # 冷却期内自动跳过 primary，选择 specialist
        second = m.dispatch(self.args('--dry-run'), self.fake, now=1100)
        self.assertEqual(second['selection']['agent'], 'specialist')
        self.assertIn('熔断冷却中', second['selection']['attempts'][0]['error'])
        cooled = m.summarize_ledger(m.load_ledger(self.ledger, strict=True), now=1100)['active_cooldowns']
        self.assertEqual([(c['provider'], c['model'], c['level']) for c in cooled], [('primary', 'fast-model', 1)])
        # 首次失败冷却 15 分钟后自动解除
        third = m.dispatch(self.args('--dry-run'), self.fake, now=1010 + m.BACKOFF_BASE_SECONDS + 1)
        self.assertEqual(third['selection']['agent'], 'primary')

    def on_failure(self, tid, *extra, now):
        return m.on_failure_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--on-failure', tid, *extra]), self.fake, now=now)

    def test_on_failure_retries_in_session_then_cools_provider_and_model(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['defaults']['medium'] = ['specialist', 'primary']
        config['defaults']['simple'] = ['specialist', 'primary']
        self.config.write_text(m.yaml.safe_dump(config))
        tid = m.dispatch(self.args('--difficulty', 'medium'), self.fake, now=1000)['result']['thread']['id']
        self.threads = [{'id': tid, 'status': 'error', 'queuedWork': 'none', 'updatedAt': 1100 * 1000}]
        # 报错先在原会话退避重试，期间不影响新派发。
        delays = [self.on_failure(tid, now=1100 + i)['delay_seconds'] for i in range(m.SESSION_RETRY_LIMIT)]
        self.assertEqual(delays, [60, 120, 240])
        sent = [c[c.index('--send-at') + 1] for c in self.calls if c[:2] == ('thread', 'retry')]
        self.assertEqual(sent, ['60s', '120s', '240s'])
        self.assertEqual(m.dispatch(self.args('--task', 'other', '--dry-run'), self.fake, now=1200)['selection']['agent'], 'specialist')
        # 重试用尽才记失败；冷却按 provider 与模型计，别的档位同样跳过。
        cooled = self.on_failure(tid, now=1500)
        self.assertEqual(cooled['action'], 'cooled')
        self.assertEqual((cooled['cooldown']['provider'], cooled['cooldown']['level']), ('specialist', 1))
        self.assertEqual(m.dispatch(self.args('--task', 'other', '--dry-run'), self.fake, now=1600)['selection']['agent'], 'primary')
        self.assertEqual(m.dispatch(self.args('--difficulty', 'medium', '--dry-run'), self.fake, now=1600)['selection']['agent'], 'primary')
        later = m.dispatch(self.args('--task', 'other', '--dry-run'), self.fake, now=1500 + m.BACKOFF_BASE_SECONDS + 1)
        self.assertEqual(later['selection']['agent'], 'specialist')

    def test_on_failure_defers_to_bb_retry_and_skips_retries_bb_gave_up_on(self):
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.threads = [{'id': tid, 'status': 'active', 'queuedWork': 'none'}]
        self.assertEqual(self.on_failure(tid, now=1100)['action'], 'not-failed')
        self.threads = [{'id': tid, 'status': 'error', 'queuedWork': 'none'}]
        self.pending_retries[tid] = [{'threadId': tid}]
        self.assertEqual(self.on_failure(tid, now=1100)['action'], 'waiting')
        self.pending_retries.clear()
        # BB 已在原会话重试到上限：不再重试，直接冷却。
        self.retry_diagnostics[tid] = {'decision': {'kind': 'decline', 'reason': 'attempts-exhausted'}}
        preview = self.on_failure(tid, '--dry-run', now=1200)
        self.assertEqual((preview['dry_run'], preview['action']), (True, 'cooled'))
        self.assertEqual(m.load_ledger(self.ledger, strict=True)['entries'][0]['outcome'], 'spawned')
        self.assertEqual(self.on_failure(tid, now=1200)['action'], 'cooled')
        self.assertFalse([c for c in self.calls if c[:2] == ('thread', 'retry')])

    def test_on_failure_restarts_count_after_recovery_and_cools_when_retry_is_impossible(self):
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.threads = [{'id': tid, 'status': 'error', 'queuedWork': 'none'}]
        self.assertEqual(self.on_failure(tid, now=1100)['attempt'], 1)
        # 原会话重试成功：派发时补记完成，不留冷却。
        self.threads = [{'id': tid, 'status': 'idle', 'queuedWork': 'none', 'updatedAt': 1200 * 1000}]
        m.dispatch(self.args('--task', 'other'), self.fake, now=1300)
        self.assertEqual(m.summarize_ledger(m.load_ledger(self.ledger, strict=True), now=1300)['active_cooldowns'], [])
        # 之后再报错是新的一次故障，从第 1 次重试算起；原会话无法重试时直接冷却。
        self.threads = [{'id': tid, 'status': 'error', 'queuedWork': 'none'}]
        self.assertEqual(self.on_failure(tid, now=1400)['attempt'], 1)
        self.retry_fails = True
        self.assertEqual(self.on_failure(tid, now=1500)['action'], 'cooled')

    def test_reconcile_records_only_finished_threads_as_completed(self):
        base = 10 ** 6
        ids = [m.dispatch(self.args('--task', f'task {i}'), self.fake, now=base)['result']['thread']['id'] for i in range(5)]
        stale = m.dispatch(self.args('--task', 'stale task'), self.fake,
                           now=base - m.RECENT_WINDOW_SECONDS - 1)['result']['thread']['id']
        at = (base + 100) * 1000
        self.threads = [
            {'id': ids[0], 'status': 'idle', 'queuedWork': 'none', 'updatedAt': at},
            {'id': ids[1], 'status': 'idle', 'queuedWork': 'waiting', 'updatedAt': at},
            {'id': ids[2], 'status': 'idle', 'queuedWork': 'none', 'hasPendingInteraction': True, 'updatedAt': at},
            {'id': ids[3], 'status': 'active', 'queuedWork': 'none', 'updatedAt': at},
            {'id': ids[4], 'status': 'error', 'queuedWork': 'waiting', 'updatedAt': at},
            {'id': stale, 'status': 'error', 'queuedWork': 'none', 'updatedAt': at},
        ]
        m.dispatch(self.args('--task', 'next task'), self.fake, now=base + 200)
        outcomes = {e['id']: e['outcome'] for e in m.load_ledger(self.ledger, strict=True)['entries']}
        self.assertEqual(outcomes[ids[0]], 'completed')
        # 报错留给 --on-failure 处理，这里不记失败。
        self.assertEqual([outcomes[tid] for tid in ids[1:]], ['spawned'] * 4)
        self.assertEqual(outcomes[stale], 'spawned')

    def test_failures_during_cooldown_extend_it_and_later_failures_escalate(self):
        def entry(tid, outcome, at):
            return {'id': tid, 'ts': at - 50, 'provider': 'p', 'model': 'm', 'outcome': outcome, 'outcome_ts': at}

        base = m.BACKOFF_BASE_SECONDS
        # 冷却期内接连失败只算一次，冷却从最后一次失败起算。
        ledger = {'entries': [entry('a', 'failed', 100), entry('b', 'failed', 200), entry('c', 'failed', 300)],
                  'cooldowns': {}}
        cooled = m.health_cooldowns(ledger, now=301)['p|m']
        self.assertEqual((cooled['level'], cooled['until']), (1, 300 + base))
        # 冷却结束后再失败，时长翻倍。
        after = 300 + base
        ledger['entries'].append(entry('d', 'failed', after + 60))
        cooled = m.health_cooldowns(ledger, now=after + 61)['p|m']
        self.assertEqual((cooled['level'], cooled['until']), (2, after + 60 + 2 * base))
        # 一次成功清零。
        ledger['entries'].append(entry('e', 'completed', after + 80))
        self.assertEqual(m.health_cooldowns(ledger, now=after + 81), {})
        # 近期窗口之前的失败不再计入等级。
        old = 10 ** 6
        fresh = old + base + m.RECENT_WINDOW_SECONDS + 100
        stale = {'entries': [entry('o1', 'failed', old), entry('o2', 'failed', old + base + 1),
                             entry('n', 'failed', fresh)], 'cooldowns': {}}
        cooled = m.health_cooldowns(stale, now=fresh + 1)['p|m']
        self.assertEqual((cooled['level'], cooled['until']), (1, fresh + base))
        # 持续失败时封顶 6 小时。
        at, entries = 10 ** 6, []
        for index in range(8):
            entries.append(entry(f'x{index}', 'failed', at))
            cooled = m.health_cooldowns({'entries': entries, 'cooldowns': {}}, now=at + 1)['p|m']
            at = cooled['until']
        self.assertEqual(cooled['level'], 8)
        self.assertEqual(cooled['until'] - entries[-1]['outcome_ts'], m.BACKOFF_MAX_SECONDS)

    def test_decision_only_record_keeps_failure_time(self):
        self.chain_config(['primary', 'specialist'])
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        m.record_decision_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-decision', tid, '--outcome', 'failed']),
            now=1100,
        )
        m.record_decision_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-decision', tid, '--decision', 'rejected']),
            now=1900,
        )
        later = m.dispatch(self.args('--dry-run'), self.fake, now=1100 + m.BACKOFF_BASE_SECONDS + 1)
        self.assertEqual(later['selection']['agent'], 'primary')

    def test_thread_list_failure_is_bypassed(self):
        import contextlib
        import io
        m.dispatch(self.args(), self.fake, now=1000)

        def broken(*a):
            if a == ('thread', 'list'):
                raise m.DispatchError('server down')
            return self.fake(*a)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = m.dispatch(self.args('--task', 'another task'), broken, now=1100)
        self.assertFalse(result['dry_run'])
        self.assertIn('读取线程状态失败', stderr.getvalue())

    def test_spawn_failure_cools_candidate_so_rerun_switches(self):
        self.chain_config(['primary', 'specialist'])

        def flaky(*a):
            if a[:2] == ('thread', 'spawn') and a[a.index('--provider') + 1] == 'primary':
                self.calls.append(a)
                raise m.DispatchError('spawn failed')
            return self.fake(*a)

        with self.assertRaisesRegex(m.DispatchError, '该候选已冷却'):
            m.dispatch(self.args(), flaky, now=1000)
        rerun = m.dispatch(self.args(), flaky, now=1010)
        self.assertEqual(rerun['selection']['agent'], 'specialist')

    def test_concurrent_ledger_write_is_merged_not_overwritten(self):
        def racing(*a):
            if a[:2] == ('thread', 'spawn'):
                # 另一会话在本次 spawn 期间写入账本。
                other = m.load_ledger(self.ledger, strict=True)
                m.append_ledger_entry(other, {'id': 'other_session', 'ts': 999, 'provider': 'x', 'model': 'y', 'outcome': 'spawned'})
                m.save_ledger(self.ledger, other, strict=True)
            return self.fake(*a)

        result = m.dispatch(self.args(), racing, now=1000)
        ids = {e['id'] for e in m.load_ledger(self.ledger, strict=True)['entries']}
        self.assertEqual(ids, {'other_session', result['result']['thread']['id']})

    def test_concurrent_spawn_failure_keeps_later_cooldown(self):
        self.chain_config(['primary', 'specialist'])

        def racing(*a):
            if a[:2] == ('thread', 'spawn'):
                # 另一会话在本次 spawn 期间更晚地记下同一 provider 与模型的 spawn 失败。
                other = m.load_ledger(self.ledger, strict=True)
                other['cooldowns']['primary|fast-model'] = {
                    'provider': 'primary', 'model': 'fast-model', 'reason': 'spawn-failed',
                    'since': 1100, 'until': 1100 + m.SPAWN_COOLDOWN_SECONDS,
                }
                m.save_ledger(self.ledger, other, strict=True)
                raise m.DispatchError('spawn failed')
            return self.fake(*a)

        with self.assertRaisesRegex(m.DispatchError, '该候选已冷却'):
            m.dispatch(self.args(), racing, now=1000)
        later = m.dispatch(self.args('--dry-run'), self.fake, now=1000 + m.SPAWN_COOLDOWN_SECONDS + 50)
        self.assertEqual(later['selection']['agent'], 'specialist')

    def test_cooldown_survives_a_full_window_of_other_dispatches(self):
        self.chain_config(['primary', 'specialist'])
        now = 10 ** 6
        ledger = m.empty_ledger()
        ledger['entries'].append({'id': 'ancient', 'ts': now - m.RECENT_WINDOW_SECONDS - 100,
                                  'provider': 'other', 'model': 'x', 'outcome': 'completed'})
        # 长任务最早派出、刚刚失败；其后又有一整窗别的派发。
        ledger['entries'].append({'id': 'long', 'ts': now - 7200, 'provider': 'primary', 'model': 'fast-model',
                                  'outcome': 'failed', 'outcome_ts': now - 60})
        ledger['entries'] += [{'id': f'busy{i}', 'ts': now - 3600, 'provider': 'other', 'model': 'x',
                               'outcome': 'completed', 'outcome_ts': now - 3000} for i in range(m.MAX_LIVE_ENTRIES)]
        m.save_ledger(self.ledger, ledger)
        m.dispatch(self.args('--task', 'another task'), self.fake, now=now)
        after = m.load_ledger(self.ledger, strict=True)
        ids = {e['id'] for e in after['entries']}
        self.assertNotIn('ancient', ids)
        self.assertIn('long', ids)
        self.assertEqual(m.summarize_ledger(after, now=now)['rolled_up_entries'], 1)
        later = m.dispatch(self.args('--dry-run'), self.fake, now=now + 60)
        self.assertEqual(later['selection']['agent'], 'specialist')

    def test_fallback_from_automatically_cools_down_skipped_candidate(self):
        self.chain_config(['primary', 'specialist'])
        m.dispatch(self.args('--fallback-from', 'specialist'), self.fake, now=2000)
        # 下一笔未传 --fallback-from 的任务在 15 分钟内也应自动跳过刚刚失败的 primary
        nxt = m.dispatch(self.args('--dry-run'), self.fake, now=2100)
        self.assertEqual(nxt['selection']['agent'], 'specialist')

    def test_review_hooks_detect_simple_skew_and_failure_rates(self):
        for _ in range(5):
            res = m.dispatch(self.args('--difficulty', 'medium'), self.fake, now=3000)
            m.record_decision_command(
                m.parser().parse_args([
                    '--ledger', str(self.ledger),
                    '--record-decision', res['result']['thread']['id'],
                    '--outcome', 'failed_transient',
                    '--decision', 'rejected',
                ]),
                now=3005,
            )
        summary = m.summarize_ledger(m.load_ledger(self.ledger, strict=True), now=3010)
        hook_names = {h['hook'] for h in summary['review_hooks']}
        self.assertIn('simple_share_low', hook_names)
        self.assertIn('high_failure_rate', hook_names)
        self.assertIn('low_acceptance_rate', hook_names)


if __name__ == '__main__':
    unittest.main()
