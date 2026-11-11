"""流程的步骤编辑框：增删、排序步骤，每一步用任务自己的设置控件改这一步的临时设置。"""
import json

from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, FluentIcon, ListWidget, MessageBoxBase, PushButton, SubtitleLabel

from ok.ui.qt.tasks.ConfigItemFactory import config_widget
from src.routine.steps import ALLOWED, Step, StepError, dump_steps, parse_steps, spec_of

# 这些控件不是存一个值的，放进一步的设置里没有意义
SKIPPED_TYPES = ('button', 'global')


class StepSettings(dict):
    """一步的设置：任务存下来的设置叠上这一步的临时设置。控件改的是这份，不会写进任务的配置文件。

    动过的项都算这一步的临时设置，哪怕和任务现在的设置一样：任务的设置以后会变，这一步不该跟着变。
    """

    def __init__(self, task, overrides):
        super().__init__(task.config)
        self.update(overrides)
        self.defaults = task.default_config
        self.touched = set(overrides)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.touched.add(key)

    def get_default(self, key):
        return self.defaults.get(key)

    def overrides(self):
        return {key: self[key] for key in self if key in self.touched}


class RoutineEditor(MessageBoxBase):

    def __init__(self, routine, parent):
        super().__init__(parent)
        self.routine = routine
        self.tasks = {type(t).__name__: t for t in routine.executor.onetime_tasks if type(t).__name__ in ALLOWED}
        self.rows = []
        self.locked = False
        self.error = BodyLabel('', self)
        self.error.setWordWrap(True)
        try:
            steps, _ = routine.steps()
            if not all(isinstance(s, Step) for s in steps):
                self.locked = True
                raise StepError('流程里有检查、等待或循环，这里还改不了，保存不会动它')
            self.rows = [(s.task, StepSettings(self.tasks[s.task], s.overrides)) for s in steps]
        except StepError as e:
            self.error.setText(str(e))
        except Exception as e:
            self.error.setText(f'存下来的步骤读不出来，从空的开始：{e}')

        self.list = ListWidget(self)
        self.list.currentRowChanged.connect(self.show_settings)
        self.task_box = ComboBox(self)
        for name, task in self.tasks.items():
            self.task_box.addItem(task.name, userData=name)
        add = PushButton(FluentIcon.ADD, '添加', self)
        add.clicked.connect(self.add_step)
        up = PushButton(FluentIcon.UP, '上移', self)
        up.clicked.connect(lambda: self.move(-1))
        down = PushButton(FluentIcon.DOWN, '下移', self)
        down.clicked.connect(lambda: self.move(1))
        remove = PushButton(FluentIcon.REMOVE, '删除', self)
        remove.clicked.connect(self.remove_step)

        add_row = QHBoxLayout()
        add_row.addWidget(self.task_box, 1)
        add_row.addWidget(add)
        move_row = QHBoxLayout()
        for button in (up, down, remove):
            move_row.addWidget(button)
        left = QVBoxLayout()
        left.addWidget(SubtitleLabel('步骤', self))
        left.addWidget(self.list, 1)
        left.addLayout(add_row)
        left.addLayout(move_row)

        self.settings_area = QScrollArea(self)
        self.settings_area.setWidgetResizable(True)
        self.settings_area.setMinimumWidth(560)
        reset = PushButton(FluentIcon.CANCEL, '清除这一步的改动', self)
        reset.clicked.connect(self.reset_step)
        right = QVBoxLayout()
        right.addWidget(SubtitleLabel('这一步的设置', self))
        right.addWidget(BodyLabel('动过的项只在这个流程的这一步生效，不改任务自己的设置', self))
        right.addWidget(self.settings_area, 1)
        right.addWidget(reset)

        body = QHBoxLayout()
        body.addLayout(left, 2)
        body.addLayout(right, 3)
        self.viewLayout.addLayout(body)
        self.viewLayout.addWidget(self.error)
        self.yesButton.setText('保存')
        self.cancelButton.setText('取消')
        self.widget.setMinimumSize(980, 620)

        self.refresh(0)

    def label(self, row):
        name, settings = self.rows[row]
        extra = '，'.join(f'{k}={v}' for k, v in settings.overrides().items())
        return f'{row + 1}. {self.tasks[name].name}' + (f'（{extra}）' if extra else '')

    def refresh(self, current):
        self.list.blockSignals(True)
        self.list.clear()
        for row in range(len(self.rows)):
            self.list.addItem(self.label(row))
        self.list.blockSignals(False)
        if self.rows:
            self.list.setCurrentRow(max(0, min(current, len(self.rows) - 1)))
        self.show_settings(self.list.currentRow())

    def show_settings(self, row):
        container = QWidget()
        layout = QVBoxLayout(container)
        if 0 <= row < len(self.rows):
            name, settings = self.rows[row]
            task = self.tasks[name]
            for key, value in settings.items():
                type_spec = (task.config_type or {}).get(key)
                if key.startswith('_') or key not in task.default_config or \
                        isinstance(type_spec, dict) and type_spec.get('type') in SKIPPED_TYPES:
                    continue
                widget = config_widget(task.config_type, task.config_description, settings, key, value, task)
                if hasattr(widget, 'update_config'):
                    widget.update_config = self.tracked(widget.update_config, row)
                layout.addWidget(widget)
        layout.addStretch(1)
        self.settings_area.setWidget(container)

    def tracked(self, update, row):
        # 只改列表里这一行的文字：在控件自己的信号里重建设置区会把正在发信号的控件删掉
        def update_and_relabel(value):
            update(value)
            self.list.item(row).setText(self.label(row))
        return update_and_relabel

    def add_step(self):
        name = self.task_box.currentData()
        if name:
            self.rows.append((name, StepSettings(self.tasks[name], {})))
            self.refresh(len(self.rows) - 1)

    def move(self, delta):
        row = self.list.currentRow()
        target = row + delta
        if 0 <= row < len(self.rows) and 0 <= target < len(self.rows):
            self.rows[row], self.rows[target] = self.rows[target], self.rows[row]
            self.refresh(target)

    def reset_step(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.rows):
            name = self.rows[row][0]
            self.rows[row] = (name, StepSettings(self.tasks[name], {}))
            self.refresh(row)

    def remove_step(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.rows):
            del self.rows[row]
            self.refresh(row)

    def steps_json(self):
        if not self.rows:
            raise StepError('流程里至少要有一步')
        steps = [Step(name, settings.overrides()) for name, settings in self.rows]
        raw = dump_steps(steps)
        parse_steps(raw, {name: spec_of(task) for name, task in self.tasks.items()})
        return json.dumps(raw, ensure_ascii=False, indent=1)

    def validate(self):
        if self.locked:
            return True
        try:
            text = self.steps_json()
        except StepError as e:
            self.error.setText(f'保存不了：{e}')
            return False
        self.routine.config['步骤'] = text
        return True
