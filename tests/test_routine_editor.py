# 流程的步骤编辑框：用任务自己的控件改一步的设置，块用表单改；保存后重开还在，任务自己的设置不变
import json
import unittest
from unittest import mock

from PySide6.QtWidgets import QWidget
from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.routine.editor_dialog import RoutineEditor
from src.tasks.fullauto import RoutineTask as R
from src.tasks.fullauto.AutoDailyClaimTask import AutoDailyClaimTask
from src.tasks.fullauto.AutoNightbookTask import AutoNightbookTask


class TestRoutineEditor(TaskTestCase):
    task_class = R.RoutineTask
    config = config

    def setUp(self):
        executor = self.task.executor
        self.book = AutoNightbookTask(executor, None)
        self.book.config = {**self.book.default_config, '刷几次': 0}
        self.daily = AutoDailyClaimTask(executor, None)
        self.daily.config = dict(self.daily.default_config)
        patcher = mock.patch.object(executor, 'onetime_tasks', [self.daily, self.book, self.task])
        patcher.start()
        self.addCleanup(patcher.stop)
        # 换成普通 dict，免得测试改写真实的 configs/RoutineTask.json
        saved = self.task.config
        self.task.config = {'步骤': R.DEFAULT_STEPS}
        self.addCleanup(setattr, self.task, 'config', saved)
        self.parent = QWidget()

    def editor(self):
        return RoutineEditor(self.task, self.parent)

    def control(self, editor, key):
        container = editor.settings_area.widget()
        return next(w for w in container.findChildren(QWidget) if getattr(w, 'key', None) == key)

    def test_build_two_steps_save_and_reopen(self):
        editor = self.editor()
        self.assertEqual(editor.list.count(), 1)
        editor.task_box.setCurrentIndex(editor.task_box.findData('AutoNightbookTask'))
        editor.add_step()
        editor.move(-1)
        self.control(editor, '刷几次').spin_box.setValue(1)
        self.assertEqual(editor.list.item(0).text(), '1. 自动夜航手册（刷几次=1）')
        self.assertTrue(editor.validate())

        saved = json.loads(self.task.config['步骤'])
        self.assertEqual(saved['steps'], [{'task': 'AutoNightbookTask', 'overrides': {'刷几次': 1}},
                                          {'task': 'AutoDailyClaimTask', 'overrides': {}}])
        self.assertEqual(self.book.config['刷几次'], 0)

        reopened = self.editor()
        self.assertEqual([reopened.list.item(i).text() for i in range(reopened.list.count())],
                         ['1. 自动夜航手册（刷几次=1）', '2. 日常领奖'])
        self.assertEqual(self.control(reopened, '刷几次').spin_box.value(), 1)

    def test_touched_value_is_kept_even_when_it_matches_the_task(self):
        editor = self.editor()
        editor.task_box.setCurrentIndex(editor.task_box.findData('AutoNightbookTask'))
        editor.add_step()
        spin = self.control(editor, '刷几次').spin_box
        spin.setValue(2)
        spin.setValue(0)
        self.assertTrue(editor.validate())
        self.assertEqual(json.loads(self.task.config['步骤'])['steps'][1]['overrides'], {'刷几次': 0})

    def test_reset_clears_the_step_changes(self):
        editor = self.editor()
        editor.task_box.setCurrentIndex(editor.task_box.findData('AutoNightbookTask'))
        editor.add_step()
        self.control(editor, '刷几次').spin_box.setValue(3)
        editor.reset_step()
        self.assertEqual(editor.list.item(1).text(), '2. 自动夜航手册')
        self.assertEqual(self.control(editor, '刷几次').spin_box.value(), 0)

    def test_remove_and_empty_routine_is_refused(self):
        editor = self.editor()
        editor.remove_step()
        self.assertEqual(editor.list.count(), 0)
        self.assertFalse(editor.validate())
        self.assertIn('至少要有一步', editor.error.text())
        self.assertEqual(self.task.config['步骤'], R.DEFAULT_STEPS)

    def test_unreadable_steps_start_empty_with_a_message(self):
        self.task.config['步骤'] = '{'
        editor = self.editor()
        self.assertEqual(editor.list.count(), 0)
        self.assertIn('读不出来', editor.error.text())

    def add(self, editor, kind):
        editor.task_box.setCurrentIndex(editor.task_box.findData(kind))
        editor.add_step()
        return editor.form

    def labels(self, editor):
        return [editor.list.item(i).text() for i in range(editor.list.count())]

    def saved(self):
        return json.loads(self.task.config['步骤'])['steps']

    def test_build_a_letter_loop_save_and_reopen(self):
        editor = self.editor()
        editor.list.setCurrentRow(0)
        loop = self.add(editor, 'loop')
        loop.hours.setValue(10)
        loop.conds.add_row()
        fact, value, _ = loop.conds.rows[0]
        fact.setCurrentText('密函还有')
        value.setCurrentText('否')
        self.add(editor, 'AutoNightbookTask')
        self.add(editor, 'wait').minutes.setValue(3)
        expected = ['1. 日常领奖', '2. 循环（10 小时，或 密函还有=否）', '    2.1. 自动夜航手册', '    2.2. 等待 3 分钟']
        self.assertEqual(self.labels(editor), expected)
        self.assertTrue(editor.validate(), editor.error.text())
        self.assertEqual(self.saved(), [
            {'task': 'AutoDailyClaimTask', 'overrides': {}},
            {'loop': {'hours': 10, 'until': [['密函还有', '否']]},
             'steps': [{'task': 'AutoNightbookTask', 'overrides': {}}, {'wait': {'minutes': 3}}]},
        ])
        self.assertEqual(self.labels(self.editor()), expected)

    def test_move_a_step_into_and_out_of_a_loop(self):
        editor = self.editor()
        editor.list.setCurrentRow(0)
        self.add(editor, 'loop')
        self.add(editor, 'check')
        editor.list.setCurrentRow(0)
        editor.move(1)
        self.assertEqual(self.labels(editor), ['1. 循环（4 小时）', '    1.1. 检查委托密函', '2. 日常领奖'])
        editor.move_in()
        self.assertEqual(self.labels(editor), ['1. 循环（4 小时）', '    1.1. 检查委托密函', '    1.2. 日常领奖'])
        self.assertEqual(editor.list.currentRow(), 2)
        editor.move_out()
        self.assertEqual(self.labels(editor), ['1. 循环（4 小时）', '    1.1. 检查委托密函', '2. 日常领奖'])

    def test_wait_for_a_condition_and_an_if(self):
        editor = self.editor()
        editor.list.setCurrentRow(0)
        wait = self.add(editor, 'wait')
        wait.mode.setCurrentIndex(1)
        wait.most.setValue(70)
        facts = wait.conds.rows[0][0]
        self.assertEqual([facts.itemText(i) for i in range(facts.count())], ['有无尽委托', '密函还有'])
        when = self.add(editor, 'if')
        when.then.setCurrentText('结束流程')
        fact, value, _ = when.conds.rows[0]
        fact.setCurrentText('上一步结果')
        value.setCurrentText('跳过')
        self.assertEqual(self.labels(editor)[1:], ['2. 等到 有无尽委托=是（每次轮换后看一次，最多 70 分钟）',
                                                   '3. 如果 上一步结果=跳过 → 结束流程'])
        self.assertTrue(editor.validate(), editor.error.text())
        self.assertEqual(self.saved()[1:], [
            {'wait': {'until': [['有无尽委托', '是']], 'every': 0, 'most': 70}},
            {'if': [['上一步结果', '跳过']], 'then': '结束流程'},
        ])

    def test_a_loop_without_a_limit_is_refused(self):
        editor = self.editor()
        editor.list.setCurrentRow(0)
        self.add(editor, 'loop').hours.setValue(0)
        self.add(editor, 'check')
        self.assertFalse(editor.validate())
        self.assertIn('次数、小时或结束时间', editor.error.text())
        self.assertEqual(self.task.config['步骤'], R.DEFAULT_STEPS)

    def test_remove_a_condition(self):
        editor = self.editor()
        editor.list.setCurrentRow(0)
        loop = self.add(editor, 'loop')
        loop.conds.add_row()
        loop.conds.remove_row(0)
        self.assertEqual(loop.conds.rows, [])
        self.assertEqual(editor.list.item(1).text(), '2. 循环（4 小时）')


if __name__ == '__main__':
    unittest.main()
