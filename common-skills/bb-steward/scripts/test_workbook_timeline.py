"""验证可见时间、排序、稳定编号与真实 CLI 提交流程。"""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workbook_timeline import format_timeline, SGT

NOW = datetime(2026, 11, 15, 4, 30, 45, tzinfo=timezone.utc)
BOOK = """# 交付

## 路线

- [ ] 阶段 1：旧工作 ← 等用户
  说明保留在原事项下。
- [ ] 阶段 2：新工作 ← 排在 阶段 1 后：验收

## 关键决策

- 保留原样。

## 用户待办

| 编号 | 状态 | 事项 | 挡住 | 提出 |
| --- | --- | --- | --- | --- |
| D1 | 待办 | 旧事项 | 阶段 1 | 2026-11-01 |
| D2 | 待办 | 新事项 | 不挡 | 2026-11-14 |
"""


class TimelineTests(unittest.TestCase):
    def test_transition_dates_and_sorts_without_renumbering(self):
        before, _ = format_timeline(BOOK, BOOK, NOW)
        edited = before.replace('[ ] 阶段 1', '[x] 阶段 1').replace('D1 | 待办', 'D1 | 已完成')
        after, warnings = format_timeline(edited, before, NOW)
        self.assertFalse(warnings)
        self.assertIn('（完成：2026-11-15 12:30:45 SGT）', after)
        self.assertIn('| D1 | 已完成 | 旧事项 | 阶段 1 | 2026-11-01 | 2026-11-15 12:30:45 SGT |', after)
        self.assertLess(after.index('| D1 |'), after.index('| D2 |'))
        self.assertIn('  说明保留在原事项下。', after)
        later = datetime(2026, 11, 16, tzinfo=SGT)
        self.assertEqual(after, format_timeline(after, before, later)[0])

    def test_pending_dates_descending_and_new_route_goes_first(self):
        before, _ = format_timeline(BOOK, BOOK, NOW)
        after, _ = format_timeline(before.replace('## 关键决策', '- [ ] 阶段 3：新增\n\n## 关键决策'),
                                   before, datetime(2026, 11, 16, tzinfo=SGT))
        self.assertLess(after.index('阶段 3'), after.index('阶段 1'))
        self.assertLess(after.index('| D2 |'), after.index('| D1 |'))
        self.assertIn('- 保留原样。', after)

    def test_unknown_history_is_not_stamped_as_today(self):
        done = BOOK.replace('[ ] 阶段 1', '[x] 阶段 1').replace('D1 | 待办', 'D1 | 已完成')
        after, warnings = format_timeline(done, done, NOW)
        self.assertEqual(len(warnings), 2)
        self.assertIn('（完成：待核实）', after)
        self.assertIn('| D1 | 已完成 | 旧事项 | 阶段 1 | 2026-11-01 | 待核实 |', after)
        self.assertLess(after.index('阶段 2'), after.index('阶段 1'))
        self.assertLess(after.index('| D2 |'), after.index('| D1 |'))

    def test_reopen_then_complete_gets_new_time(self):
        before, _ = format_timeline(BOOK, BOOK, NOW)
        done, _ = format_timeline(before.replace('[ ] 阶段 1', '[x] 阶段 1').replace('D1 | 待办', 'D1 | 已完成'), before, NOW)
        reopened, _ = format_timeline(done.replace('[x] 阶段 1', '[ ] 阶段 1').replace('D1 | 已完成', 'D1 | 待办'), done, NOW)
        self.assertNotIn('（完成：', reopened)
        later = datetime(2026, 11, 16, tzinfo=SGT)
        again, _ = format_timeline(reopened.replace('[ ] 阶段 1', '[x] 阶段 1').replace('D1 | 待办', 'D1 | 已完成'), reopened, later)
        self.assertIn('（完成：2026-11-16 00:00:00 SGT）', again)
        self.assertIn('| 2026-11-01 | 2026-11-16 00:00:00 SGT |', again)

    def test_escaped_pipes_and_traditional_headings(self):
        book = BOOK.replace('## 路线', '## 路線').replace('## 用户待办', '## 用戶待辦').replace('旧事项', r'旧\|事项')
        after, _ = format_timeline(book, book, NOW)
        self.assertIn(r'旧\|事项', after)
        self.assertLess(after.index('| D2 |'), after.index('| D1 |'))

    def test_same_time_is_stable_and_missing_columns_added(self):
        book = BOOK.replace('| 提出 |', '| 说明 |').replace('2026-11-01', '背景一').replace('2026-11-14', '背景二')
        once, _ = format_timeline(book, book, NOW)
        self.assertIn('| 说明 | 提出 | 完成 |', once)
        self.assertLess(once.index('| D1 |'), once.index('| D2 |'))
        self.assertEqual(once, format_timeline(once, book, NOW)[0])

    def test_cli_uses_file_repository_head_and_is_idempotent(self):
        script = Path(__file__).with_name('steward_workbook.py').resolve()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.run(['git', '-C', folder, *args], check=True, capture_output=True)
            git('init')
            path = root / 'workbook.md'
            path.write_text(BOOK)
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'initial')
            path.write_text(BOOK.replace('[ ] 阶段 1', '[x] 阶段 1').replace('D1 | 待办', 'D1 | 已完成'))
            run = lambda: subprocess.run([sys.executable, str(script), '--mode', 'format', '--file', str(path)],
                                          check=True, capture_output=True, text=True)
            run()
            once = path.read_text()
            self.assertNotIn('待核实', once)
            self.assertIn('SGT', once)
            self.assertLess(once.index('| D1 |'), once.index('| D2 |'))
            run()
            self.assertEqual(once, path.read_text())
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'complete')
            run()
            self.assertEqual(once, path.read_text())


if __name__ == '__main__':
    unittest.main()
