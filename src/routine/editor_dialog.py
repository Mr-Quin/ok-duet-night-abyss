"""流程的步骤编辑框：增删、排序步骤和块，任务用它自己的设置控件改这一步的临时设置，
检查、等待、循环和「如果」用这里的表单。循环里的步骤缩进显示在循环下面。"""
import json

from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, ComboBox, FluentIcon, LineEdit, ListWidget, MessageBoxBase, PushButton,
                            SpinBox, SubtitleLabel)

from ok.ui.qt.tasks.ConfigItemFactory import config_widget
from src.routine.steps import (ACTIONS, ALLOWED, BREAK, ENDLESS, FACTS, LETTER_FACTS, LETTERS_LEFT, Check, If, Loop,
                               Step, StepError, Wait, describe, dump_steps, parse_steps, spec_of)

# 这些控件不是存一个值的，放进一步的设置里没有意义
SKIPPED_TYPES = ('button', 'global')
BLOCKS = (('检查委托密函', 'check'), ('等待', 'wait'), ('循环', 'loop'), ('如果', 'if'))
INDENT = '    '


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


class TaskNode:
    kind = 'task'

    def __init__(self, task, settings):
        self.task, self.settings = task, settings

    def step(self):
        return Step(self.task.__class__.__name__, self.settings.overrides())


class BlockNode:
    """检查、等待、循环或「如果」，fields 是表单改的值，循环的 children 是里面的步骤。"""

    def __init__(self, kind, fields=None, children=None):
        self.kind = kind
        self.fields = fields if fields is not None else new_fields(kind)
        self.children = children if children is not None else []

    def step(self, children=()):
        f = self.fields
        if self.kind == 'check':
            return Check()
        if self.kind == 'wait':
            if f['mode'] == 'minutes':
                return Wait(minutes=f['minutes'])
            return Wait(until=cond(f['until']), every=f['every'], most=f['most'])
        if self.kind == 'loop':
            return Loop(tuple(children), times=f['times'], hours=f['hours'], until_time=f['until_time'].strip(),
                        until=cond(f['until']))
        return If(cond(f['when']), f['then'])


def cond(rows):
    return tuple((name, value) for name, value in rows)


def new_fields(kind):
    if kind == 'wait':
        return {'mode': 'minutes', 'minutes': 30, 'until': [[ENDLESS, '是']], 'every': 0, 'most': 60}
    if kind == 'loop':
        return {'times': 0, 'hours': 4, 'until_time': '', 'until': []}
    if kind == 'if':
        return {'when': [[LETTERS_LEFT, '否']], 'then': BREAK}
    return {}


def node_of(step, tasks):
    if isinstance(step, Step):
        return TaskNode(tasks[step.task], StepSettings(tasks[step.task], step.overrides))
    if isinstance(step, Check):
        return BlockNode('check')
    rows = lambda c: [[name, value] for name, value in c]
    if isinstance(step, Wait):
        fields = new_fields('wait')
        if step.until:
            fields.update(mode='until', until=rows(step.until), every=step.every, most=step.most)
        else:
            fields['minutes'] = step.minutes
        return BlockNode('wait', fields)
    if isinstance(step, Loop):
        fields = {'times': step.times, 'hours': step.hours, 'until_time': step.until_time, 'until': rows(step.until)}
        return BlockNode('loop', fields, [node_of(s, tasks) for s in step.steps])
    return BlockNode('if', {'when': rows(step.when), 'then': step.then})


def to_steps(nodes):
    return [n.step(to_steps(n.children)) if n.kind == 'loop' else n.step() for n in nodes]


class ConditionList(QWidget):
    """「任一条成立」的条件，每行一个名字下拉框和一个值下拉框。直接改 rows_data 这个列表。"""

    def __init__(self, rows_data, facts, changed, parent=None):
        super().__init__(parent)
        self.data, self.facts, self.changed = rows_data, facts, changed
        self.rows = []
        self.line_widgets = []
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.lines = QVBoxLayout()
        self.box.addLayout(self.lines)
        add = PushButton(FluentIcon.ADD, '添加条件', self)
        add.clicked.connect(self.add_row)
        self.box.addWidget(add)
        self.build()

    def build(self):
        # 删除按钮在自己的 clicked 里触发重建，旧控件只能 deleteLater
        for line in self.line_widgets:
            line.hide()
            line.deleteLater()
        self.line_widgets, self.rows = [], []
        for i, (name, current) in enumerate(self.data):
            line = QWidget(self)
            row = QHBoxLayout(line)
            row.setContentsMargins(0, 0, 0, 0)
            fact = ComboBox(line)
            fact.addItems(list(self.facts))
            fact.setCurrentText(name)
            value = ComboBox(line)
            value.addItems(list(FACTS[name]))
            value.setCurrentText(current)
            remove = PushButton(FluentIcon.REMOVE, '', line)
            fact.currentTextChanged.connect(lambda text, i=i: self.set_fact(i, text))
            value.currentTextChanged.connect(lambda text, i=i: self.set_value(i, text))
            remove.clicked.connect(lambda _=False, i=i: self.remove_row(i))
            row.addWidget(fact, 1)
            row.addWidget(value, 1)
            row.addWidget(remove)
            self.lines.addWidget(line)
            self.line_widgets.append(line)
            self.rows.append((fact, value, remove))

    def set_fact(self, i, name):
        self.data[i] = [name, FACTS[name][0]]
        value = self.rows[i][1]
        value.blockSignals(True)
        value.clear()
        value.addItems(list(FACTS[name]))
        value.setCurrentText(FACTS[name][0])
        value.blockSignals(False)
        self.changed()

    def set_value(self, i, text):
        self.data[i][1] = text
        self.changed()

    def add_row(self):
        name = next(iter(self.facts))
        self.data.append([name, FACTS[name][0]])
        self.build()
        self.changed()

    def remove_row(self, i):
        del self.data[i]
        self.build()
        self.changed()


class BlockForm(QWidget):
    """检查、等待、循环、「如果」的设置表单。控件直接改 node.fields，改完调 changed 刷新列表里那一行。"""

    def __init__(self, node, changed, parent=None):
        super().__init__(parent)
        self.node, self.changed = node, changed
        self.layout_ = QVBoxLayout(self)
        f = node.fields
        if node.kind == 'check':
            self.note('到委托密函页签看一眼，记下还有密函的栏里有没有无尽委托、还有没有密函，不进委托')
        elif node.kind == 'wait':
            self.mode = self.combo('怎么等', ['等一段时间', '等到条件满足'], 0 if f['mode'] == 'minutes' else 1,
                                   self.set_mode)
            self.minutes = self.spin('等几分钟', f, 'minutes', 1, 24 * 60)
            self.conds = self.conditions('等到下面任一条成立（会去委托密函看）', f['until'], LETTER_FACTS)
            self.every = self.spin('隔几分钟看一次；0 为每次整点轮换后看', f, 'every', 0, 24 * 60)
            self.most = self.spin('最多等几分钟，到了就往下走，算跳过', f, 'most', 1, 24 * 60)
            self.show_mode()
        elif node.kind == 'loop':
            self.note('任一个结束条件满足就停；次数、小时、结束时间至少给一个')
            self.times = self.spin('最多几次；0 为不限', f, 'times', 0, 10000)
            self.hours = self.spin('最多几小时；0 为不限', f, 'hours', 0, 72)
            self.label('到几点结束（HH:MM，比如 06:00；过了就是明天）；空着为不限')
            self.until_time = LineEdit(self)
            self.until_time.setText(f['until_time'])
            self.until_time.textChanged.connect(lambda text: self.set('until_time', text))
            self.layout_.addWidget(self.until_time)
            self.conds = self.conditions('或者下面任一条成立时结束（每次开始前看）', f['until'], FACTS)
        else:
            self.conds = self.conditions('下面任一条成立时', f['when'], FACTS)
            self.then = self.combo('就', list(ACTIONS), ACTIONS.index(f['then']),
                                   lambda i: self.set('then', ACTIONS[i]))
        self.layout_.addStretch(1)

    def note(self, text):
        label = BodyLabel(text, self)
        label.setWordWrap(True)
        self.layout_.addWidget(label)

    def label(self, text):
        label = BodyLabel(text, self)
        self.layout_.addWidget(label)
        return label

    def set(self, key, value):
        self.node.fields[key] = value
        self.changed()

    def spin(self, title, fields, key, low, high):
        label = self.label(title)
        box = SpinBox(self)
        box.setRange(low, high)
        box.setValue(fields[key])
        box.valueChanged.connect(lambda value: self.set(key, value))
        self.layout_.addWidget(box)
        box.title = label
        return box

    def combo(self, title, items, index, on_change):
        self.label(title)
        box = ComboBox(self)
        box.addItems(items)
        box.setCurrentIndex(index)
        # qfluentwidgets 的 ComboBox 用代码改选中项时只发 currentTextChanged
        box.currentTextChanged.connect(lambda text: on_change(items.index(text)))
        self.layout_.addWidget(box)
        return box

    def conditions(self, title, rows, facts):
        label = self.label(title)
        conds = ConditionList(rows, facts, self.changed, self)
        self.layout_.addWidget(conds)
        conds.title = label
        return conds

    def set_mode(self, index):
        self.set('mode', 'minutes' if index == 0 else 'until')
        self.show_mode()

    def show_mode(self):
        by_time = self.node.fields['mode'] == 'minutes'
        for w in (self.minutes, self.minutes.title):
            w.setVisible(by_time)
        for w in (self.conds, self.conds.title, self.every, self.every.title, self.most, self.most.title):
            w.setVisible(not by_time)


class RoutineEditor(MessageBoxBase):

    def __init__(self, routine, parent):
        super().__init__(parent)
        self.routine = routine
        self.tasks = {type(t).__name__: t for t in routine.executor.onetime_tasks if type(t).__name__ in ALLOWED}
        self.nodes = []
        self.flat = []
        self.form = None
        self.error = BodyLabel('', self)
        self.error.setWordWrap(True)
        try:
            steps, _ = routine.steps()
            self.nodes = [node_of(s, self.tasks) for s in steps]
        except Exception as e:
            self.error.setText(f'存下来的步骤读不出来，从空的开始：{e}')

        self.list = ListWidget(self)
        self.list.currentRowChanged.connect(self.show_settings)
        self.task_box = ComboBox(self)
        for name, task in self.tasks.items():
            self.task_box.addItem(task.name, userData=name)
        for title, kind in BLOCKS:
            self.task_box.addItem(title, userData=kind)
        add = PushButton(FluentIcon.ADD, '添加', self)
        add.clicked.connect(self.add_step)
        up = PushButton(FluentIcon.UP, '上移', self)
        up.clicked.connect(lambda: self.move(-1))
        down = PushButton(FluentIcon.DOWN, '下移', self)
        down.clicked.connect(lambda: self.move(1))
        into = PushButton(FluentIcon.RIGHT_ARROW, '移进上面的循环', self)
        into.clicked.connect(self.move_in)
        out = PushButton(FluentIcon.LEFT_ARROW, '移出循环', self)
        out.clicked.connect(self.move_out)
        remove = PushButton(FluentIcon.REMOVE, '删除', self)
        remove.clicked.connect(self.remove_step)

        add_row = QHBoxLayout()
        add_row.addWidget(self.task_box, 1)
        add_row.addWidget(add)
        move_row = QHBoxLayout()
        for button in (up, down, remove):
            move_row.addWidget(button)
        nest_row = QHBoxLayout()
        for button in (into, out):
            nest_row.addWidget(button)
        left = QVBoxLayout()
        left.addWidget(SubtitleLabel('步骤', self))
        left.addWidget(self.list, 1)
        left.addWidget(BodyLabel('选中循环时添加，加到循环里面；否则加在选中的这一步后面', self))
        left.addLayout(add_row)
        left.addLayout(move_row)
        left.addLayout(nest_row)

        self.settings_area = QScrollArea(self)
        self.settings_area.setWidgetResizable(True)
        self.settings_area.setMinimumWidth(560)
        reset = PushButton(FluentIcon.CANCEL, '清除这一步的改动', self)
        reset.clicked.connect(self.reset_step)
        right = QVBoxLayout()
        right.addWidget(SubtitleLabel('这一步的设置', self))
        right.addWidget(BodyLabel('任务里动过的项只在这个流程的这一步生效，不改任务自己的设置', self))
        right.addWidget(self.settings_area, 1)
        right.addWidget(reset)

        body = QHBoxLayout()
        body.addLayout(left, 2)
        body.addLayout(right, 3)
        self.viewLayout.addLayout(body)
        self.viewLayout.addWidget(self.error)
        self.yesButton.setText('保存')
        self.cancelButton.setText('取消')
        self.widget.setMinimumSize(1040, 680)

        self.refresh(self.nodes[0] if self.nodes else None)

    def flatten(self, nodes, prefix='', depth=0, owner=None):
        rows = []
        for i, node in enumerate(nodes, 1):
            label = f'{prefix}{i}'
            rows.append((node, nodes, owner, depth, label))
            if node.kind == 'loop':
                rows += self.flatten(node.children, f'{label}.', depth + 1, node)
        return rows

    def label(self, row):
        node, _, _, depth, label = self.flat[row]
        if node.kind == 'task':
            extra = '，'.join(f'{k}={v}' for k, v in node.settings.overrides().items())
            text = node.task.name + (f'（{extra}）' if extra else '')
        else:
            text = describe(node.step())
        return f'{INDENT * depth}{label}. {text}'

    def refresh(self, current=None):
        self.flat = self.flatten(self.nodes)
        self.list.blockSignals(True)
        self.list.clear()
        for row in range(len(self.flat)):
            self.list.addItem(self.label(row))
        self.list.blockSignals(False)
        rows = [r for r, entry in enumerate(self.flat) if entry[0] is current]
        if rows:
            self.list.setCurrentRow(rows[0])
        self.show_settings(self.list.currentRow())

    def selected(self):
        row = self.list.currentRow()
        return self.flat[row] if 0 <= row < len(self.flat) else None

    def show_settings(self, row):
        container = QWidget()
        layout = QVBoxLayout(container)
        self.form = None
        if 0 <= row < len(self.flat):
            node = self.flat[row][0]
            if node.kind == 'task':
                self.task_settings(node, row, layout)
            else:
                self.form = BlockForm(node, lambda: self.relabel(row), container)
                layout.addWidget(self.form)
        layout.addStretch(1)
        self.settings_area.setWidget(container)

    def task_settings(self, node, row, layout):
        task, settings = node.task, node.settings
        for key, value in settings.items():
            type_spec = (task.config_type or {}).get(key)
            if key.startswith('_') or key not in task.default_config or \
                    isinstance(type_spec, dict) and type_spec.get('type') in SKIPPED_TYPES:
                continue
            widget = config_widget(task.config_type, task.config_description, settings, key, value, task)
            if hasattr(widget, 'update_config'):
                widget.update_config = self.tracked(widget.update_config, row)
            layout.addWidget(widget)

    def relabel(self, row):
        # 只改列表里这一行的文字：在控件自己的信号里重建设置区会把正在发信号的控件删掉
        self.list.item(row).setText(self.label(row))

    def tracked(self, update, row):
        def update_and_relabel(value):
            update(value)
            self.relabel(row)
        return update_and_relabel

    def add_step(self):
        kind = self.task_box.currentData()
        if not kind:
            return
        node = TaskNode(self.tasks[kind], StepSettings(self.tasks[kind], {})) if kind in self.tasks else BlockNode(kind)
        at = self.selected()
        if at is None:
            self.nodes.append(node)
        elif at[0].kind == 'loop':
            at[0].children.append(node)
        else:
            siblings = at[1]
            siblings.insert(siblings.index(at[0]) + 1, node)
        self.refresh(node)

    def move(self, delta):
        at = self.selected()
        if at is None:
            return
        node, siblings = at[0], at[1]
        i = siblings.index(node)
        if 0 <= i + delta < len(siblings):
            siblings[i], siblings[i + delta] = siblings[i + delta], siblings[i]
            self.refresh(node)

    def move_in(self):
        at = self.selected()
        if at is None:
            return
        node, siblings = at[0], at[1]
        i = siblings.index(node)
        if i > 0 and siblings[i - 1].kind == 'loop':
            del siblings[i]
            siblings[i - 1].children.append(node)
            self.refresh(node)

    def move_out(self):
        at = self.selected()
        if at is None or at[2] is None:
            return
        node, siblings, owner = at[0], at[1], at[2]
        outer = next(entry[1] for entry in self.flat if entry[0] is owner)
        siblings.remove(node)
        outer.insert(outer.index(owner) + 1, node)
        self.refresh(node)

    def reset_step(self):
        at = self.selected()
        if at is None:
            return
        node = at[0]
        if node.kind == 'task':
            node.settings = StepSettings(node.task, {})
        elif node.kind != 'loop':
            node.fields = new_fields(node.kind)
        self.refresh(node)

    def remove_step(self):
        at = self.selected()
        if at is None:
            return
        row = self.list.currentRow()
        at[1].remove(at[0])
        self.flat = self.flatten(self.nodes)
        nxt = self.flat[min(row, len(self.flat) - 1)][0] if self.flat else None
        self.refresh(nxt)

    def steps_json(self):
        if not self.nodes:
            raise StepError('流程里至少要有一步')
        raw = dump_steps(to_steps(self.nodes))
        parse_steps(raw, {name: spec_of(task) for name, task in self.tasks.items()})
        return json.dumps(raw, ensure_ascii=False, indent=1)

    def validate(self):
        try:
            text = self.steps_json()
        except StepError as e:
            self.error.setText(f'保存不了：{e}')
            return False
        self.routine.config['步骤'] = text
        return True
