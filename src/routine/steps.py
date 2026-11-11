"""流程的步骤：按顺序跑哪些任务、检查、等待和循环，每一步临时改哪些设置。

存成 {'version': 2, 'steps': [...]}，每一项是下面一种：
  {'task': 任务类名, 'overrides': {设置名: 值}}
  {'check': '委托密函'}                         看一眼委托密函，记下有没有无尽委托、还有没有密函
  {'wait': {'minutes': 分钟}}                   回大世界等一段时间
  {'wait': {'until': 条件, 'every': 分钟, 'most': 分钟}}
                                                每隔 every 分钟（0 为每次整点轮换后）看一次委托密函，
                                                条件满足就往下走，最多等 most 分钟
  {'loop': {'times': 次, 'hours': 小时, 'until_time': 'HH:MM', 'until': 条件}, 'steps': [...]}
                                                重复里面的步骤，任一个结束条件满足就停
  {'if': 条件, 'then': '结束循环' | '下一轮' | '结束流程'}

条件是 [[名字, 值], ...]，任一项成立就算成立。名字和值见 FACTS，由步骤跑完时写进流程的上下文。
版本 1 只有 task 一种，照样能读。
任务按类名认，不按序号认：onetime_tasks 的顺序一变，序号就指到别的任务上了。
"""
import re
from dataclasses import dataclass, field

VERSION = 2
ALLOWED = ('AutoDailyClaimTask', 'AutoNightbookTask')

RESULT = '上一步结果'
ENDLESS = '有无尽委托'
LETTERS_LEFT = '密函还有'
FACTS = {
    RESULT: ('跑了', '跳过', '失败'),
    ENDLESS: ('是', '否'),
    LETTERS_LEFT: ('是', '否'),
}
# 这几项要看了委托密函才知道
LETTER_FACTS = (ENDLESS, LETTERS_LEFT)
# 会去看委托密函的任务
LETTER_READERS = ('AutoNightbookTask',)
CHECKS = ('委托密函',)
BREAK, NEXT_ROUND, END = '结束循环', '下一轮', '结束流程'
ACTIONS = (BREAK, NEXT_ROUND, END)
MAX_LOOP_DEPTH = 2


class StepError(ValueError):
    pass


@dataclass(frozen=True)
class TaskSpec:
    name: str
    title: str
    defaults: dict
    types: dict = field(default_factory=dict)


def spec_of(task):
    return TaskSpec(type(task).__name__, task.name, dict(task.default_config), dict(task.config_type or {}))


@dataclass(frozen=True)
class Step:
    task: str
    overrides: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    what: str = CHECKS[0]


@dataclass(frozen=True)
class Wait:
    minutes: int = 0
    until: tuple = ()
    every: int = 0
    most: int = 0


@dataclass(frozen=True)
class Loop:
    steps: tuple
    times: int = 0
    hours: int = 0
    until_time: str = ''
    until: tuple = ()


@dataclass(frozen=True)
class If:
    when: tuple
    then: str


def dump_steps(steps):
    return {'version': VERSION, 'steps': [_dump(s) for s in steps]}


def _dump(s):
    if isinstance(s, Step):
        return {'task': s.task, 'overrides': dict(s.overrides)}
    if isinstance(s, Check):
        return {'check': s.what}
    if isinstance(s, Wait):
        if not s.until:
            return {'wait': {'minutes': s.minutes}}
        return {'wait': {'until': _dump_cond(s.until), 'every': s.every, 'most': s.most}}
    if isinstance(s, Loop):
        ends = {'times': s.times, 'hours': s.hours, 'until_time': s.until_time, 'until': _dump_cond(s.until)}
        return {'loop': {k: v for k, v in ends.items() if v}, 'steps': [_dump(c) for c in s.steps]}
    return {'if': _dump_cond(s.when), 'then': s.then}


def _dump_cond(cond):
    return [[name, value] for name, value in cond]


def parse_steps(raw, specs):
    """检查并解析存下来的步骤，specs 是 {类名: TaskSpec}。同一个任务可以出现好几次。"""
    if not isinstance(raw, dict):
        raise StepError('流程格式不对：应该是一个字典')
    if raw.get('version') not in (1, VERSION):
        raise StepError(f'流程版本 {raw.get("version")!r} 不认识，只认 1 和 {VERSION}')
    items = raw.get('steps')
    if not isinstance(items, list):
        raise StepError('流程格式不对：steps 应该是列表')
    steps = _parse_list(items, specs, '', 0)
    _check_letter_facts(steps)
    return steps


def _parse_list(items, specs, prefix, depth):
    return [_parse_item(f'{prefix}{i}', item, specs, depth) for i, item in enumerate(items, 1)]


def _parse_item(label, item, specs, depth):
    where = f'第 {label} 步'
    if not isinstance(item, dict):
        raise StepError(f'{where}格式不对：应该是字典，要有 task、check、wait、loop 或 if')
    if 'task' in item:
        return _parse_step(where, item, specs)
    if 'check' in item:
        if item['check'] not in CHECKS:
            raise StepError(f'{where}：检查 {item["check"]!r} 认不出，只能检查{"、".join(CHECKS)}')
        return Check(item['check'])
    if 'wait' in item:
        return _parse_wait(where, item['wait'])
    if 'loop' in item:
        return _parse_loop(label, where, item, specs, depth)
    if 'if' in item:
        then = item.get('then')
        if then not in ACTIONS:
            raise StepError(f'{where}：「如果」之后做什么 {then!r} 认不出，只能是{"、".join(ACTIONS)}')
        if then != END and depth == 0:
            raise StepError(f'{where}：{then}只能放在循环里')
        return If(_parse_cond(where, item['if']), then)
    raise StepError(f'{where}：认不出这一步，要有 task、check、wait、loop 或 if')


def _parse_step(where, item, specs):
    name = item['task']
    if not isinstance(name, str):
        raise StepError(f'{where}格式不对：要有 task')
    spec = specs.get(name)
    if spec is None:
        raise StepError(f'{where}：没有任务 {name}')
    if name not in ALLOWED:
        raise StepError(f'{where}：{spec.title} 还不能放进流程')
    overrides = item.get('overrides')
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise StepError(f'{where} {spec.title}：overrides 应该是字典')
    return Step(name, {key: _check_value(where, spec, key, value) for key, value in overrides.items()})


def _parse_wait(where, raw):
    if not isinstance(raw, dict):
        raise StepError(f'{where}：等待的设置应该是字典')
    minutes = _count(where, raw, 'minutes', '等几分钟')
    until = raw.get('until')
    if bool(minutes) == bool(until):
        raise StepError(f'{where}：等待要么给等多久（分钟），要么给等到什么条件，只能选一个')
    if minutes:
        return Wait(minutes=minutes)
    cond = _parse_cond(where, until)
    others = [name for name, _ in cond if name not in LETTER_FACTS]
    if others:
        raise StepError(f'{where}：等待只能等委托密函里看得到的（{"、".join(LETTER_FACTS)}），'
                        f'不能等{"、".join(others)}')
    most = _count(where, raw, 'most', '最多等几分钟')
    if not most:
        raise StepError(f'{where}：等条件时要给最多等几分钟')
    return Wait(until=cond, every=_count(where, raw, 'every', '隔几分钟看一次'), most=most)


def _parse_loop(label, where, item, specs, depth):
    raw = item['loop']
    if not isinstance(raw, dict):
        raise StepError(f'{where}：循环的设置应该是字典')
    if depth >= MAX_LOOP_DEPTH:
        raise StepError(f'{where}：循环最多套两层')
    until_time = raw.get('until_time') or ''
    if until_time and not (isinstance(until_time, str) and re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', until_time)):
        raise StepError(f'{where}：结束时间 {until_time!r} 应该是 HH:MM，比如 06:00')
    times, hours = _count(where, raw, 'times', '次数'), _count(where, raw, 'hours', '小时')
    if not (times or hours or until_time):
        raise StepError(f'{where}：循环要给次数、小时或结束时间，免得一直跑下去')
    until = _parse_cond(where, raw['until']) if raw.get('until') else ()
    items = item.get('steps')
    if not isinstance(items, list) or not items:
        raise StepError(f'{where}：循环里面没有步骤')
    steps = tuple(_parse_list(items, specs, f'{label}.', depth + 1))
    return Loop(steps, times=times, hours=hours, until_time=until_time, until=until)


def _count(where, raw, key, title):
    value = raw.get(key, 0) or 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StepError(f'{where}：{title}应该是不小于 0 的整数，给的是 {value!r}')
    return value


def _parse_cond(where, raw):
    if not isinstance(raw, list) or not raw:
        raise StepError(f'{where}：条件应该是至少一项的列表')
    cond = []
    for pair in raw:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise StepError(f'{where}：条件 {pair!r} 应该是 [名字, 值]')
        name, value = pair
        if name not in FACTS:
            raise StepError(f'{where}：条件 {name!r} 认不出，只有{"、".join(FACTS)}')
        if value not in FACTS[name]:
            raise StepError(f'{where}：条件「{name}」的值 {value!r} 不对，只能是{"、".join(FACTS[name])}')
        cond.append((name, value))
    return tuple(cond)


def walk(steps):
    for s in steps:
        yield s
        if isinstance(s, Loop):
            yield from walk(s.steps)


def _check_letter_facts(steps):
    reads = any(isinstance(s, (Check, Wait)) and (isinstance(s, Check) or s.until) or
                isinstance(s, Step) and s.task in LETTER_READERS for s in walk(steps))
    if reads:
        return
    for s in walk(steps):
        cond = s.when if isinstance(s, If) else s.until if isinstance(s, Loop) else ()
        for name, _ in cond:
            if name in LETTER_FACTS:
                raise StepError(f'条件「{name}」要看了委托密函才知道，流程里没有步骤会读委托密函：'
                                f'加一个检查委托密函，或者自动夜航手册')


def _check_value(where, spec, key, value):
    where = f'{where} {spec.title} 的「{key}」'
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
