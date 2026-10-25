"""容量控制的行为与真实跨进程互斥；不调用线上 BB。"""
import json
import multiprocessing
import os
from pathlib import Path
import time
import unittest
from unittest import mock

import test_dispatch as fixtures

m = fixtures.m


# 独立进程使用不同账本，唯一共享的是用户级并发状态。
def dispatch_worker(config, ledger, state, start, results, difficulty="simple"):
    m.CONCURRENCY_PATH = Path(state)
    args = m.parser().parse_args(['--config', config, '--ledger', ledger,
                                  '--difficulty', difficulty, '--task', '并行任务',
                                  '--project', 'proj', '--environment', 'env'])

    def bb(*argv):
        if argv[:2] == ('environment', 'show'):
            return {'id': 'env', 'projectId': 'proj'}
        if argv[:2] == ('provider', 'list'):
            return [{'id': 'amp', 'available': True, 'capabilities': {'permissionModes': ['accept-edits']}}]
        if argv[:2] == ('provider', 'models'):
            return [{'id': 'model'}, {'id': 'simple-model'}]
        if argv[:2] == ('thread', 'show'):
            return {'thread': {'id': 'parent'}}
        if argv[:2] == ('thread', 'list'):
            return []  # 模拟创建成功后线程尚未出现在列表中。
        if argv[:2] == ('thread', 'spawn'):
            time.sleep(0.15)  # 扩大无锁实现会超发的窗口。
            return {'id': f'created_{os.getpid()}', 'status': 'active'}
        raise AssertionError(argv)

    start.wait(5)
    try:
        m.dispatch(args, bb)
        results.put('spawned')
    except m.DispatchError as exc:
        results.put(str(exc))


class ConcurrencyTests(unittest.TestCase):
    args = fixtures.DispatchTests.args
    def setUp(self):
        fixtures.DispatchTests.setUp(self)
        self.state = Path(self.temp.name) / 'concurrency.json'
        patch = mock.patch.object(m, 'CONCURRENCY_PATH', self.state)
        patch.start()
        self.addCleanup(patch.stop)
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['primary']['max_concurrency'] = 1
        config['defaults']['simple'] = ['primary', 'specialist']
        self.config.write_text(m.yaml.safe_dump(config))

    def fake(self, *args):
        if args == ('thread', 'list', '--include-hidden'):
            return self.threads
        return fixtures.DispatchTests.fake(self, *args)

    def running(self, status='active', queued='none', interaction=False):
        return {'id': 'created_1', 'providerId': 'primary', 'status': status,
                'queuedWork': queued, 'hasPendingInteraction': interaction, 'archivedAt': None}

    def test_shared_across_difficulties_and_ledgers_then_releases_after_turn(self):
        first = m.dispatch(self.args(), self.fake)
        self.assertEqual(first['selection']['provider'], 'primary')
        # 列表尚未可见也占位；不同账本与不同难度不能绕过。
        other_ledger = str(Path(self.temp.name) / 'other-ledger.json')
        with self.assertRaisesRegex(m.DispatchError, '并发已满'):
            m.dispatch(self.args('--difficulty', 'medium', '--ledger', other_ledger), self.fake)
        # 初始 idle 没有回合结束事件，仍占位。
        self.threads = [self.running(status='idle')]
        second = m.dispatch(self.args(), self.fake)
        self.assertEqual(second['selection']['provider'], 'specialist')
        self.turns['created_1'] = [(int(time.time()) + 1, 'completed')]
        third = m.dispatch(self.args(), self.fake)
        self.assertEqual(third['selection']['provider'], 'primary')

    def test_live_active_queued_interaction_and_unknown_states_are_occupied(self):
        for status, queued, interaction in [('active', 'none', False), ('idle', 'waiting', False),
                                             ('idle', 'none', True), ('stopping', 'none', False),
                                             ('error', 'waiting', True), ('error', 'unknown', False),
                                             ('error', 'waiting', None), ('unknown', 'none', False)]:
            with self.subTest(status=status, queued=queued, interaction=interaction):
                self.threads = [self.running(status, queued, interaction)]
                result = m.dispatch(self.args('--dry-run'), self.fake)
                self.assertEqual(result['selection']['provider'], 'specialist')
                self.assertIn('并发已满', result['selection']['attempts'][0]['error'])
        self.assertFalse(self.state.exists())
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_archived_queued_threads_do_not_occupy_capacity(self):
        for status in ('idle', 'error', 'active'):
            with self.subTest(status=status):
                self.threads = [{**self.running(status, 'waiting', True), 'archivedAt': 1234}]
                result = m.dispatch(self.args('--dry-run'), self.fake)
                self.assertEqual(result['selection']['provider'], 'primary')
                self.assertEqual(result['selection']['concurrency']['used'], 0)
        self.assertFalse(self.state.exists())

    def test_archived_thread_releases_reservation_without_turn_end(self):
        m.dispatch(self.args(), self.fake)
        self.threads = [{**self.running('error', 'waiting'), 'archivedAt': 1234}]
        before = self.state.read_bytes()
        status = m.concurrency_command(self.args('--concurrency-status'), self.fake)
        self.assertEqual(status['usage']['primary'], 0)
        self.assertEqual(status['reservations'], [])
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(m.dispatch(self.args('--dry-run'), self.fake)['selection']['provider'], 'primary')

    def test_error_queued_messages_waiting_for_retry_do_not_occupy_capacity(self):
        for queued in ('none', 'waiting', 'failed'):
            with self.subTest(queued=queued):
                self.threads = [{**self.running('error', queued), 'archivedAt': None}]
                result = m.dispatch(self.args('--dry-run'), self.fake)
                self.assertEqual(result['selection']['provider'], 'primary')
                self.assertEqual(result['selection']['concurrency']['used'], 0)
        self.assertFalse(self.state.exists())

    def test_error_queued_reservation_releases_after_failed_turn(self):
        m.dispatch(self.args(), self.fake)
        self.threads = [self.running('error', 'waiting')]
        # 没有结束事件的已登记创建仍保守占位。
        self.assertEqual(m.dispatch(self.args('--dry-run'), self.fake)['selection']['provider'], 'specialist')
        self.turns['created_1'] = [(int(time.time()) + 1, 'failed')]
        self.assertEqual(m.dispatch(self.args('--dry-run'), self.fake)['selection']['provider'], 'primary')

    def test_capacity_does_not_cool_or_change_ledger_and_cannot_be_bypassed(self):
        self.threads = [self.running()]
        with self.assertRaisesRegex(m.DispatchError, '并发已满'):
            m.dispatch(self.args('--difficulty', 'medium'), self.fake)
        with self.assertRaisesRegex(m.DispatchError, '并发已满'):
            m.dispatch(self.args('--fallback-from', 'primary', '--difficulty', 'medium'), self.fake)
        self.assertFalse(self.ledger.exists())
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

    def test_duplicate_aliases_of_provider_share_smallest_limit(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['same'] = {'provider': 'primary', 'max_concurrency': 5,
                                     'routes': {'simple': {'model': 'fast-model'}}}
        config['defaults']['simple'] = ['same', 'specialist']
        self.config.write_text(m.yaml.safe_dump(config))
        self.threads = [self.running()]
        result = m.dispatch(self.args('--dry-run'), self.fake)
        self.assertEqual(result['selection']['provider'], 'specialist')
        self.assertIn('1/1', result['selection']['attempts'][0]['error'])

    def test_invalid_limits_are_rejected_and_absent_limit_preserves_old_behavior(self):
        config = m.yaml.safe_load(self.config.read_text())
        for limit in [0, -1, True, '1', 1.5, None]:
            with self.subTest(limit=limit):
                config['agents']['primary']['max_concurrency'] = limit
                self.config.write_text(m.yaml.safe_dump(config))
                with self.assertRaisesRegex(m.DispatchError, '正整数'):
                    m.dispatch(self.args(), self.fake)
        config['agents']['primary'].pop('max_concurrency')
        self.config.write_text(m.yaml.safe_dump(config))
        m.dispatch(self.args(), self.fake)
        m.dispatch(self.args(), self.fake)
        self.assertEqual(self.spawn_counter, 2)
        self.assertFalse(self.state.exists())

    def test_unknown_spawn_keeps_reservation_until_explicit_release(self):
        def timeout(*args):
            if args[:2] == ('thread', 'spawn'):
                raise m.DispatchError('创建结果未知')
            return self.fake(*args)

        with self.assertRaisesRegex(m.DispatchError, '占位.*已保留'):
            m.dispatch(self.args(), timeout)
        before = self.state.read_bytes()
        status = m.concurrency_command(self.args('--concurrency-status'), self.fake)
        self.assertEqual(status['usage']['primary'], 1)
        self.assertEqual(before, self.state.read_bytes())
        reservation = status['reservations'][0]['id']
        m.concurrency_command(self.args('--release-reservation', reservation, '--dry-run'), self.fake)
        self.assertEqual(before, self.state.read_bytes())
        with self.assertRaisesRegex(m.DispatchError, '未知'):
            m.concurrency_command(self.args('--release-reservation', 'unknown'), self.fake)
        m.concurrency_command(self.args('--release-reservation', reservation), self.fake)
        self.assertEqual(json.loads(self.state.read_text())['reservations'], [])

    def test_successful_spawn_counted_once_and_error_turn_releases(self):
        m.dispatch(self.args(), self.fake)
        self.threads = [self.running()]
        status = m.concurrency_command(self.args('--concurrency-status'), self.fake)
        self.assertEqual(status['usage']['primary'], 1)
        self.threads = [self.running(status='error')]
        self.turns['created_1'] = [(int(time.time()) + 1, 'failed')]
        # 清空故障冷却无关：这次仅按槽位释放判断。
        self.assertEqual(m.dispatch(self.args(), self.fake)['selection']['provider'], 'primary')

    def test_state_lock_and_thread_query_failures_do_not_overdispatch(self):
        for contents in ['{', '{"version": 1, "reservations": [null]}']:
            self.state.write_text(contents)
            with self.assertRaisesRegex(m.DispatchError, '并发状态'):
                m.dispatch(self.args(), self.fake)
        self.state.unlink()
        with mock.patch.object(m, 'fcntl', None), self.assertRaisesRegex(m.DispatchError, '文件锁'):
            m.dispatch(self.args(), self.fake)

        def no_list(*args):
            if args[:2] == ('thread', 'list'):
                raise m.DispatchError('thread list failed')
            return self.fake(*args)

        self.assertEqual(m.dispatch(self.args(), no_list)['selection']['provider'], 'specialist')
        self.assertEqual(self.spawn_counter, 1)

    def test_limit_two_counts_each_thread_once(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['primary']['max_concurrency'] = 2
        self.config.write_text(m.yaml.safe_dump(config))
        m.dispatch(self.args(), self.fake)
        m.dispatch(self.args(), self.fake)
        self.threads = [self.running(), {**self.running(), 'id': 'created_2'}]
        result = m.dispatch(self.args(), self.fake)
        self.assertEqual(result['selection']['provider'], 'specialist')
        self.assertIn('2/2', result['selection']['attempts'][0]['error'])

    def test_environment_override_applies_limit_to_actual_provider(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['environments']['env_other']['agents']['specialist']['max_concurrency'] = 1
        self.config.write_text(m.yaml.safe_dump(config))
        self.threads = [{**self.running(), 'providerId': 'remote-provider'}]
        with self.assertRaisesRegex(m.DispatchError, 'remote-provider: 1/1'):
            m.dispatch(self.args('--environment', 'env_other', '--difficulty', 'complex'), self.fake)

    def test_interrupted_or_malformed_spawn_keeps_durable_slot(self):
        for response in ('crash', {}):
            with self.subTest(response=response):
                def broken(*args):
                    if args[:2] == ('thread', 'spawn'):
                        if response == 'crash':
                            raise RuntimeError('unexpected process failure')
                        return response
                    return self.fake(*args)
                with self.assertRaises((m.DispatchError, RuntimeError)):
                    m.dispatch(self.args(), broken)
                self.assertEqual(m.concurrency_command(self.args('--concurrency-status'), self.fake)['usage']['primary'], 1)
                self.state.unlink()

    def test_different_processes_using_different_ledgers_spawn_only_once(self):
        config = Path(self.temp.name) / 'process.yaml'
        config.write_text('''version: 2
defaults: {simple: amp}
agents:
  amp:
    provider: amp
    max_concurrency: 1
    routes: {simple: {model: model}}
''')
        ctx = multiprocessing.get_context('fork')
        start, results = ctx.Event(), ctx.Queue()
        workers = [ctx.Process(target=dispatch_worker, args=(str(config),
                   str(Path(self.temp.name) / f'ledger-{i}.json'), str(self.state), start, results))
                   for i in range(4)]
        for worker in workers:
            worker.start()
        start.set()
        outcomes = [results.get(timeout=10) for _ in workers]
        for worker in workers:
            worker.join(timeout=5)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(outcomes.count('spawned'), 1, outcomes)
        self.assertTrue(all(x == 'spawned' or '并发已满' in x for x in outcomes), outcomes)


    def scoped_config(self):
        config = m.yaml.safe_load(self.config.read_text())
        config['agents']['primary']['concurrency_models'] = ['medium-model', 'deep-model']
        config['agents']['primary']['routes']['complex'] = {'model': 'deep-model'}
        config['defaults']['complex'] = 'primary'
        self.config.write_text(m.yaml.safe_dump(config))
        # 同 provider 的 medium/complex 模型目录。
        def scoped_bb(*args):
            if args[:3] == ('provider', 'models', 'primary'):
                return [{'id': name, 'supportedReasoningEfforts': [{'reasoningEffort': 'max'},
                         {'reasoningEffort': 'high'}]} for name in ['fast-model', 'medium-model', 'deep-model']]
            return self.fake(*args)
        return scoped_bb

    def test_scoped_medium_and_complex_share_one_slot_but_simple_is_unlimited(self):
        bb = self.scoped_config()
        for _ in range(2):
            self.assertEqual(m.dispatch(self.args(), bb)['selection']['provider'], 'primary')
        self.threads = [self.running(), {**self.running(), 'id': 'created_2'}]
        limited = m.dispatch(self.args('--difficulty', 'medium'), bb)
        self.assertEqual(limited['selection']['concurrency']['used'], 0)
        self.threads.append({**self.running(), 'id': 'created_3'})
        with self.assertRaisesRegex(m.DispatchError, '并发已满'):
            m.dispatch(self.args('--difficulty', 'complex', '--ledger', str(self.ledger.with_name('other.json'))), bb)
        simple = m.dispatch(self.args(), bb)
        self.assertEqual(simple['selection']['provider'], 'primary')
        self.assertNotIn('concurrency', simple['selection'])
        self.threads[2]['status'] = 'idle'
        self.turns['created_3'] = [(int(time.time()) + 1, 'completed')]
        self.assertEqual(m.dispatch(self.args('--difficulty', 'complex'), bb)['selection']['provider'], 'primary')

    def test_scoped_unknown_spawn_only_blocks_its_own_model_pool(self):
        bb = self.scoped_config()
        def broken(*args):
            if args[:2] == ('thread', 'spawn'):
                raise m.DispatchError('创建结果未知')
            return bb(*args)
        with self.assertRaises(m.DispatchError):
            m.dispatch(self.args('--difficulty', 'medium'), broken)
        # 受限 medium 的未知占位不能阻止 simple；禁用统计冷却以隔离容量行为。
        self.ledger.unlink(missing_ok=True)
        self.assertEqual(m.dispatch(self.args(), bb)['selection']['provider'], 'primary')
        with self.assertRaisesRegex(m.DispatchError, '并发已满'):
            m.dispatch(self.args('--difficulty', 'complex'), bb)

    def test_unknown_legacy_models_and_external_threads_count_conservatively(self):
        bb = self.scoped_config()
        self.threads = [self.running()]
        with self.assertRaisesRegex(m.DispatchError, '并发已满'):
            m.dispatch(self.args('--difficulty', 'medium'), bb)
        self.threads = []
        self.state.write_text(json.dumps({'version': 1, 'reservations': [
            {'id': 'legacy', 'provider': 'primary', 'ts': int(time.time()), 'thread': None}]}))
        with self.assertRaisesRegex(m.DispatchError, '并发已满'):
            m.dispatch(self.args('--difficulty', 'complex'), bb)
        self.assertEqual(m.dispatch(self.args(), bb)['selection']['provider'], 'primary')

    def test_scope_validation_and_duplicate_aliases_keep_provider_wide_limit(self):
        config = m.yaml.safe_load(self.config.read_text())
        for invalid in [None, [], '', 'medium-model', [1], [' '], [' medium-model']]:
            with self.subTest(invalid=invalid):
                config['agents']['primary']['concurrency_models'] = invalid
                self.config.write_text(m.yaml.safe_dump(config))
                with self.assertRaisesRegex(m.DispatchError, 'concurrency_models'):
                    m.dispatch(self.args(), self.fake)
        config['agents']['primary']['concurrency_models'] = ['medium-model']
        config['agents']['same'] = {'provider': 'primary', 'max_concurrency': 2,
                                    'routes': {'simple': {'model': 'fast-model'}}}
        self.config.write_text(m.yaml.safe_dump(config))
        self.threads = [self.running()]
        self.assertEqual(m.dispatch(self.args('--dry-run'), self.fake)['selection']['provider'], 'specialist')
        config['agents']['primary'].pop('max_concurrency')
        self.config.write_text(m.yaml.safe_dump(config))
        with self.assertRaisesRegex(m.DispatchError, '需要同时配置'):
            m.dispatch(self.args(), self.fake)

    def test_scoped_cross_process_dispatch_allows_simple_and_one_shared_limited_task(self):
        config = Path(self.temp.name) / 'scoped-process.yaml'
        config.write_text('''version: 2
fast: false
defaults: {simple: amp, medium: amp, complex: amp}
agents:
  amp:
    provider: amp
    max_concurrency: 1
    concurrency_models: [model]
    routes:
      simple: {model: simple-model}
      medium: {model: model}
      complex: {model: model}
''')
        ctx = multiprocessing.get_context('fork')
        start = ctx.Event()
        difficulties = ['simple', 'simple', 'medium', 'complex']
        queues = [ctx.Queue() for _ in difficulties]
        workers = [ctx.Process(target=dispatch_worker, args=(str(config),
                   str(Path(self.temp.name) / f'scoped-ledger-{i}.json'), str(self.state), start, queues[i], difficulty))
                   for i, difficulty in enumerate(difficulties)]
        for worker in workers:
            worker.start()
        start.set()
        outcomes = [queue.get(timeout=10) for queue in queues]
        for worker in workers:
            worker.join(timeout=5)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(outcomes[:2], ['spawned', 'spawned'], outcomes)
        self.assertEqual(outcomes[2:].count('spawned'), 1, outcomes)
        self.assertTrue(any('并发已满' in result for result in outcomes[2:]), outcomes)
