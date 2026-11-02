"""流程的步骤：按顺序跑哪些任务，每一步临时改哪些设置。

存成 {'version': 1, 'steps': [{'task': 任务类名, 'overrides': {设置名: 值}}]}。
任务按类名认，不按序号认：onetime_tasks 的顺序一变，序号就指到别的任务上了。
"""
from dataclasses import dataclass, field

VERSION = 1
ALLOWED = ('AutoDailyClaimTask', 'AutoNightbookTask')


class StepError(ValueError):
    pass


@dataclass(frozen=True)
class TaskSpec:
    name: str
    title: str
    defaults: dict
    types: dict = field(default_factory=dict)
    routine: bool = False


def spec_of(task):
    return TaskSpec(type(task).__name__, task.name, dict(task.default_config),
                    dict(task.config_type or {}), bool(getattr(task, 'is_routine', False)))


@dataclass(frozen=True)
class Step:
    task: str
    overrides: dict = field(default_factory=dict)


def overrides_from(values, saved):
    """编辑框里一步的设置和任务存下来的设置不一样的那些项，就是这一步的临时设置。"""
    return {key: value for key, value in values.items() if saved.get(key) != value}


def dump_steps(steps):
    return {'version': VERSION,
            'steps': [{'task': s.task, 'overrides': dict(s.overrides)} for s in steps]}


def parse_steps(raw, specs):
    """检查并解析存下来的步骤，specs 是 {类名: TaskSpec}。同一个任务可以出现好几次。"""
    if not isinstance(raw, dict):
        raise StepError('流程格式不对：应该是一个字典')
    if raw.get('version') != VERSION:
        raise StepError(f'流程版本 {raw.get("version")!r} 不认识，只认 {VERSION}')
    items = raw.get('steps')
    if not isinstance(items, list):
        raise StepError('流程格式不对：steps 应该是列表')
    return [_parse_step(i, item, specs) for i, item in enumerate(items, 1)]


def _parse_step(i, item, specs):
    if not isinstance(item, dict) or not isinstance(item.get('task'), str):
        raise StepError(f'第 {i} 步格式不对：要有 task')
    name = item['task']
    spec = specs.get(name)
    if spec is None:
        raise StepError(f'第 {i} 步：没有任务 {name}')
    if spec.routine:
        raise StepError(f'第 {i} 步：流程里不能再套流程（{spec.title}）')
    if name not in ALLOWED:
        raise StepError(f'第 {i} 步：{spec.title} 还不能放进流程')
    overrides = item.get('overrides')
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise StepError(f'第 {i} 步 {spec.title}：overrides 应该是字典')
    return Step(name, {key: _check_value(i, spec, key, value) for key, value in overrides.items()})


def _check_value(i, spec, key, value):
    where = f'第 {i} 步 {spec.title} 的「{key}」'
    if key not in spec.defaults:
        raise StepError(f'{where}：这个任务没有这项设置')
    default = spec.defaults[key]
    # bool 是 int 的子类，要先单独判断
    if isinstance(default, bool):
        ok = isinstance(value, bool)
    elif isinstance(default, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif isinstance(default, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        value = float(value) if ok else value
    else:
        ok = isinstance(value, type(default))
    if not ok:
        raise StepError(f'{where}：应该是 {type(default).__name__}，给的是 {value!r}')
    type_spec = spec.types.get(key) or {}
    options = type_spec.get('options')
    if options is not None and value not in options:
        raise StepError(f'{where}：{value!r} 不在可选项里（{"、".join(map(str, options))}）')
    low, high = type_spec.get('min'), type_spec.get('max')
    if low is not None and value < low or high is not None and value > high:
        raise StepError(f'{where}：{value!r} 超出范围 {low} 到 {high}')
    return value
