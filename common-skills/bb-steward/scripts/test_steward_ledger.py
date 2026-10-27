import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import steward_workbook as sw
from test_steward_workbook import VALID_WORKBOOK


FIXTURE = (Path(__file__).parent / 'fixtures' / '要求帳.md').read_text()


def ledger_row(status='完成', result='CI 21→8 分（-62%）', material='PR #117'):
    return ('# 使用者要求帳\n\n## 2026-10-27 起（效率）\n\n'
            '| 日期 | 要求 | 狀態 | 結果 | 材料 |\n'
            '| --- | --- | --- | --- | --- |\n'
            f'| 10-27 | 優化 CI | {status} | {result} | {material} |\n')


class LedgerTests(unittest.TestCase):
    def test_sample_shaped_fixture_with_multiple_periods_and_all_states(self):
        res = sw.check_ledger(FIXTURE)
        self.assertTrue(res['ok'], res['errors'])
        self.assertEqual(res['stats'], {'periods': 2, 'rows': 8})
        self.assertEqual(sum(res['summary'].values()), 8)
        self.assertEqual(res['summary']['進行中'], 1)
        self.assertEqual(res['summary']['待使用者'], 1)

    def test_accepts_locatable_materials_and_specific_qualitative_results(self):
        for material in ('[報告](report.md)', 'PR #117', 'commit 7f3b384',
                         '/tmp/report.md', '../analysis/report.md', '會話回覆 10-27',
                         '会话回复', 'https://example.org/report'):
            for status in ('完成', '採納'):
                with self.subTest(material=material, status=status):
                    self.assertTrue(sw.check_ledger(ledger_row(status, '新增主資料編輯彈窗', material))['ok'])

    def test_ledger_is_not_limited_to_one_screen(self):
        text = ledger_row() + ledger_row().splitlines()[-1] + '\n'
        text += (ledger_row().splitlines()[-1] + '\n') * 60
        self.assertTrue(sw.check_ledger(text)['ok'])
        self.assertGreater(sw.check_ledger(text)['stats']['rows'], 45)

    def test_rejects_bad_structure(self):
        valid = ledger_row()
        cases = [valid.replace('## 2026-10-27 起（效率）', ''),
                 valid.replace('## 2026-10-27 起（效率）', '## 效率'),
                 valid.replace('狀態 | 結果', '結果 | 狀態'),
                 valid.replace('| --- | --- | --- | --- | --- |\n', ''),
                 valid.replace('| PR #117 |', '| PR #117 | 多一欄 |'),
                 valid + '\n| 日期 | 要求 | 狀態 | 結果 | 材料 |\n| --- | --- | --- | --- | --- |\n',
                 '# 要求帳\n',
                 '# 要求帳\n## 2026-10-27 起（效率）\n無表格\n']
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(sw.check_ledger(text)['ok'])

    def test_rejects_unknown_state_and_missing_fields(self):
        for text in (ledger_row('已完成'), ledger_row().replace('| 10-27 |', '| |'),
                     ledger_row().replace('| 優化 CI |', '| — |')):
            self.assertFalse(sw.check_ledger(text)['ok'])

    def test_rejects_empty_or_vacuous_results_for_every_state(self):
        for status in sw.LEDGER_STATES:
            for result in ('', '—', '完成', '已完成。', '**已完成**', '已採納', '已處理！', 'done', '已全部完成', '已經全部完成了'):
                with self.subTest(status=status, result=result):
                    res = sw.check_ledger(ledger_row(status, result))
                    self.assertFalse(res['ok'])
                    self.assertTrue(any('第 7 行' in e and '具体结论' in e for e in res['errors']))

    def test_escaped_pipe_in_requirement_preserves_five_columns(self):
        text = ledger_row().replace('優化 CI', r'優化 CI \| 文件檢查')
        self.assertTrue(sw.check_ledger(text)['ok'])

    def test_terminal_states_need_material(self):
        for status in ('完成', '採納'):
            for material in ('', '—', '待補', '已交付', '本機預覽 feedback-batch-c（至 11-03）', '[報告]()'):
                with self.subTest(status=status, material=material):
                    self.assertFalse(sw.check_ledger(ledger_row(status, material=material))['ok'])

    def test_superseded_requires_named_replacement(self):
        for result in ('已被覆蓋', '後續處理', '被取代', '被 — 取代', '被後續要求取代', '由於需求已改變', '理由尚待確認'):
            self.assertFalse(sw.check_ledger(ledger_row('被覆蓋', result))['ok'], result)
        for result in ('被「紅框報告」列取代', '由紅框版報告取代', '改為紅框版報告'):
            self.assertTrue(sw.check_ledger(ledger_row('被覆蓋', result))['ok'], result)

    def test_excluded_requires_reason(self):
        for result in ('', '排除', '已排除', '取消', '不做', '不採納', '不執行', '排除這個要求', '已取消该需求'):
            self.assertFalse(sw.check_ledger(ledger_row('排除', result))['ok'], result)
        self.assertTrue(sw.check_ledger(ledger_row('排除', '使用者只採納 1、3、5'))['ok'])

    def test_cli_returns_json_and_correct_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '要求帳.md'
            for text, expected in ((FIXTURE, 0), (ledger_row('未知'), 2)):
                path.write_text(text)
                proc = subprocess.run([sys.executable, str(Path(sw.__file__)), '--mode', 'ledger-check',
                                       '--file', str(path)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, expected, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)['ok'], expected == 0)

    def test_workbook_entry_resolves_relative_to_workbook_not_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / '工作簿.md'
            ledger = root / '領域設計-要求帳.md'
            path.write_text(VALID_WORKBOOK.replace('\n## 路线', '\n逐项见[要求帐](領域設計-要求帳.md)。\n\n## 路线', 1))
            self.assertFalse(sw.check_workbook_file(path)['ok'])
            ledger.write_text(FIXTURE)
            self.assertTrue(sw.check_workbook_file(path)['ok'])
            path.write_text(path.read_text().replace('領域設計-要求帳.md', '%E9%A0%98%E5%9F%9F%E8%A8%AD%E8%A8%88-要求帳.md#結果'))
            self.assertTrue(sw.check_workbook_file(path)['ok'])

    def test_check_cli_checks_entry_without_requiring_one_for_legacy_workbooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'workbook.md'
            for link, expected in (('', 0), ('[逐项记录](topic-要求帳.md)', 2),
                                   ('[要求帳](https://example.org/ledger.md)', 2)):
                path.write_text(VALID_WORKBOOK.replace('\n## 路线', f'\n{link}\n\n## 路线', 1))
                with patch.object(sys, 'argv', ['steward_workbook', '--mode', 'check', '--file', str(path)]):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(sw.main(), expected)
                    self.assertEqual(json.loads(output.getvalue())['ok'], expected == 0)


if __name__ == '__main__':
    unittest.main()
