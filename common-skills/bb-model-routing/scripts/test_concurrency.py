"""容量控制的行为与真实跨进程互斥；不调用线上 BB。"""
import json
import multiprocessing
from pathlib import Path
import time
import unittest
from unittest import mock

import test_dispatch as fixtures

m = fixtures.m


# 独立进程使用不同账本，唯一共享的是用户级并发状态。
def dispatch_worker(config, ledger, state, start, results):
    m.CONCURRENCY_PATH = Path(state)
    args = m.parser().parse_args(['--config', config, '--ledger', ledger,
                                  '--difficulty', 'simple', '--task', '并行任务',
                                  '--project', 'proj', '--environment', 'env'])

    def bb(*argv):
        if argv[:2] == ('environment', 'show'):
            return {'id': 'env', 'projectId': 'proj'}
        if argv[:2] == ('provider', 'list'):
            return [{'id': 'amp', 'available': True, 'capabilities': {'permissionModes': ['accept-edits']}}]
        if argv[:2] == ('provider', 'models'):
            return [{'id': 'model'}]
        if argv[:2] == ('thread', 'show'):
            return {'thread': {'id': 'parent'}}
        if argv[:2] == ('thread', 'list'):
            return []  # 模拟创建成功后线程尚未出现在列表中。
        if argv[:2] == ('thread', 'spawn'):
            time.sleep(0.15)  # 扩大无锁实现会超发的窗口。
            return {'id': 'created', 'status': 'active'}
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
                'queuedWork': queued, 'hasPendingInteraction': interaction}

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
                                             ('error', 'waiting', False)]:
            with self.subTest(status=status, queued=queued, interaction=interaction):
                self.threads = [self.running(status, queued, interaction)]
                result = m.dispatch(self.args('--dry-run'), self.fake)
                self.assertEqual(result['selection']['provider'], 'specialist')
                self.assertIn('并发已满', result['selection']['attempts'][0]['error'])
        self.assertFalse(self.state.exists())
        self.assertFalse(any(c[:2] == ('thread', 'spawn') for c in self.calls))

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
