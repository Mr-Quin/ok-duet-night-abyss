# 流程的步骤编辑框：用任务自己的控件改一步的设置，保存后重开还在，任务自己的设置不变
import json
import unittest
from unittest import mock

from PySide6.QtWidgets import QWidget
from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.routine.editor_dialog import RoutineEditor
from src.routine.steps import overrides_from
from src.tasks.fullauto import RoutineTask as R
from src.tasks.fullauto.AutoDailyClaimTask import AutoDailyClaimTask
from src.tasks.fullauto.AutoNightbookTask import AutoNightbookTask


class TestOverridesFrom(unittest.TestCase):

    def test_only_changed_values(self):
        self.assertEqual(overrides_from({'刷几次': 1, '来源': '夜航手册'}, {'刷几次': 0, '来源': '夜航手册'}),
                         {'刷几次': 1})


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


if __name__ == '__main__':
    unittest.main()
