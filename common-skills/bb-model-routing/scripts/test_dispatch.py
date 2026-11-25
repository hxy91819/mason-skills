"""Offline dispatch behavior tests; the fake BB boundary never creates real threads."""
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
        # Keep overlays hermetic: never read the real user's overlay directory.
        overlay_dir = mock.patch.dict(os.environ, {'BB_DISPATCH_OVERLAY_DIR': str(Path(self.temp.name) / 'overlays')})
        overlay_dir.start()
        self.addCleanup(overlay_dir.stop)
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
            # Real show only gives queue counts; queuedWork and hasPendingInteraction exist only in list.
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
            '--unknown', 'test reason',
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
        # Redispatch copies the task from the child's first message: drop the old protocol and reattach once for the current mode.
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
            # Redispatch copies the task from the child's first message: no double append, same candidate order and title.
            copied = m.dispatch(self.args('--task', prompt(first), '--dry-run'), self.fake)
            self.assertEqual(prompt(copied), prompt(first))
            self.assertEqual(copied['selection']['candidates'], first['selection']['candidates'])
            self.assertEqual(copied['selection']['title'], first['selection']['title'])

    def test_copied_task_with_legacy_chinese_protocol_is_stripped_and_gets_english_protocol(self):
        legacy_quiet = ('linked task\n\n## 回报方式（bb-dispatch 附加）\n'
                        '回合结束不会自动通知父线程。只在这几种情况下用 `bb thread tell <父线程ID>` 发一条消息。')
        legacy_auto = 'linked task\n\n## 回报方式（bb-dispatch 附加）\n回合结束时，BB 会自动把你的最终回复送达父线程。'
        expected = m.dispatch(self.args('--task', 'linked task', '--dry-run'), self.fake)
        for copied_task in (legacy_quiet, legacy_auto):
            with self.subTest(copied_task=copied_task):
                copied = m.dispatch(self.args('--task', copied_task, '--dry-run'), self.fake)
                prompt = copied['argv'][copied['argv'].index('--prompt') + 1]
                self.assertEqual(prompt, 'linked task' + m.REPORT_PROTOCOL_ANCHOR + m.REPORT_PROTOCOL)
                self.assertNotIn('回报方式', prompt)
                self.assertEqual(copied['selection']['title'], expected['selection']['title'])
                self.assertEqual(copied['selection']['candidates'], expected['selection']['candidates'])

    def test_legacy_chinese_quota_window_cooldown_still_applies_with_english_reason(self):
        ledger = m.empty_ledger()
        ledger['cooldowns']['primary|fast-model'] = {
            'provider': 'primary', 'model': 'fast-model', 'reason': '额度窗口',
            'since': 1000, 'until': 5000, 'quota': True,
        }
        cooldown = m.health_cooldowns(ledger, now=2000)['primary|fast-model']
        self.assertEqual((cooldown['reason'], cooldown['quota'], cooldown['until']), ('quota window', True, 5000))

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

        with self.assertRaisesRegex(m.DispatchError, 'proxy environment'):
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
        self.assertIn("agents.primary.fast must be true or false", str(ctx.exception))

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
                 ('Fix login', 'Fix login'),
                 ('  [Agent] [Agent] Fix\nlogin ', 'Fix login'),
                 ('🟢 🟡 🔴 [Agent] Fix login', 'Fix login'),
                 ('🟩 🟨 🟥 💚 💛 ❤️ [Agent] Fix login', 'Fix login'),
                 ('[Agent]', 'Task'),
                 ('🟢', 'Task'),
                 ('🟨', 'Task'),
                 ('❤️', 'Task'),
                 ('📒', 'Task'),
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
                    result = m.dispatch(self.args('--difficulty', difficulty, '--title', '📒 test task', '--dry-run'), self.fake)
                    self.assertEqual(result['selection']['title'], prefix + ' test task')

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

        res_l = m.dispatch(self.args('--difficulty', 'medium', '--title', 'test task', '--dry-run'), self.fake)
        self.assertEqual(res_l['selection']['title'], '🟨 test task')

        res_b = m.dispatch(self.args('--difficulty', 'complex', '--title', 'test task', '--dry-run'), self.fake)
        self.assertEqual(res_b['selection']['title'], '❤️ test task')

        res_custom = m.dispatch(self.args('--difficulty', 'simple', '--title', 'test task', '--dry-run'), self.fake)
        self.assertEqual(res_custom['selection']['title'], '💚 test task')

    def test_spawn_failure_is_not_retried(self):
        def failing(*args):
            if args[:2] == ('thread', 'spawn'):
                self.calls.append(args)
                raise m.DispatchError('creation result unknown')
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
        with self.assertRaisesRegex(m.DispatchError, 'at least one candidate with weight > 0'):
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
                                      '--difficulty', 'complex', '--task', 'judge the plan', *extra])

    def test_direct_medium_or_complex_needs_no_escalation_or_reason(self):
        long_task = 'refine the steps ' * 700
        for diff in ('medium', 'complex'):
            args = self.args('--difficulty', diff, '--task', long_task)
            args.unknown = None
            result = m.dispatch(args, self.fake, now=1000)
            self.assertEqual(result['selection']['difficulty'], diff)
            self.assertNotIn('escalated_from', result['selection'])

    def test_optional_reason_and_escalation_are_recorded(self):
        unknown = 'unclear whether the fault is in the gateway, scheduler or storage layer' * 10
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
        receipt = {'dry_run': False, 'selection': {'warnings': ['grading skew reminder']}, 'result': {'thread': {'id': 'thr_x'}}}
        argv = ['bb-dispatch', '--config', str(self.config), '--difficulty', 'simple', '--task', 't']
        with mock.patch.object(m, 'dispatch', return_value=receipt), mock.patch('sys.argv', argv), \
                mock.patch('sys.stdout', new_callable=io.StringIO) as out, \
                mock.patch('sys.stderr', new_callable=io.StringIO) as err:
            self.assertEqual(m.main(), 0)
        self.assertEqual(json.loads(out.getvalue())['result']['thread']['id'], 'thr_x')
        self.assertIn('warning: grading skew reminder', err.getvalue())

    def test_ledger_records_minimal_facts_and_overwrites_on_repeat_decision(self):
        res = m.dispatch(self.args('--task', 'SENSITIVE_SECRET_TOKEN_123'), self.fake, now=1000)
        tid = res['result']['thread']['id']
        raw_ledger = self.ledger.read_text()
        self.assertNotIn('SENSITIVE_SECRET_TOKEN_123', raw_ledger)
        self.assertNotIn('SENSITIVE_SECRET_TOKEN_123', m.events_path(self.ledger).read_text())
        # Unknown IDs are rejected
        with self.assertRaisesRegex(m.DispatchError, 'refusing to write back an unknown ID'):
            m.record_outcome_command(
                m.parser().parse_args(['--ledger', str(self.ledger), '--record-outcome', 'thr_unknown', '--outcome', 'completed']),
                now=1010,
            )
        # Writing back the same ID again overwrites instead of appending; the old option name still works
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
        # Legacy manual failure types still count, but no longer set the duration by type.
        m.record_outcome_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--record-outcome', tid, '--outcome', 'failed_quota']),
            now=1010,
        )
        # During the cooldown primary is skipped automatically and specialist is chosen
        second = m.dispatch(self.args('--dry-run'), self.fake, now=1100)
        self.assertEqual(second['selection']['agent'], 'specialist')
        self.assertIn('circuit-breaker cooldown', second['selection']['attempts'][0]['error'])
        cooled = m.summarize_ledger(m.load_ledger(self.ledger, strict=True), now=1100)['active_cooldowns']
        self.assertEqual([(c['provider'], c['model'], c['level']) for c in cooled], [('primary', 'fast-model', 1)])
        # The first failure's 15-minute cooldown lifts automatically
        third = m.dispatch(self.args('--dry-run'), self.fake, now=1010 + m.BACKOFF_BASE_SECONDS + 1)
        self.assertEqual(third['selection']['agent'], 'primary')

    def on_failure(self, tid, *extra, now):
        return m.on_failure_command(
            m.parser().parse_args(['--ledger', str(self.ledger), '--on-failure', tid, *extra]), self.fake, now=now)

    def turn_ended(self, tid, at, status='failed'):
        """The thread ends a turn at `at` seconds: the log gains a turn-end event and the thread rests in error or idle."""
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
        """A provider/error in the thread log. detail uses JSON from a real incident, not an error sentence."""
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
        # Errors first retry in the original session with backoff without affecting new dispatches; the next retry is scheduled only after one runs and fails again.
        at, delays = 1100, []
        for _ in range(m.SESSION_RETRY_LIMIT):
            delays.append(self.on_failure(tid, now=at)['delay_seconds'])
            at += delays[-1] + 10
            self.turn_ended(tid, at - 5)
        self.assertEqual(delays, [60, 120, 240])
        sent = [c[c.index('--send-at') + 1] for c in self.calls if c[:2] == ('thread', 'retry')]
        self.assertEqual(sent, ['60s', '120s', '240s'])
        self.assertEqual(m.dispatch(self.args('--task', 'other', '--dry-run'), self.fake, now=1200)['selection']['agent'], 'specialist')
        # Failure is recorded only once retries are exhausted; cooldown is per provider and model, so other tiers skip it too.
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
        task = '  Goal\n\nkeep the full task $(literal)\n'
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
                {'type': 'text', 'text': 'later messages must not become the task body'},
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
        self.assertNotIn('keep the full task', self.ledger.read_text())

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
            {'type': 'text', 'text': 'only later messages'},
        ]}}]
        prefix = ['--config', str(self.config), '--ledger', str(self.ledger), '--redispatch']
        for source_id, message in [(tid, 'first-turn dispatch task text'), ('missing', 'valid original difficulty')]:
            with self.subTest(source_id=source_id), self.assertRaisesRegex(m.DispatchError, message):
                m.dispatch(m.parser().parse_args([*prefix, source_id]), self.fake, now=1100)
        self.assertEqual(self.spawn_counter, 1)

    def test_on_failure_waits_while_a_retry_is_queued_but_not_for_deferred_messages(self):
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        # Parent messages queued on the errored thread are sent only on retry and do not count as an existing retry.
        self.threads = [{'id': tid, 'status': 'error', 'queuedWork': 'waiting', 'updatedAt': 1095 * 1000}]
        at = 1100
        for attempt in range(1, m.SESSION_RETRY_LIMIT + 1):
            self.assertEqual(self.on_failure(tid, now=at)['attempt'], attempt)
            # Repeated calls while the last scheduled retry has not run: only wait, schedule nothing, and never cool even at the 3rd.
            self.assertEqual(self.on_failure(tid, now=at + 5)['action'], 'waiting')
            at += 60 * 2 ** (attempt - 1) + 10
            self.turn_ended(tid, at - 5)
        self.assertEqual(len([c for c in self.calls if c[:2] == ('thread', 'retry')]), m.SESSION_RETRY_LIMIT)
        self.assertEqual((self.ledger_entry(tid)['outcome'], self.ledger_entry(tid)['retries']), ('spawned', 3))
        # BB replies that the turn already has a queued retry (e.g. the user clicked retry in the UI): wait as well, no cooldown.
        other = m.dispatch(self.args('--task', 'other'), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(other, 1095)
        self.retry_error = m.DispatchError('bb thread retry failed: retry_already_queued:', code='retry_already_queued')
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
        # BB already retried to its limit in the original session: no more retries, cool directly.
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
        # The original-session retry succeeded with no other dispatch recording completion; a later error is a new fault counted from 1.
        self.turn_ended(tid, 1170, 'completed')
        self.turn_ended(tid, 1295)
        self.assertEqual(self.on_failure(tid, now=1300)['attempt'], 1)
        self.assertEqual([(e['thread'], e['retries']) for e in self.logged('recovered')], [(tid, 1)])
        # Cool directly when the original session cannot be retried.
        self.turn_ended(tid, 1395)
        self.retry_error = m.DispatchError('bb thread retry failed: thread_not_failed:', code='thread_not_failed')
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
        # A later success clears primary's cooldown.
        self.assertEqual(m.dispatch(self.args('--task', 'next'), self.fake, now=1060)['selection']['agent'], 'primary')
        # A finished thread reused and then errored: the outcome stays during original-session retries, that success still counts, and old failures do not revive the cooldown.
        self.turn_ended(reused, 1095)
        self.assertEqual(self.on_failure(reused, now=1100)['action'], 'retry-scheduled')
        self.assertEqual(m.dispatch(self.args('--task', 'later', '--dry-run'), self.fake, now=1150)['selection']['agent'], 'primary')
        # After a successful retry, the next dispatch records the recovery and resets the retry count.
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
        # flaky recovers after the 2nd original-session retry; broken then exhausts its retries and cools.
        self.on_failure(flaky, now=1100)
        self.turn_ended(flaky, 1102)
        self.on_failure(flaky, now=1104)
        self.turn_ended(flaky, 1106, 'completed')
        for index in range(m.SESSION_RETRY_LIMIT):
            self.on_failure(broken, now=1110 + 10 * index)
            self.turn_ended(broken, 1115 + 10 * index)
        self.on_failure(broken, now=1110 + 10 * m.SESSION_RETRY_LIMIT)
        # BB giving up after one original-session retry counts as a retry that did not save it; BB giving up immediately does not count as a retry outcome.
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
        # Errors are left to --on-failure; no failure is recorded here.
        self.assertEqual([outcomes[tid] for tid in ids[1:]], ['spawned'] * 4)
        self.assertEqual(outcomes[stale], 'spawned')

    def test_failures_during_cooldown_extend_it_and_later_failures_escalate(self):
        def entry(tid, outcome, at):
            return {'id': tid, 'ts': at - 50, 'provider': 'p', 'model': 'm', 'outcome': outcome, 'outcome_ts': at}

        base = m.BACKOFF_BASE_SECONDS
        # Back-to-back failures during a cooldown count once; the cooldown runs from the last failure.
        ledger = {'entries': [entry('a', 'failed', 100), entry('b', 'failed', 200), entry('c', 'failed', 300)],
                  'cooldowns': {}}
        cooled = m.health_cooldowns(ledger, now=301)['p|m']
        self.assertEqual((cooled['level'], cooled['until']), (1, 300 + base))
        # A failure after the cooldown ends doubles the duration.
        after = 300 + base
        ledger['entries'].append(entry('d', 'failed', after + 60))
        cooled = m.health_cooldowns(ledger, now=after + 61)['p|m']
        self.assertEqual((cooled['level'], cooled['until']), (2, after + 60 + 2 * base))
        # One success resets it.
        ledger['entries'].append(entry('e', 'completed', after + 80))
        self.assertEqual(m.health_cooldowns(ledger, now=after + 81), {})
        # Failures before the recent window no longer count toward the level.
        old = 10 ** 6
        fresh = old + base + m.RECENT_WINDOW_SECONDS + 100
        stale = {'entries': [entry('o1', 'failed', old), entry('o2', 'failed', old + base + 1),
                             entry('n', 'failed', fresh)], 'cooldowns': {}}
        cooled = m.health_cooldowns(stale, now=fresh + 1)['p|m']
        self.assertEqual((cooled['level'], cooled['until']), (1, fresh + base))
        # Persistent failures cap at 6 hours.
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
        self.assertIn('cannot read thread status', stderr.getvalue())

    def test_spawn_failure_cools_candidate_so_rerun_switches(self):
        self.chain_config(['primary', 'specialist'])

        def flaky(*a):
            if a[:2] == ('thread', 'spawn') and a[a.index('--provider') + 1] == 'primary':
                self.calls.append(a)
                raise m.DispatchError('spawn failed')
            return self.fake(*a)

        with self.assertRaisesRegex(m.DispatchError, 'candidate is now cooling'):
            m.dispatch(self.args(), flaky, now=1000)
        rerun = m.dispatch(self.args(), flaky, now=1010)
        self.assertEqual(rerun['selection']['agent'], 'specialist')

    def test_concurrent_ledger_write_is_merged_not_overwritten(self):
        def racing(*a):
            if a[:2] == ('thread', 'spawn'):
                # Another session writes the ledger during this spawn.
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
                # Another session records a later spawn failure for the same provider and model during this spawn.
                other = m.load_ledger(self.ledger, strict=True)
                other['cooldowns']['primary|fast-model'] = {
                    'provider': 'primary', 'model': 'fast-model', 'reason': 'spawn-failed',
                    'since': 1100, 'until': 1100 + m.SPAWN_COOLDOWN_SECONDS,
                }
                m.save_ledger(self.ledger, other, strict=True)
                raise m.DispatchError('spawn failed')
            return self.fake(*a)

        with self.assertRaisesRegex(m.DispatchError, 'candidate is now cooling'):
            m.dispatch(self.args(), racing, now=1000)
        later = m.dispatch(self.args('--dry-run'), self.fake, now=1000 + m.SPAWN_COOLDOWN_SECONDS + 50)
        self.assertEqual(later['selection']['agent'], 'specialist')

    def test_cooldown_survives_a_full_window_of_other_dispatches(self):
        self.chain_config(['primary', 'specialist'])
        now = 10 ** 6
        ledger = m.empty_ledger()
        ledger['entries'].append({'id': 'ancient', 'ts': now - m.RECENT_WINDOW_SECONDS - 100,
                                  'provider': 'other', 'model': 'x', 'outcome': 'completed'})
        # A long task dispatched first has just failed; a full window of other dispatches followed.
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
        # The next task without --fallback-from should also skip the just-failed primary within 15 minutes
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
        self.assertEqual(event['unknown'], 'test reason')
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
            req(1, 'user', 'original task'),
            req(2, 'agent', 'addition before delivery', 'thr_parent'),
            {'seq': 3, 'type': 'turn/completed', 'data': {'status': 'completed'}},
            req(4, 'agent', '[bb message from thread:thr_parent] one more fix needed', 'thr_parent'),
            req(5, 'agent', 'sent from another thread', 'thr_other'),
            req(6, 'system', '[bb system] @thread:thr_child completed'),
            req(7, 'user', '[bb_long_task] merge finished'),
            req(8, 'user', 'direct user correction'),
        ]

        stopped_log = [
            req(1, 'user', 'original task'),
            {'seq': 2, 'type': 'system/thread/interrupted', 'data': {'reason': 'manual-stop'}},
            {'seq': 3, 'type': 'turn/completed', 'data': {'status': 'interrupted'}},
            req(4, 'agent', 'stopped and redispatched', 'thr_parent'),
        ]

        def call(*argv):
            if argv[:2] == ('thread', 'list'):
                return [{'id': 'thr_new', 'parentThreadId': 'thr_parent', 'title': '🟡 Fix'},
                        {'id': 'thr_stopped', 'parentThreadId': 'thr_parent'}, {'id': 'thr_retry'}]
            if argv[:2] == ('thread', 'log'):
                return {'thr_new': log, 'thr_stopped': stopped_log}.get(argv[2], [])
            raise AssertionError(argv)
        args = m.parser().parse_args(['--ledger', str(self.ledger), '--followups', '--days', '1'])
        result = m.followups_command(args, call=call, now=200000)
        rows = {r['thread']: r for r in result['rows']}
        self.assertEqual(set(rows), {'thr_new', 'thr_stopped', 'thr_retry'})
        row = rows['thr_new']
        self.assertEqual((row['title'], row['difficulty'], row['agent'], row['model']), ('🟡 Fix', 'medium', 'b', 'n'))
        self.assertEqual([(f['seq'], f['from']) for f in row['followups']], [(4, 'parent'), (8, 'user')])
        stopped = rows['thr_stopped']
        self.assertEqual((stopped['delivered'], stopped['stopped_before_delivery'], stopped['redispatched_as']),
                         (False, True, ['thr_retry']))
        self.assertEqual(stopped['followups'], [])
        self.assertEqual(result['by_agent']['a'], {'threads': 1, 'delivered': 0, 'stopped_before_delivery': 1,
                                                   'redispatched': 1, 'with_followups': 0, 'followups': 0})
        self.assertNotIn('one more fix needed', self.ledger.read_text() if self.ledger.exists() else '')

    def test_resource_exhausted_skips_session_retry_and_cools_for_an_hour(self):
        """Incident: pi hit 429 RESOURCE_EXHAUSTED every time and provider-retry said no-rate-limit-state, yet it still retried after 1, 2, 4 minutes."""
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
        """Incident: model_cooldown's reset_seconds is only tens of seconds; cooling by it redispatches to the same model right away."""
        self.chain_config(['primary', 'specialist'])
        tid = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        self.turn_ended(tid, 1095)
        detail = json.dumps({'code': 'model_cooldown', 'message': 'All credentials for model gemini-3.8-flash-high are cooling down',
                             'reset_seconds': 30, 'reset_time': '30s'})
        self.provider_error(tid, '429: ' + detail)
        # Another thread in the batch has not errored yet; one quota failure should make later dispatches skip, without waiting for it to fail too.
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
        # Only a 429 and a sentence, with no structured quota code and no quota decline: still retry in the original session.
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
        # The success is still in the ledger but outside the 48-hour horizon; a leftover quota window must not revive.
        saved['cooldowns']['primary|fast-model'] = {
            'provider': 'primary', 'model': 'fast-model', 'reason': m.QUOTA_WINDOW_REASON,
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

    # Advisors.
    def advisor_config(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['defaults']['advisor'] = {'mode': 'weighted-load-balance', 'candidates': {'sage': 1, 'muse': 1}}
        config['agents']['sage'] = {'provider': 'specialist', 'routes': {'advisor': {'model': 'deep-model', 'reasoning': 'high'}}}
        config['agents']['muse'] = {'provider': 'primary', 'routes': {'advisor': {'model': 'medium-model', 'reasoning': 'high'}}}
        self.config.write_text(m.yaml.safe_dump(config))

    def advise(self, *extra, task='Which cache design fits?'):
        return m.parser().parse_args(['--config', str(self.config), '--ledger', str(self.ledger),
                                      '--purpose', 'advise', '--task', task, *extra])

    def test_blind_advisor_dispatch_uses_advisor_route_only(self):
        self.advisor_config()
        result = m.dispatch(self.advise(), self.fake, now=1000)
        selection = result['selection']
        self.assertIn(selection['agent'], ('sage', 'muse'))
        self.assertEqual(sorted(selection['candidates']), ['muse', 'sage'])
        self.assertEqual((selection['purpose'], selection['difficulty']), ('advise', 'advisor'))
        self.assertTrue(selection['title'].startswith('🟣 '))
        entry = json.loads(self.ledger.read_text())['entries'][0]
        self.assertEqual((entry['purpose'], entry['difficulty']), ('advise', 'advisor'))
        self.assertEqual(m.summarize_ledger(json.loads(self.ledger.read_text()), now=1000)['by_difficulty']['advisor']['total'], 1)
        # Worker routes never pick an advisor.
        for difficulty in ('simple', 'medium', 'complex'):
            args = self.args('--dry-run')
            args.difficulty = difficulty
            self.assertNotIn(m.dispatch(args, self.fake, now=1000)['selection']['agent'], ('sage', 'muse'))

    def test_named_advisor_is_used_without_falling_back(self):
        self.advisor_config()
        for name in ('sage', 'muse'):
            with self.subTest(name):
                selection = m.dispatch(self.advise('--advisor', name, '--dry-run'), self.fake)['selection']
                self.assertEqual((selection['agent'], selection['candidates'], selection['fallbacks']), (name, [name], []))
        self.providers = [p for p in self.providers if p['id'] != 'specialist']
        with self.assertRaisesRegex(m.DispatchError, 'sage'):
            m.dispatch(self.advise('--advisor', 'sage', '--dry-run'), self.fake)

    def test_advisor_arguments_are_rejected_when_misused(self):
        self.advisor_config()
        cases = [
            self.advise('--advisor', 'primary', '--dry-run'),
            self.advise('--difficulty', 'complex', '--dry-run'),
            self.args('--advisor', 'sage', '--dry-run'),
            self.advise('--advisor', 'sage', '--fallback-from', 'muse', '--dry-run'),
        ]
        for args in cases:
            with self.subTest(argv=vars(args)), self.assertRaises(m.DispatchError):
                m.dispatch(args, self.fake)

    def test_advisor_only_agent_in_worker_chain_is_skipped(self):
        self.advisor_config()
        config = m.yaml.safe_load(self.config.read_text())
        config['defaults']['simple'] = ['sage', 'primary']
        config['defaults']['medium'] = 'sage'
        self.config.write_text(m.yaml.safe_dump(config))
        selection = m.dispatch(self.args('--dry-run'), self.fake)['selection']
        self.assertEqual(selection['agent'], 'primary')
        self.assertIn('sage', selection['attempts'][0]['agent'])
        args = self.args('--dry-run')
        args.difficulty = 'medium'
        with self.assertRaisesRegex(m.DispatchError, 'sage'):
            m.dispatch(args, self.fake)

    def test_advisor_ignores_project_floor(self):
        self.advisor_config()
        self.project_floor('complex')
        selection = m.dispatch(self.advise('--dry-run'), self.fake)['selection']
        self.assertEqual(selection['difficulty'], 'advisor')
        self.assertIn(selection['agent'], ('sage', 'muse'))

    def redispatch_args(self, tid, *extra):
        spawn = [call for call in self.calls if call[:2] == ('thread', 'spawn')][-1]
        self.requests[tid] = [{'type': 'client/turn/requested', 'data': {'source': 'spawn', 'input': [
            {'type': 'text', 'text': spawn[spawn.index('--prompt') + 1]},
        ]}}]
        return m.parser().parse_args(['--config', str(self.config), '--ledger', str(self.ledger),
                                      '--redispatch', tid, *extra])

    def test_redispatch_keeps_named_advisor_and_blind_stays_blind(self):
        self.advisor_config()
        named = m.dispatch(self.advise('--advisor', 'sage'), self.fake, now=1000)['result']['thread']['id']
        self.assertEqual(self.ledger_entry(named)['advisor'], 'sage')
        again = m.dispatch(self.redispatch_args(named, '--dry-run'), self.fake, now=1100)['selection']
        self.assertEqual((again['purpose'], again['agent'], again['candidates']), ('advise', 'sage', ['sage']))
        self.providers = [p for p in self.providers if p['id'] != 'specialist']
        with self.assertRaisesRegex(m.DispatchError, 'sage'):
            m.dispatch(self.redispatch_args(named, '--dry-run'), self.fake, now=1100)
        blind = m.dispatch(self.advise(), self.fake, now=1000)['result']['thread']['id']
        self.assertNotIn('advisor', self.ledger_entry(blind))
        again = m.dispatch(self.redispatch_args(blind, '--dry-run'), self.fake, now=1100)['selection']
        self.assertEqual((again['purpose'], sorted(again['candidates'])), ('advise', ['muse', 'sage']))

    def test_redispatch_rejects_misused_advisor_flags(self):
        self.advisor_config()
        named = m.dispatch(self.advise('--advisor', 'sage'), self.fake, now=1000)['result']['thread']['id']
        worker = m.dispatch(self.args(), self.fake, now=1000)['result']['thread']['id']
        for args in (self.redispatch_args(named, '--fallback-from', 'muse', '--dry-run'),
                     self.redispatch_args(named, '--advisor', 'sage', '--fallback-from', 'muse', '--dry-run'),
                     self.redispatch_args(worker, '--advisor', 'sage', '--dry-run')):
            with self.subTest(argv=vars(args)), self.assertRaises(m.DispatchError):
                m.dispatch(args, self.fake, now=1100)

    def test_advisor_without_configured_route_reports_missing_config(self):
        with self.assertRaisesRegex(m.DispatchError, 'defaults.advisor'):
            m.dispatch(self.advise('--dry-run'), self.fake)

    def test_overlay_can_pin_advisor_route(self):
        self.advisor_config()
        with self.overlay_env():
            self.set_overlay('defaults: {advisor: sage}\n')
            selection = m.dispatch(self.advise('--dry-run'), self.fake, now=1100)['selection']
        self.assertEqual(selection['agent'], 'sage')

    # Temporary routing overlays.
    OVERLAY = '''defaults: {simple: [trial, primary], complex: trial}
agents:
  trial:
    provider: specialist
    routes: {default: {model: deep-model, reasoning: max}}
'''

    def overlay_env(self, thread: str | None = 'parent'):
        if thread:
            return mock.patch.dict(os.environ, {'BB_THREAD_ID': thread})
        return mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != 'BB_THREAD_ID'}, clear=True)

    def set_overlay(self, text=None, *extra, now=1000):
        source = Path(self.temp.name) / 'overlay-input.yaml'
        source.write_text(self.OVERLAY if text is None else text)
        args = m.parser().parse_args(['--config', str(self.config), '--overlay-set', str(source), *extra])
        return m.overlay_set_command(args, now=now)

    def test_overlay_routes_only_its_thread_and_leaves_main_config_untouched(self):
        before = self.config.read_bytes()
        with self.overlay_env():
            self.set_overlay(None, '--note', 'user: try specialist max')
            result = m.dispatch(self.args(), self.fake, now=1100)
        self.assertEqual(self.config.read_bytes(), before)
        selection = result['selection']
        self.assertEqual((selection['agent'], selection['reasoning']), ('trial', 'max'))
        self.assertEqual(selection['candidates'], ['trial', 'primary'])
        self.assertEqual(selection['overlay']['note'], 'user: try specialist max')
        self.assertTrue(any('overlay active' in w for w in selection['warnings']))
        self.assertTrue(json.loads(self.ledger.read_text())['entries'][0]['overlay'])
        # Unset difficulties keep the main config's route.
        with self.overlay_env():
            medium = m.dispatch(self.args('--dry-run'), self.fake, now=1100)
        self.assertEqual(medium['selection']['agent'], 'trial')
        args = self.args('--dry-run')
        args.difficulty = 'medium'
        with self.overlay_env():
            self.assertEqual(m.dispatch(args, self.fake, now=1100)['selection']['agent'], 'primary')
        with self.overlay_env('other_thread'):
            other = m.dispatch(self.args('--dry-run'), self.fake, now=1100)
        self.assertEqual(other['selection']['agent'], 'primary')
        self.assertNotIn('overlay', other['selection'])

    def test_overlay_beats_environment_block(self):
        args = self.args('--environment', 'env_other', '--dry-run')
        args.difficulty = 'complex'
        with self.overlay_env():
            self.set_overlay()
            selection = m.dispatch(args, self.fake, now=1100)['selection']
        self.assertEqual((selection['agent'], selection['provider']), ('trial', 'specialist'))

    def test_expired_overlay_falls_back_to_main_config_with_warning(self):
        with self.overlay_env():
            self.set_overlay(None, '--hours', '1', now=1000)
            selection = m.dispatch(self.args('--dry-run'), self.fake, now=1000 + 3601)['selection']
        self.assertEqual(selection['agent'], 'primary')
        self.assertTrue(selection['overlay']['expired'])
        self.assertTrue(any('expired' in w for w in selection['warnings']))

    def test_overlay_set_replaces_clear_removes_and_show_lists(self):
        with self.overlay_env():
            self.set_overlay()
            self.set_overlay('defaults: {simple: specialist}\n')
            self.assertEqual(m.dispatch(self.args('--dry-run'), self.fake, now=1100)['selection']['agent'], 'specialist')
            shown = m.overlay_show_command(now=1100)['overlays']
            self.assertEqual([(o['thread'], o['active'], o['defaults']) for o in shown],
                             [('parent', True, {'simple': 'specialist'})])
            m.overlay_clear_command(m.parser().parse_args(['--overlay-clear']))
            self.assertEqual(m.dispatch(self.args('--dry-run'), self.fake, now=1100)['selection']['agent'], 'primary')
            with self.assertRaises(m.DispatchError):
                m.overlay_clear_command(m.parser().parse_args(['--overlay-clear']))

    def test_overlay_set_prunes_other_expired_overlays(self):
        with self.overlay_env('old_thread'):
            self.set_overlay(None, '--hours', '1', now=1000)
        with self.overlay_env():
            result = self.set_overlay(None, now=1000 + 3601)
        self.assertEqual(result['pruned_expired'], ['old_thread'])

    def test_overlay_set_rejects_bad_input_without_writing(self):
        bad = {
            'unknown key': 'defaults: {simple: primary}\npermission_mode: full\n',
            'undefined alias': 'defaults: {simple: ghost}\n',
            'bad difficulty': 'defaults: {hard: primary}\n',
            'route missing': 'defaults: {complex: trial}\nagents: {trial: {provider: specialist, routes: {simple: {model: deep-model}}}}\n',
            'empty': '{}\n',
            'main alias lacks route': 'defaults: {complex: primary}\n',
            'replaced alias breaks untouched route': 'agents: {primary: {provider: primary, routes: {simple: {model: fast-model}}}}\n',
            'alias only in one environment': 'defaults: {simple: envonly}\n',
        }
        config = m.yaml.safe_load(self.config.read_text())
        config['environments']['env_other']['agents']['envonly'] = {
            'provider': 'remote-provider', 'routes': {'default': {'model': 'remote-model'}}}
        self.config.write_text(m.yaml.safe_dump(config))
        with self.overlay_env():
            for name, text in bad.items():
                with self.subTest(name), self.assertRaises(m.DispatchError):
                    self.set_overlay(text)
            self.assertFalse(m.overlay_path('parent').exists())
        with self.overlay_env(None), self.assertRaises(m.DispatchError):
            self.set_overlay()

    def test_corrupt_overlay_fails_dispatch_instead_of_silently_using_main_config(self):
        with self.overlay_env():
            path = m.overlay_path('parent')
            path.parent.mkdir(parents=True)
            path.write_text('defaults: [oops\n')
            with self.assertRaises(m.DispatchError):
                m.dispatch(self.args('--dry-run'), self.fake, now=1100)

if __name__ == '__main__':
    unittest.main()
