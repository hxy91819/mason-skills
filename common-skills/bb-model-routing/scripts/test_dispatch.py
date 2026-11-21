"""离线验证派发行为；假 BB 边界不创建真实线程。"""
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

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
        self.retry_error = None
        self.turns = {}
        self.requests = {}
        self.provider_errors = {}
        self.providers =[{'id': name, 'available': True, 'capabilities': {'permissionModes': ['accept-edits']}} for name in ['primary', 'specialist', 'remote-provider']]

    def fake(self, *args):
        self.calls.append(args)
        if args == ('status',):
            return {'project': {'id': 'proj'}, 'thread': {'id': 'parent', 'environment': {'display': {'id': 'env'}}}}
        if args[:2] == ('environment', 'show'):
            return {'id': args[2], 'projectId': 'proj'}
        if args[:2] == ('thread', 'show'):
            # 真实 show 只给排队数，queuedWork 与 hasPendingInteraction 只在 list 里有。
            known = next((t for t in self.threads if t.get('id') == args[2]), {})
            return {'thread': {'id': args[2], 'projectId': 'proj', 'status': known.get('status', 'error'),
                               'environmentId': known.get('environmentId', 'env'),
                               'parentNotifications': known.get('parentNotifications'),
                               'queuedMessageCount': int(known.get('queuedWork') == 'waiting'),
                               'updatedAt': known.get('updatedAt')}}
        if args == ('thread', 'list'):
            return self.threads
        if args[:2] == ('thread', 'log'):
            events = list(self.requests.get(args[2], []))
            for at, status in self.turns.get(args[2], []):
                events.append({'seq': len(events) + 1, 'type': 'turn/started', 'createdAt': at * 1000 - 500, 'data': {}})
                events.append({'seq': len(events) + 1, 'type': 'turn/completed', 'createdAt': at * 1000,
                               'data': {'status': status}})
            events.extend(self.provider_errors.get(args[2], []))
            return events
        if args[:2] == ('provider-retry', 'status'):
            return {'retries': self.pending_retries.get(args[2], [])}
        if args[:2] == ('provider-retry', 'explain'):
            return {'threadId': args[2], 'diagnostic': self.retry_diagnostics.get(args[2])}
        if args[:2] == ('thread', 'retry'):
            if self.retry_error is not None:
                raise self.retry_error
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
            '--unknown', '测试用原因',
            *extra,
        ])

    def project_floor(self, minimum):
        config = m.yaml.safe_load(self.config.read_text())
        config['projects'] = {'proj': {'min_difficulty': minimum}}
        self.config.write_text(m.yaml.safe_dump(config))

    def test_project_floor_lifts_route_and_records_request(self):
        self.project_floor('medium')
        result = m.dispatch(self.args(), self.fake)
        selection = result['selection']
        self.assertEqual(selection['purpose'], 'work')
        self.assertEqual(selection['difficulty'], 'medium')
        self.assertEqual(selection['requested_difficulty'], 'simple')
        self.assertEqual(selection['model'], 'medium-model')
        self.assertTrue(selection['warnings'])
        entry = json.loads(self.ledger.read_text())['entries'][0]
        self.assertEqual(entry['purpose'], 'work')
        self.assertEqual((entry['difficulty'], entry['requested_difficulty']), ('medium', 'simple'))

    def test_review_skips_project_floor_and_records_purpose(self):
        self.project_floor('medium')
        result = m.dispatch(self.args('--purpose', 'review'), self.fake)
        selection = result['selection']
        self.assertEqual(selection['purpose'], 'review')
        self.assertEqual(selection['difficulty'], 'simple')
        self.assertEqual(selection['requested_difficulty'], 'simple')
        self.assertEqual(selection['model'], 'fast-model')
        self.assertNotIn('warnings', selection)
        entry = json.loads(self.ledger.read_text())['entries'][0]
        self.assertEqual((entry['purpose'], entry['difficulty']), ('review', 'simple'))
        event = json.loads(m.events_path(self.ledger).read_text().splitlines()[-1])
        self.assertEqual((event['event'], event['purpose']), ('dispatch', 'review'))

    def test_unconfigured_project_keeps_request(self):
        self.config.write_text(self.config.read_text() + '\nprojects: {other: {min_difficulty: complex}}\n')
        selection = m.dispatch(self.args('--dry-run'), self.fake)['selection']
        self.assertEqual(selection['difficulty'], 'simple')
        self.assertNotIn('warnings', selection)

    def test_project_floor_dry_run_warnings_reach_json_and_stderr(self):
        self.project_floor('medium')
        dispatch = m.dispatch
        with mock.patch.object(m, 'dispatch', side_effect=lambda args: dispatch(args, self.fake)), mock.patch('sys.argv', ['bb-dispatch', '--config', str(self.config), '--ledger', str(self.ledger), '--dry-run', '--difficulty', 'simple', '--task', 'preview']), mock.patch('sys.stdout', new_callable=io.StringIO) as out, mock.patch('sys.stderr', new_callable=io.StringIO) as err:
            self.assertEqual(m.main(), 0)
        selection = json.loads(out.getvalue())['selection']
        self.assertEqual(selection['difficulty'], 'medium')
        self.assertIn(selection['warnings'][0], err.getvalue())
        self.assertEqual(self.spawn_counter, 0)
        self.assertFalse(self.ledger.exists())

    def test_invalid_project_floor_fails_without_spawn(self):
        self.project_floor('invalid')
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertEqual(self.spawn_counter, 0)

    def test_dry_run_never_spawns_and_preserves_task(self):
        result = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertEqual(result['selection']['agent'], 'primary')
        prompt = result['argv'][result['argv'].index('--prompt') + 1]
        self.assertTrue(prompt.startswith(self.args().task + m.REPORT_PROTOCOL_ANCHOR))
        self.assertIn('--parent-thread', result['argv'])
        self.assertIn('parent', result['argv'])
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_quiet_parent_notifications_spawn_with_tell_protocol(self):
        def prompt(result):
            return result['argv'][result['argv'].index('--prompt') + 1]

        default = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertNotIn('--parent-notifications', default['argv'])
        self.assertTrue(prompt(default).endswith(m.REPORT_PROTOCOL))

        quiet = m.dispatch(self.args('--parent-notifications', 'stuck', '--dry-run'), self.fake)
        argv = quiet['argv']
        self.assertEqual(argv[argv.index('--parent-notifications') + 1], 'stuck')
        self.assertTrue(prompt(quiet).endswith(m.QUIET_REPORT_PROTOCOL))
        self.assertEqual(quiet['selection']['parent_notifications'], 'stuck')
        # 续派时从子线程首条消息复制任务文本：去掉旧回报方式，按当前模式重新附加一次。
        copied = m.dispatch(self.args('--task', prompt(quiet), '--parent-notifications', 'stuck', '--dry-run'), self.fake)
        self.assertEqual(prompt(copied), prompt(quiet))

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

    def test_workspace_path_in_another_project_keeps_parent_and_report_protocol(self):
        workspace = Path(self.temp.name) / 'workspace'
        workspace.mkdir()
        result = m.dispatch(self.args('--project', 'other', '--environment', str(workspace), '--dry-run'), self.fake)
        self.assertEqual(result['argv'][result['argv'].index('--parent-thread') + 1], 'parent')
        self.assertEqual(result['argv'][result['argv'].index('--prompt') + 1],
                         self.args().task + m.REPORT_PROTOCOL_ANCHOR + m.REPORT_PROTOCOL)

    def test_environment_in_another_project_keeps_parent_and_report_protocol(self):
        def other_project(*args):
            if args[:2] == ('environment', 'show'):
                return {'id': args[2], 'projectId': 'other'}
            return self.fake(*args)

        with mock.patch.dict(os.environ, {'BB_THREAD_ID': 'parent'}):
            result = m.dispatch(
                self.args('--project', 'other', '--environment', 'env_other', '--dry-run'), other_project
            )
        self.assertEqual(result['selection']['project'], 'other')
        self.assertEqual(result['argv'][result['argv'].index('--parent-thread') + 1], 'parent')
        self.assertEqual(result['argv'][result['argv'].index('--prompt') + 1],
                         self.args().task + m.REPORT_PROTOCOL_ANCHOR + m.REPORT_PROTOCOL)

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

    def test_codex_permission_defaults_and_explicit_overrides(self):
        for explicit, agent_permission, global_permission, expected in [
            (None, None, None, 'auto'),
            (None, None, 'full', 'full'),
            (None, 'auto', 'full', 'auto'),
            ('accept-edits', 'auto', 'full', 'accept-edits'),
        ]:
            with self.subTest(explicit=explicit, agent=agent_permission, global_permission=global_permission):
                cfg = m.yaml.safe_load(self.config.read_text())
                cfg.pop('permission_mode', None)
                if global_permission:
                    cfg['permission_mode'] = global_permission
                if agent_permission:
                    cfg['agents']['primary']['permission_mode'] = agent_permission
                self.providers[0]['pluginId'] = 'provider-codex'
                self.providers[0]['capabilities']['permissionModes'] = ['accept-edits', 'auto', 'full']
                extra = ['--permission-mode', explicit] if explicit else []
                self.config.write_text(m.yaml.safe_dump(cfg))
                result = m.dispatch(self.args('--dry-run', *extra), self.fake)
                self.assertEqual(result['selection']['permission_mode'], expected)
                self.assertEqual(result['argv'][result['argv'].index('--permission-mode') + 1], expected)

    def test_permission_mismatch_does_not_escalate(self):
        self.providers[0]['capabilities']['permissionModes'] = ['full']
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args(), self.fake)
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))
        result = m.dispatch(self.args('--permission-mode', 'full', '--dry-run'), self.fake)
        self.assertEqual(result['selection']['permission_mode'], 'full')

    def enable_fast_catalog(self, model_tiers=None):
        for provider in self.providers:
            provider['serviceTiers'] = [{'id': 'default'}, {'id': 'fast'}]
        original = self.fake

        def with_tiers(*args):
            if args[:2] == ('provider', 'models'):
                models = original(*args)
                for model in models:
                    if model_tiers is not None:
                        model['supportedServiceTiers'] = [{'id': tier} for tier in model_tiers]
                return models
            return original(*args)

        return with_tiers

    def test_fast_defaults_off_and_true_enables_it(self):
        result = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertIsNone(result['selection']['service_tier'])
        self.assertNotIn('--service-tier', result['argv'])
        omitted = m.dispatch(self.args('--dry-run'), self.enable_fast_catalog())
        self.assertEqual(omitted['selection']['service_tier'], 'default')
        config = m.yaml.safe_load(self.config.read_text())
        config['fast'] = True
        self.config.write_text(m.yaml.safe_dump(config))
        enabled = m.dispatch(self.args('--dry-run'), self.enable_fast_catalog())
        self.assertEqual(enabled['selection']['service_tier'], 'fast')
        self.assertEqual(enabled['argv'][enabled['argv'].index('--service-tier') + 1], 'fast')

    def test_fast_false_passes_default_when_supported_and_omits_when_unsupported(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['fast'] = False
        self.config.write_text(m.yaml.safe_dump(config))
        unsupported = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertIsNone(unsupported['selection']['service_tier'])
        self.assertNotIn('--service-tier', unsupported['argv'])
        supported = m.dispatch(self.args('--dry-run'), self.enable_fast_catalog())
        self.assertEqual(supported['selection']['service_tier'], 'default')
        self.assertEqual(supported['argv'][supported['argv'].index('--service-tier') + 1], 'default')

    def test_fast_passes_default_for_models_that_omit_fast(self):
        result = m.dispatch(self.args('--dry-run'), self.enable_fast_catalog(model_tiers=['default']))
        self.assertEqual(result['selection']['service_tier'], 'default')
        self.assertEqual(result['argv'][result['argv'].index('--service-tier') + 1], 'default')

    def test_environment_fast_override_and_invalid_value(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['fast'] = True
        config['environments']['env'] = {'fast': False}
        self.config.write_text(m.yaml.safe_dump(config))
        result = m.dispatch(self.args('--environment', 'env', '--dry-run'), self.enable_fast_catalog())
        self.assertEqual(result['selection']['service_tier'], 'default')
        self.assertEqual(result['argv'][result['argv'].index('--service-tier') + 1], 'default')
        config['environments']['env']['fast'] = 'yes'
        self.config.write_text(m.yaml.safe_dump(config))
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args('--environment', 'env', '--dry-run'), self.enable_fast_catalog())

    def test_agent_fast_override_and_invalid_value(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['fast'] = True
        config['agents']['primary']['fast'] = False
        self.config.write_text(m.yaml.safe_dump(config))
        result = m.dispatch(self.args('--dry-run'), self.enable_fast_catalog())
        self.assertEqual(result['selection']['service_tier'], 'default')
        self.assertEqual(result['argv'][result['argv'].index('--service-tier') + 1], 'default')

        config['fast'] = False
        config['agents']['primary']['fast'] = True
        self.config.write_text(m.yaml.safe_dump(config))
        result = m.dispatch(self.args('--dry-run'), self.enable_fast_catalog())
        self.assertEqual(result['selection']['service_tier'], 'fast')
        self.assertEqual(result['argv'][result['argv'].index('--service-tier') + 1], 'fast')

        config['agents']['primary']['fast'] = 'invalid'
        self.config.write_text(m.yaml.safe_dump(config))
        with self.assertRaises(m.DispatchError) as ctx:
            m.dispatch(self.args('--dry-run'), self.enable_fast_catalog())
        self.assertIn("agents.primary.fast 必须是 true 或 false", str(ctx.exception))

    def test_fast_cli_is_rejected(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.args('--fast')

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
                 ('🟩 🟨 🟥 💚 💛 ❤️ [Agent] 修复登录', '修复登录'),
                 ('[Agent]', '任务'),
                 ('🟢', '任务'),
                 ('🟨', '任务'),
                 ('❤️', '任务'),
                 ('📒', '任务'),
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

    def test_codexm_book_titles_across_difficulties(self):
        for alias in ('codexm', 'codex-m', 'custom_agent'):
            for difficulty, prefix in [('simple', '📗'), ('medium', '📒'), ('complex', '📕')]:
                with self.subTest(alias=alias, difficulty=difficulty):
                    config = m.yaml.safe_load(self.config.read_text())
                    config['agents'][alias] = {
                        'provider': 'primary',
                        'routes': {difficulty: {'model': 'fast-model', 'reasoning': 'low'}}
                    }
                    if alias == 'custom_agent':
                        config['agents'][alias]['shape'] = 'book'
                    config['defaults'][difficulty] = alias
                    self.config.write_text(m.yaml.safe_dump(config))
                    result = m.dispatch(self.args('--difficulty', difficulty, '--title', '📒 测试任务', '--dry-run'), self.fake)
                    self.assertEqual(result['selection']['title'], prefix + ' 测试任务')

    def test_shaped_title_prefixes_by_agent_and_shape(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['codexl'] = {
            'provider': 'primary',
            'routes': {'medium': {'model': 'medium-model', 'reasoning': 'low'}}
        }
        config['agents']['codexb'] = {
            'provider': 'primary',
            'routes': {'complex': {'model': 'fast-model', 'reasoning': 'low'}}
        }
        config['agents']['custom_agent'] = {
            'provider': 'primary',
            'shape': 'heart',
            'routes': {'simple': {'model': 'fast-model', 'reasoning': 'low'}}
        }
        config['defaults']['medium'] = 'codexl'
        config['defaults']['complex'] = 'codexb'
        config['defaults']['simple'] = 'custom_agent'
        self.config.write_text(m.yaml.safe_dump(config))

        res_l = m.dispatch(self.args('--difficulty', 'medium', '--title', '测试任务', '--dry-run'), self.fake)
        self.assertEqual(res_l['selection']['title'], '🟨 测试任务')

        res_b = m.dispatch(self.args('--difficulty', 'complex', '--title', '测试任务', '--dry-run'), self.fake)
        self.assertEqual(res_b['selection']['title'], '❤️ 测试任务')

        res_custom = m.dispatch(self.args('--difficulty', 'simple', '--title', '测试任务', '--dry-run'), self.fake)
        self.assertEqual(res_custom['selection']['title'], '💚 测试任务')

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

    def complex_args(self, *extra):
        return m.parser().parse_args(['--config', str(self.config), '--ledger', str(self.ledger),
                                      '--difficulty', 'complex', '--task', '裁决方案', *extra])

    def test_direct_medium_or_complex_needs_no_escalation_or_reason(self):
        long_task = '细化步骤' * 700
        for diff in ('medium', 'complex'):
            args = self.args('--difficulty', diff, '--task', long_task)
            args.unknown = None
            result = m.dispatch(args, self.fake, now=1000)
            self.assertEqual(result['selection']['difficulty'], diff)
            self.assertNotIn('escalated_from', result['selection'])

    def test_optional_reason_and_escalation_are_recorded(self):
        unknown = '不知道故障在网关、调度还是存储哪一层' * 10
        stated = m.dispatch(self.complex_args('--unknown', unknown), self.fake, now=1000)
        self.assertEqual(stated['selection']['unknown'], unknown)
        escalated = m.dispatch(self.complex_args('--escalate-from', 'thr_prev_failed'), self.fake, now=1001)
        self.assertIn(('thread', 'show', 'thr_prev_failed'), self.calls)
        entries = {e['id']: e for e in m.load_ledger(self.ledger, strict=True)['entries']}
        self.assertEqual(entries[stated['result']['thread']['id']]['unknown'], unknown[:m.UNKNOWN_MAX_CHARS])
        self.assertEqual(entries[escalated['result']['thread']['id']]['escalated_from'], 'thr_prev_failed')
        self.assertNotIn('unknown', entries[escalated['result']['thread']['id']])

    def test_high_complex_share_raises_no_warning(self):
        ledger = m.empty_ledger()
        for idx in range(10):
            m.append_ledger_entry(ledger, {
                'id': f'thr_{idx}', 'ts': 900 + idx, 'parent_thread': 'parent', 'difficulty': 'complex',
                'agent': 'primary', 'provider': 'primary', 'model': 'fast-model', 'reasoning': 'max',
                'outcome': 'completed', 'decision': 'accepted',
            })
        m.save_ledger(self.ledger, ledger)
        result = m.dispatch(self.args(), self.fake, now=1000)
        self.assertNotIn('warnings', result['selection'])
        self.assertEqual(m.summarize_ledger(m.load_ledger(self.ledger, strict=True), now=1000)['review_hooks'], [])

    def test_review_warnings_also_reach_stderr(self):
        receipt = {'dry_run': False, 'selection': {'warnings': ['分档偏斜提醒']}, 'result': {'thread': {'id': 'thr_x'}}}
        argv = ['bb-dispatch', '--config', str(self.config), '--difficulty', 'simple', '--task', 't']
        with mock.patch.object(m, 'dispatch', return_value=receipt), mock.patch('sys.argv', argv), \
                mock.patch('sys.stdout', new_callable=io.StringIO) as out, \
                mock.patch('sys.stderr', new_callable=io.StringIO) as err:
            self.assertEqual(m.main(), 0)
        self.assertEqual(json.loads(out.getvalue())['result']['thread']['id'], 'thr_x')
        self.assertIn('提醒：分档偏斜提醒', err.getvalue())

    def test_ledger_records_minimal_facts_and_overwrites_on_repeat_decision(self):
        res = m.dispatch(self.args('--task', 'SENSITIVE_SECRET_TOKEN_123'), self.fake, now=1000)
        tid = res['result']['thread']['id']
        raw_ledger = self.ledger.read_text()
        self.assertNotIn('SENSITIVE_SECRET_TOKEN_123', raw_ledger)
        self.assertNotIn('SENSITIVE_SECRET_TOKEN_123', m.events_path(self.ledger).read_text())
        # 未知 ID 拒绝
        with self.assertRaisesRegex(m.DispatchError, '拒绝回写未知 ID'):
            m.record_outcome_command(
                m.parser().parse_args(['--ledger', str(self.ledger), '--record-outcome', 'thr_unknown', '--outcome', 'completed']),
                now=1010,
            )
        # 重复回写同一 ID 覆盖而非追加；旧参数名仍可用
        for flag, outcome, now in (('--record-outcome', 'failed', 1010), ('--record-decision', 'completed', 1020)):
            m.record_outcome_command(
                m.parser().parse_args(['--ledger', str(self.ledger), flag, tid, '--outcome', outcome]), now=now)
        ledger_data = m.load_ledger(self.ledger, strict=True)
        self.assertEqual(len(ledger_data['entries']), 1)
        self.assertEqual(ledger_data['entries'][0]['outcome'], 'completed')
        self.assertNotIn('decision', ledger_data['entries'][0])
        summary = m.summarize_ledger(ledger_data, now=1020)
        self.assertEqual(summary['total_dispatches'], 1)
        self.assertEqual(summary['by_agent']['primary']['outcomes']['completed'], 1)

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
            }, max_live=200)
        self.assertEqual(len(ledger['entries']), 200)
        summary = m.summarize_ledger(ledger, now=2000)
        self.assertEqual(summary['live_entries'], 200)
        self.assertEqual(summary['rolled_up_entries'], 5)
        self.assertEqual(summary['total_dispatches'], 205)
        self.assertEqual(summary['by_agent']['primary']['total'], 205)
        self.assertEqual(summary['by_agent']['primary']['outcomes']['completed'], 205)

    def test_circuit_breaker_skips_cooled_down_candidate_and_recovers(self):
        self.chain_config(['primary', 'specialist'])
        first = m.dispatch(self.args(), self.fake, now=1000)
        self.assertEqual(first['selection']['agent'], 'primary')
        tid = first['result']['thread']['id']
        # 旧版手动回写的失败类型照样计入，但不再按类型定时长。
        m.record_outcome_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-outcome', tid, '--outcome', 'failed_quota']),
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

    def turn_ended(self, tid, at, status='failed'):
        """线程在 at 秒结束一个回合：日志多一条结束事件，线程停在 error 或空闲。"""
        self.turns.setdefault(tid, []).append((at, status))
        thread = next((t for t in self.threads if t['id'] == tid), None)
        if thread is None:
            thread = {'id': tid, 'queuedWork': 'none'}
            self.threads.append(thread)
        thread.update(status='error' if status == 'failed' else 'idle', updatedAt=at * 1000)

    def ledger_entry(self, tid):
        return next(e for e in m.load_ledger(self.ledger, strict=True)['entries'] if e['id'] == tid)

    def logged(self, kind):
        lines = m.events_path(self.ledger).read_text().splitlines()
        return [event for event in map(json.loads, lines) if event['event'] == kind]

    def provider_error(self, tid, detail, at=1090, http=429):
        """线程日志里的 provider/error。detail 用真实事故的 JSON，而不是报错句子。"""
        self.provider_errors.setdefault(tid, []).append({
            'type': 'provider/error', 'createdAt': at * 1000,
            'data': {
                'message': 'Provider error', 'detail': detail,
                'errorInfo': {'category': 'rate-limit', 'providerCode': None, 'httpStatusCode': http},
            },
        })

    def test_on_failure_retries_in_session_then_cools_provider_and_model(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['defaults']['medium'] = ['specialist', 'primary']
        config['defaults']['simple'] = ['specialist', 'primary']
        self.config.write_text(m.yaml.safe_dump(config))
        tid = m.dispatch(self.args('--difficulty', 'medium'), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(tid, 1095)
        # 报错先在原会话退避重试，期间不影响新派发；每次重试执行后又失败，才安排下一次。
        at, delays = 1100, []
        for _ in range(m.SESSION_RETRY_LIMIT):
            delays.append(self.on_failure(tid, now=at)['delay_seconds'])
            at += delays[-1] + 10
            self.turn_ended(tid, at - 5)
        self.assertEqual(delays, [60, 120, 240])
        sent = [c[c.index('--send-at') + 1] for c in self.calls if c[:2] == ('thread', 'retry')]
        self.assertEqual(sent, ['60s', '120s', '240s'])
        self.assertEqual(m.dispatch(self.args('--task', 'other', '--dry-run'), self.fake, now=1200)['selection']['agent'], 'specialist')
        # 重试用尽才记失败；冷却按 provider 与模型计，别的档位同样跳过。
        cooled = self.on_failure(tid, now=at)
        self.assertEqual(cooled['action'], 'cooled')
        self.assertEqual((cooled['cooldown']['provider'], cooled['cooldown']['level']), ('specialist', 1))
        self.assertEqual(m.dispatch(self.args('--task', 'other', '--dry-run'), self.fake, now=at + 100)['selection']['agent'], 'primary')
        self.assertEqual(m.dispatch(self.args('--difficulty', 'medium', '--dry-run'), self.fake, now=at + 100)['selection']['agent'], 'primary')
        later = m.dispatch(self.args('--task', 'other', '--dry-run'), self.fake, now=at + m.BACKOFF_BASE_SECONDS + 1)
        self.assertEqual(later['selection']['agent'], 'specialist')

    def test_redispatch_recovers_first_task_and_requested_difficulty_after_quota_cooldown(self):
        self.project_floor('medium')
        config = m.yaml.safe_load(self.config.read_text())
        config['defaults']['medium'] = ['primary', 'specialist']
        self.config.write_text(m.yaml.safe_dump(config))
        task = '  目标\n\n保留完整任务 $(literal)\n'
        original = m.dispatch(self.args('--task', task, '--environment', 'env_other',
                                        '--parent-notifications', 'stuck'), self.fake, now=1000)
        tid = original['result']['thread']['id']
        spawn = next(call for call in self.calls if call[:2] == ('thread', 'spawn'))
        prompt = spawn[spawn.index('--prompt') + 1]
        self.requests[tid] = [
            {'type': 'thread/created', 'data': {}},
            {'type': 'client/turn/requested', 'data': {'source': 'spawn', 'input': [
                {'type': 'text', 'text': prompt[:7]}, {'type': 'text', 'text': prompt[7:]},
            ]}},
            {'type': 'client/turn/requested', 'data': {'source': 'message', 'input': [
                {'type': 'text', 'text': '后续消息不能成为任务正文'},
            ]}},
        ]
        self.turn_ended(tid, 1095)
        self.threads[0].update(environmentId='env_other', parentNotifications='stuck')
        self.retry_diagnostics[tid] = {'decision': {'kind': 'decline', 'reason': 'not-resettable'}}
        self.assertEqual(self.on_failure(tid, now=1100)['action'], 'cooled')

        argv = ['bb-dispatch', '--config', str(self.config), '--ledger', str(self.ledger), '--redispatch', tid]
        dispatch = m.dispatch
        with mock.patch.object(m, 'dispatch', side_effect=lambda args: dispatch(args, self.fake, now=1200)), \
                mock.patch('sys.argv', argv), mock.patch('sys.stdout', new_callable=io.StringIO) as out, \
                mock.patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(m.main(), 0)
        result = json.loads(out.getvalue())
        selection = result['selection']
        self.assertEqual((selection['requested_difficulty'], selection['difficulty']), ('simple', 'medium'))
        self.assertEqual((selection['provider'], selection['escalated_from']), ('remote-provider', tid))
        respawn = [call for call in self.calls if call[:2] == ('thread', 'spawn')][-1]
        self.assertEqual(respawn[respawn.index('--environment') + 1], 'env_other')
        self.assertEqual(respawn[respawn.index('--parent-notifications') + 1], 'stuck')
        self.assertEqual(respawn[respawn.index('--prompt') + 1], task + m.REPORT_PROTOCOL_ANCHOR + m.QUIET_REPORT_PROTOCOL)
        self.assertIn(('thread', 'log', tid, '--all'), self.calls)
        self.assertEqual(self.ledger_entry(result['result']['thread']['id'])['escalated_from'], tid)
        self.assertNotIn('保留完整任务', self.ledger.read_text())

    def test_redispatch_keeps_review_purpose_exempt_from_project_floor(self):
        self.project_floor('medium')
        tid = m.dispatch(self.args('--purpose', 'review'), self.fake, now=1000)['result']['thread']['id']
        spawn = next(call for call in self.calls if call[:2] == ('thread', 'spawn'))
        self.requests[tid] = [{'type': 'client/turn/requested', 'data': {'source': 'spawn', 'input': [
            {'type': 'text', 'text': spawn[spawn.index('--prompt') + 1]},
        ]}}]
        argv = ['bb-dispatch', '--config', str(self.config), '--ledger', str(self.ledger), '--redispatch', tid]
        dispatch = m.dispatch
        with mock.patch.object(m, 'dispatch', side_effect=lambda args: dispatch(args, self.fake, now=1200)), \
                mock.patch('sys.argv', argv), mock.patch('sys.stdout', new_callable=io.StringIO) as out, \
                mock.patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(m.main(), 0)
        selection = json.loads(out.getvalue())['selection']
        self.assertEqual((selection['purpose'], selection['difficulty']), ('review', 'simple'))

    def test_redispatch_requires_known_difficulty_and_initial_spawn_text(self):
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.requests[tid] = [{'type': 'client/turn/requested', 'data': {'source': 'message', 'input': [
            {'type': 'text', 'text': '仅有后续消息'},
        ]}}]
        prefix = ['--config', str(self.config), '--ledger', str(self.ledger), '--redispatch']
        for source_id, message in [(tid, '首轮派发任务文本'), ('missing', '有效原始难度')]:
            with self.subTest(source_id=source_id), self.assertRaisesRegex(m.DispatchError, message):
                m.dispatch(m.parser().parse_args([*prefix, source_id]), self.fake, now=1100)
        self.assertEqual(self.spawn_counter, 1)

    def test_on_failure_waits_while_a_retry_is_queued_but_not_for_deferred_messages(self):
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        # 父线程的消息排在报错线程上，要等线程被重试才送出，不算已有重试。
        self.threads = [{'id': tid, 'status': 'error', 'queuedWork': 'waiting', 'updatedAt': 1095 * 1000}]
        at = 1100
        for attempt in range(1, m.SESSION_RETRY_LIMIT + 1):
            self.assertEqual(self.on_failure(tid, now=at)['attempt'], attempt)
            # 重复调用时上次安排的重试还没执行：只等待，不再安排，用到第 3 次也不冷却。
            self.assertEqual(self.on_failure(tid, now=at + 5)['action'], 'waiting')
            at += 60 * 2 ** (attempt - 1) + 10
            self.turn_ended(tid, at - 5)
        self.assertEqual(len([c for c in self.calls if c[:2] == ('thread', 'retry')]), m.SESSION_RETRY_LIMIT)
        self.assertEqual((self.ledger_entry(tid)['outcome'], self.ledger_entry(tid)['retries']), ('spawned', 3))
        # BB 回复这个回合已有排队的重试（例如用户在界面上点了重试）：同样等待，不冷却。
        other = m.dispatch(self.args('--task', 'other'), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(other, 1095)
        self.retry_error = m.DispatchError('bb thread retry 失败：retry_already_queued：', code='retry_already_queued')
        self.assertEqual(self.on_failure(other, now=1100)['action'], 'waiting')
        self.assertEqual((self.ledger_entry(other)['outcome'], self.ledger_entry(other).get('retries')), ('spawned', None))

    def test_bb_json_error_code_reaches_the_caller(self):
        envelope = '{"ok": false, "error": {"code": "retry_already_queued", "message": "turn already has a retry queued"}}'
        failed = m.subprocess.CompletedProcess([], 1, stdout=envelope, stderr='')
        with mock.patch.object(m.subprocess, 'run', return_value=failed):
            with self.assertRaises(m.DispatchError) as caught:
                m.bb('thread', 'retry', 'thr_x')
        self.assertEqual(caught.exception.code, 'retry_already_queued')
        self.assertIn('turn already has a retry queued', str(caught.exception))

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
        self.turn_ended(tid, 1095)
        self.assertEqual(self.on_failure(tid, now=1100)['attempt'], 1)
        # 原会话重试成功，其间没有别的派发补记完成；之后再报错仍是新的一次故障，从第 1 次算起。
        self.turn_ended(tid, 1170, 'completed')
        self.turn_ended(tid, 1295)
        self.assertEqual(self.on_failure(tid, now=1300)['attempt'], 1)
        self.assertEqual([(e['thread'], e['retries']) for e in self.logged('recovered')], [(tid, 1)])
        # 原会话无法重试时直接冷却。
        self.turn_ended(tid, 1395)
        self.retry_error = m.DispatchError('bb thread retry 失败：thread_not_failed：', code='thread_not_failed')
        self.assertEqual(self.on_failure(tid, now=1400)['action'], 'cooled')
        self.assertEqual([e['reason'] for e in self.logged('cooled')], ['retry-impossible'])

    def test_retrying_a_reused_thread_keeps_its_earlier_success(self):
        self.chain_config(['primary', 'specialist'])
        failed = m.dispatch(self.args('--task', 'failed'), self.fake, now=1000)['result']['thread']['id']
        reused = m.dispatch(self.args('--task', 'reused'), self.fake, now=1000)['result']['thread']['id']
        m.record_outcome_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-outcome', failed, '--outcome', 'failed']),
            now=1010,
        )
        self.threads = [{'id': reused, 'status': 'idle', 'queuedWork': 'none', 'updatedAt': 1050 * 1000}]
        # 之后的一次成功清零了 primary 的冷却。
        self.assertEqual(m.dispatch(self.args('--task', 'next'), self.fake, now=1060)['selection']['agent'], 'primary')
        # 做完的线程续用后报错：原会话重试期间终态不动，那次成功照样算数，旧失败不复活冷却。
        self.turn_ended(reused, 1095)
        self.assertEqual(self.on_failure(reused, now=1100)['action'], 'retry-scheduled')
        self.assertEqual(m.dispatch(self.args('--task', 'later', '--dry-run'), self.fake, now=1150)['selection']['agent'], 'primary')
        # 重试成功后，下一次派发补记恢复并把重试次数清零。
        self.turn_ended(reused, 1170, 'completed')
        m.dispatch(self.args('--task', 'more'), self.fake, now=1300)
        self.assertEqual((self.ledger_entry(reused)['outcome'], self.ledger_entry(reused).get('retries')), ('completed', None))
        self.assertEqual([(e['thread'], e['retries']) for e in self.logged('recovered')], [(reused, 1)])

    def test_review_log_shows_retries_recoveries_and_cooldowns(self):
        self.chain_config(['primary', 'specialist'])
        flaky, broken, given_up, hopeless = (
            m.dispatch(self.args('--task', task), self.fake, now=1000)['result']['thread']['id']
            for task in ('flaky', 'broken', 'given up', 'hopeless'))
        self.turn_ended(flaky, 1095)
        self.turn_ended(broken, 1095)
        # flaky 在原会话第 2 次重试后恢复；broken 随后重试用尽、冷却。
        self.on_failure(flaky, now=1100)
        self.turn_ended(flaky, 1102)
        self.on_failure(flaky, now=1104)
        self.turn_ended(flaky, 1106, 'completed')
        for index in range(m.SESSION_RETRY_LIMIT):
            self.on_failure(broken, now=1110 + 10 * index)
            self.turn_ended(broken, 1115 + 10 * index)
        self.on_failure(broken, now=1110 + 10 * m.SESSION_RETRY_LIMIT)
        # 原会话重试过一次后 BB 放弃的也算重试没救回来；一上来 BB 就放弃的不算原会话重试的收场。
        self.turn_ended(given_up, 1145)
        self.on_failure(given_up, now=1150)
        self.turn_ended(given_up, 1155)
        self.turn_ended(hopeless, 1155)
        for tid in (given_up, hopeless):
            self.retry_diagnostics[tid] = {'decision': {'kind': 'decline', 'reason': 'attempts-exhausted'}}
            self.on_failure(tid, now=1160)
        self.assertEqual(m.dispatch(self.args('--task', 'next'), self.fake, now=1400)['selection']['agent'], 'specialist')
        m.dispatch(self.args('--task', 'preview', '--dry-run'), self.fake, now=1500)
        review = m.summarize_events(self.ledger, now=1500)
        self.assertEqual((review['dispatches'], review['diverted_dispatches'], review['retries']), (5, 1, 6))
        self.assertEqual((review['recovered'], review['recovered_by_attempt']), (1, {'2': 1}))
        self.assertEqual((review['cooled'], review['cooled_by_reason']), (3, {'exhausted': 1, 'bb-gave-up': 2}))
        self.assertEqual((review['retried_then_cooled'], review['retry_recovery_rate']), (2, round(1 / 3, 4)))
        self.assertEqual(review['by_target']['primary|fast-model']['max_level'], 1)
        self.assertEqual(sum(day['retries'] for day in review['daily']), 6)

    def test_review_log_stays_bounded_and_keeps_the_newest_events(self):
        with mock.patch.object(m, 'EVENTS_MAX_BYTES', 2000):
            for index in range(200):
                m.append_events(self.ledger, [{'ts': index, 'event': 'retry', 'thread': f't{index}'}])
        log = m.events_path(self.ledger)
        self.assertLessEqual(log.stat().st_size, 2000)
        threads = [json.loads(line)['thread'] for line in log.read_text().splitlines()]
        self.assertEqual(threads[-1], 't199')
        self.assertNotIn('t0', threads)

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

    def test_review_hooks_detect_failure_rates_without_simple_quota(self):
        for _ in range(5):
            res = m.dispatch(self.args('--difficulty', 'medium'), self.fake, now=3000)
            m.record_outcome_command(
                m.parser().parse_args([
                    '--ledger', str(self.ledger),
                    '--record-outcome', res['result']['thread']['id'],
                    '--outcome', 'failed_transient',
                ]),
                now=3005,
            )
        summary = m.summarize_ledger(m.load_ledger(self.ledger, strict=True), now=3010)
        hook_names = {h['hook'] for h in summary['review_hooks']}
        self.assertNotIn('simple_share_low', hook_names)
        self.assertIn('high_failure_rate', hook_names)

    def test_dispatch_event_keeps_chain_facts_without_task_text(self):
        m.dispatch(self.args('--task', 'SECRET_TASK_TEXT', '--escalate-from', 'thr_prev'), self.fake, now=1000)
        event = [json.loads(l) for l in m.events_path(self.ledger).read_text().splitlines()][-1]
        self.assertEqual(event['event'], 'dispatch')
        self.assertEqual(event['escalated_from'], 'thr_prev')
        self.assertEqual(event['unknown'], '测试用原因')
        self.assertIn('task_chars', event)
        self.assertNotIn('requested_difficulty', event)
        self.assertNotIn('SECRET_TASK_TEXT', json.dumps(event, ensure_ascii=False))

    def test_followups_lists_parent_and_user_messages_after_first_delivery(self):
        events = [
            {'ts': 100, 'event': 'dispatch', 'thread': 'thr_old', 'difficulty': 'simple', 'agent': 'a', 'model': 'm'},
            {'ts': 190000, 'event': 'dispatch', 'thread': 'thr_new', 'difficulty': 'medium', 'agent': 'b', 'model': 'n'},
            {'ts': 190500, 'event': 'dispatch', 'thread': 'thr_stopped', 'difficulty': 'simple', 'agent': 'a', 'model': 'm'},
            {'ts': 191000, 'event': 'dispatch', 'thread': 'thr_retry', 'difficulty': 'medium', 'agent': 'b', 'model': 'n',
             'escalated_from': 'thr_stopped'},
        ]
        m.events_path(self.ledger).write_text(''.join(json.dumps(e) + '\n' for e in events))

        def req(seq, initiator, text, sender=None):
            return {'seq': seq, 'type': 'client/turn/requested',
                    'data': {'initiator': initiator, 'senderThreadId': sender, 'input': [{'type': 'text', 'text': text}]}}
        log = [
            req(1, 'user', '原始任务'),
            req(2, 'agent', '交付前的补充', 'thr_parent'),
            {'seq': 3, 'type': 'turn/completed', 'data': {'status': 'completed'}},
            req(4, 'agent', '[bb message from thread:thr_parent] 还有一处要改', 'thr_parent'),
            req(5, 'agent', '别的线程发来的', 'thr_other'),
            req(6, 'system', '[bb system] @thread:thr_child completed'),
            req(7, 'user', '[bb_long_task] 合入结束'),
            req(8, 'user', '用户直接纠正'),
        ]

        stopped_log = [
            req(1, 'user', '原始任务'),
            {'seq': 2, 'type': 'system/thread/interrupted', 'data': {'reason': 'manual-stop'}},
            {'seq': 3, 'type': 'turn/completed', 'data': {'status': 'interrupted'}},
            req(4, 'agent', '已停掉并改派', 'thr_parent'),
        ]

        def call(*argv):
            if argv[:2] == ('thread', 'list'):
                return [{'id': 'thr_new', 'parentThreadId': 'thr_parent', 'title': '🟡 修复'},
                        {'id': 'thr_stopped', 'parentThreadId': 'thr_parent'}, {'id': 'thr_retry'}]
            if argv[:2] == ('thread', 'log'):
                return {'thr_new': log, 'thr_stopped': stopped_log}.get(argv[2], [])
            raise AssertionError(argv)
        args = m.parser().parse_args(['--ledger', str(self.ledger), '--followups', '--days', '1'])
        result = m.followups_command(args, call=call, now=200000)
        rows = {r['thread']: r for r in result['rows']}
        self.assertEqual(set(rows), {'thr_new', 'thr_stopped', 'thr_retry'})
        row = rows['thr_new']
        self.assertEqual((row['title'], row['difficulty'], row['agent'], row['model']), ('🟡 修复', 'medium', 'b', 'n'))
        self.assertEqual([(f['seq'], f['from']) for f in row['followups']], [(4, 'parent'), (8, 'user')])
        stopped = rows['thr_stopped']
        self.assertEqual((stopped['delivered'], stopped['stopped_before_delivery'], stopped['redispatched_as']),
                         (False, True, ['thr_retry']))
        self.assertEqual(stopped['followups'], [])
        self.assertEqual(result['by_agent']['a'], {'threads': 1, 'delivered': 0, 'stopped_before_delivery': 1,
                                                   'redispatched': 1, 'with_followups': 0, 'followups': 0})
        self.assertNotIn('还有一处要改', self.ledger.read_text() if self.ledger.exists() else '')

    def test_resource_exhausted_skips_session_retry_and_cools_for_an_hour(self):
        """事故：pi 每次 429 RESOURCE_EXHAUSTED，provider-retry 判 no-rate-limit-state，仍重试 1、2、4 分钟。"""
        self.chain_config(['primary', 'specialist'])
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(tid, 1095)
        self.provider_error(tid, '429: {"code":429,"message":"Resource has been exhausted (e.g. check quota).","status":"RESOURCE_EXHAUSTED"}')
        self.retry_diagnostics[tid] = {'decision': {'kind': 'decline', 'reason': 'no-rate-limit-state'},
                                       'availability': {'kind': 'not-routed'}}
        cooled = self.on_failure(tid, now=1100)
        self.assertEqual(cooled['action'], 'cooled')
        self.assertTrue(cooled['cooldown'].get('quota'))
        self.assertGreaterEqual(cooled['cooldown']['until'] - 1100, m.QUOTA_BACKOFF_BASE_SECONDS)
        self.assertFalse([c for c in self.calls if c[:2] == ('thread', 'retry')])
        self.assertTrue(self.ledger_entry(tid).get('quota'))
        nxt = m.dispatch(self.args('--task', 'next'), self.fake, now=1200)
        self.assertEqual(nxt['selection']['agent'], 'specialist')
        review = m.summarize_events(self.ledger, now=1200)
        self.assertEqual(review['quota_cooldown_skips'], 1)

    def test_model_cooldown_json_is_quota_and_ignores_short_reset_seconds(self):
        """事故：model_cooldown 的 reset_seconds 只有几十秒，按它冷却会马上再派到同一模型。"""
        self.chain_config(['primary', 'specialist'])
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(tid, 1095)
        detail = json.dumps({'code': 'model_cooldown', 'message': 'All credentials for model gemini-3.8-flash-high are cooling down',
                             'reset_seconds': 30, 'reset_time': '30s'})
        self.provider_error(tid, '429: ' + detail)
        # 同一批里另一条线程还没报错；一条额度失败就应让后续派发跳过，不必等它也失败。
        other = m.dispatch(self.args('--task', 'other'), self.fake, now=1000)['result']['thread']['id']
        cooled = self.on_failure(tid, now=1100)
        self.assertEqual(cooled['action'], 'cooled')
        self.assertEqual(cooled['cooldown']['until'] - 1100, m.QUOTA_BACKOFF_BASE_SECONDS)
        self.assertFalse([c for c in self.calls if c[:2] == ('thread', 'retry')])
        self.assertEqual(self.ledger_entry(other).get('outcome', 'spawned'), 'spawned')
        later = m.dispatch(self.args('--task', 'later'), self.fake, now=1300)
        self.assertEqual(later['selection']['agent'], 'specialist')
        self.assertEqual(m.summarize_events(self.ledger, now=1300)['quota_cooldown_skips'], 1)

    def test_quota_cooldown_doubles_after_it_expires_and_plain_429_still_retries(self):
        self.chain_config(['primary', 'specialist'])
        first = m.dispatch(self.args('--task', 'first'), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(first, 1095)
        self.retry_diagnostics[first] = {'decision': {'kind': 'decline', 'reason': 'not-resettable'}}
        self.on_failure(first, now=1100)
        opened = 1100 + m.QUOTA_BACKOFF_BASE_SECONDS + 1
        self.assertEqual(m.dispatch(self.args('--task', 'retry-window', '--dry-run'), self.fake, now=opened)['selection']['agent'], 'primary')
        second = m.dispatch(self.args('--task', 'second'), self.fake, now=opened)['result']['thread']['id']
        self.turn_ended(second, opened + 10)
        self.retry_diagnostics[second] = {'decision': {'kind': 'decline', 'reason': 'no-rate-limit-state'}}
        again = self.on_failure(second, now=opened + 20)
        self.assertEqual((again['cooldown']['level'], again['cooldown']['until'] - (opened + 20)),
                         (2, 2 * m.QUOTA_BACKOFF_BASE_SECONDS))
        # 只有 429 和句子、没有结构化额度码，也没有额度类 decline：仍走原会话重试。
        plain = m.dispatch(self.args('--task', 'plain'), self.fake, now=opened + 30)['result']['thread']['id']
        self.turn_ended(plain, opened + 40)
        self.provider_error(plain, '429 RESOURCE_EXHAUSTED', at=opened + 35)
        scheduled = self.on_failure(plain, now=opened + 50)
        self.assertEqual(scheduled['action'], 'retry-scheduled')
        self.assertEqual(scheduled['delay_seconds'], 60)

    def test_subscription_window_cooldown_lasts_until_reset(self):
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(tid, 1095)
        reset = (1000 + 10 * 3600) * 1000
        self.retry_diagnostics[tid] = {
            'decision': {'kind': 'decline', 'reason': 'beyond-maximum-wait'},
            'availability': {'kind': 'blocked', 'retryAt': reset},
        }
        cooled = self.on_failure(tid, now=1100)
        self.assertEqual(cooled['cooldown']['until'], 1000 + 10 * 3600)
        self.assertFalse([c for c in self.calls if c[:2] == ('thread', 'retry')])

    def test_long_quota_window_is_cleared_by_success_and_stays_clear(self):
        self.chain_config(['primary', 'specialist'])
        failed = m.dispatch(self.args('--task', 'failed'), self.fake, now=1000)['result']['thread']['id']
        other = m.dispatch(self.args('--task', 'other'), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(failed, 1095)
        reset = (1000 + 8 * 24 * 3600) * 1000
        self.retry_diagnostics[failed] = {
            'decision': {'kind': 'decline', 'reason': 'beyond-maximum-wait'},
            'availability': {'kind': 'blocked', 'retryAt': reset},
        }
        cooled = self.on_failure(failed, now=1100)
        self.assertGreater(cooled['cooldown']['until'], 1100 + m.RECENT_WINDOW_SECONDS)
        self.threads = [{'id': other, 'status': 'idle', 'queuedWork': 'none', 'updatedAt': 1200 * 1000}]
        recovered = m.dispatch(self.args('--task', 'after success'), self.fake, now=1300)
        self.assertEqual(recovered['selection']['agent'], 'primary')
        saved = m.load_ledger(self.ledger, strict=True)
        self.assertNotIn('primary|fast-model', saved['cooldowns'])
        # 成功记录还在账本里，但已经离开 48 小时视野；残留的额度窗口不能复活。
        saved['cooldowns']['primary|fast-model'] = {
            'provider': 'primary', 'model': 'fast-model', 'reason': '额度窗口',
            'since': 1100, 'until': 1000 + 8 * 24 * 3600, 'quota': True,
        }
        later = 1200 + m.RECENT_WINDOW_SECONDS + 10
        self.assertNotIn('primary|fast-model', m.health_cooldowns(saved, now=later))

    def test_quota_error_before_recovery_does_not_classify_the_next_failure(self):
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.provider_error(tid, '429: {"status":"RESOURCE_EXHAUSTED","code":429}', at=1050)
        self.turn_ended(tid, 1100, 'completed')
        self.turn_ended(tid, 1295)
        scheduled = self.on_failure(tid, now=1300)
        self.assertEqual(scheduled['action'], 'retry-scheduled')

if __name__ == '__main__':
    unittest.main()
