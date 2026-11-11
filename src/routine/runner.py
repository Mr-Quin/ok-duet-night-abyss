"""按顺序跑流程的每一步，循环、等待和「如果」也在这里。

每一步直接调子任务的 run()，不走 enable()：enable() 只会把它排进队列，等流程跑完才轮到。
流程自己一直是 executor 的 current_task，停止和暂停都跟着流程走。

步骤跑完把结果写进上下文（steps.FACTS），循环的结束条件和「如果」读它。
子任务跑的时候能拿到 routine_facts 这个字典，往里写它看到的东西，比如委托密函还有没有。
"""
import datetime
import time
from dataclasses import dataclass

from ok.task.exceptions import FinishedException, TaskDisabledException

from src.evidence import checkpoint
from src.routine.steps import BREAK, END, ENDLESS, LETTERS_LEFT, NEXT_ROUND, RESULT, Check, If, Loop, Step, Wait

RAN, SKIPPED, FAILED = '跑了', '跳过', '失败'
# 委托密函整点轮换，多等一分钟免得赶在换好之前
ROTATION = 3600
ROTATION_GRACE = 60
# 长时间等待切成小段睡，停止按钮才能及时生效
SLEEP_SLICE = 60


@dataclass
class StepResult:
    index: str
    title: str
    error: str = ''
    outcome: str = RAN

    @property
    def ok(self):
        return not self.error

    def line(self):
        if not self.ok:
            return f'第 {self.index} 步 {self.title}：失败，{self.error}'
        return f'第 {self.index} 步 {self.title}：' + ('跳过' if self.outcome == SKIPPED else '完成')


class StepFailed(Exception):
    def __init__(self, results):
        self.results = results
        failed = next(r for r in reversed(results) if not r.ok)
        super().__init__(failed.line())


class _Break(Exception):
    pass


class _NextRound(Exception):
    pass


class _End(Exception):
    pass


def run_steps(routine, steps, tasks, keep_going=False, game=None, clock=time.time):
    """tasks 是 {类名: 任务}，game 管回大世界和看委托密函（见 game.py）。

    返回每一步的结果；有一步失败就抛 StepFailed，keep_going 时跑完再抛。
    """
    run = _Run(routine, tasks, keep_going, game, clock)
    try:
        run.block(steps, '', None)
    except _End:
        pass
    if not all(r.ok for r in run.results):
        raise StepFailed(run.results)
    return run.results


class _Run:
    def __init__(self, routine, tasks, keep_going, game, clock):
        self.routine, self.tasks, self.keep_going, self.game, self.clock = routine, tasks, keep_going, game, clock
        self.facts = {}
        self.results = []

    def block(self, steps, prefix, deadline):
        for n, step in enumerate(steps, 1):
            label = f'{prefix}{n}'
            if isinstance(step, Step):
                self.task(step, label)
            elif isinstance(step, Check):
                self.attempt(label, '检查委托密函', self.check)
            elif isinstance(step, Wait):
                self.attempt(label, '等待', lambda: self.wait(step, deadline))
            elif isinstance(step, Loop):
                self.loop(step, label, deadline)
            elif isinstance(step, If):
                self.decide(step, label)

    def task(self, step, label):
        child = self.tasks[step.task]
        saved_config, saved_info = child.config, child.info
        # 临时设置只放在这份副本里：ok-script 的 Config 一赋值就写盘
        child.config = dict(saved_config)
        child.config.update(step.overrides)
        child.info = self.routine.info
        child.evidence = getattr(self.routine, 'evidence', None)
        child.routine_facts = {}

        def run():
            child.run()
            return child.routine_facts.pop(RESULT, RAN)
        try:
            self.attempt(label, child.name, run, child)
        finally:
            child.config, child.info = saved_config, saved_info
            child.evidence = None
            child.routine_facts = None

    def attempt(self, label, title, fn, child=None):
        result = StepResult(label, title)
        checkpoint(self.routine, f'step{label}-start', f'第 {label} 步开始：{title}')
        try:
            result.outcome = fn() or RAN
        except (TaskDisabledException, FinishedException):
            raise
        except Exception as e:
            result.error = str(e) or type(e).__name__
            result.outcome = FAILED
        if child is not None:
            child.routine_facts.pop(RESULT, None)
            self.facts.update(child.routine_facts)
        self.facts[RESULT] = result.outcome
        self.results.append(result)
        checkpoint(self.routine, f'step{label}-' + ('done' if result.ok else 'failed'), result.line())
        if not result.ok and not self.keep_going:
            raise StepFailed(self.results)

    def check(self):
        self.facts.update(self.game.letters())
        self.routine.log_info(f'委托密函：{ENDLESS} {self.facts[ENDLESS]}，{LETTERS_LEFT} {self.facts[LETTERS_LEFT]}')

    def wait(self, step, deadline):
        limit = deadline or float('inf')
        if not step.until:
            self.sleep_until(min(self.clock() + step.minutes * 60, limit))
            return RAN
        end = min(self.clock() + step.most * 60, limit)
        while True:
            self.check()
            if self.met(step.until):
                return RAN
            now = self.clock()
            later = now + step.every * 60 if step.every else now - now % ROTATION + ROTATION + ROTATION_GRACE
            if later > end:
                self.routine.log_info('等到上限了，条件还没满足')
                return SKIPPED
            self.routine.log_info(f'条件还没满足，{clock_text(later)} 再看')
            self.sleep_until(later)

    def sleep_until(self, when):
        if when <= self.clock():
            return
        self.game.world()
        while (left := when - self.clock()) > 0:
            self.routine.sleep(min(SLEEP_SLICE, left))

    def loop(self, step, label, deadline):
        start = self.clock()
        ends = [t for t in (deadline, step.hours and start + step.hours * 3600, end_time(start, step.until_time)) if t]
        end = min(ends) if ends else None
        rounds = 0
        while True:
            if step.times and rounds >= step.times:
                why = f'跑满 {step.times} 次'
            elif end is not None and self.clock() >= end:
                why = '到时间了'
            elif step.until and self.met(step.until):
                why = '结束条件满足了'
            else:
                rounds += 1
                checkpoint(self.routine, f'step{label}-round{rounds}', f'第 {label} 步循环第 {rounds} 次')
                try:
                    self.block(step.steps, f'{label}.', end)
                except _NextRound:
                    pass
                except _Break:
                    why = '「如果」结束了循环'
                    break
                continue
            break
        checkpoint(self.routine, f'step{label}-end', f'第 {label} 步循环结束：{why}，跑了 {rounds} 次')

    def decide(self, step, label):
        if not self.met(step.when):
            return
        checkpoint(self.routine, f'step{label}-if', f'第 {label} 步：条件满足，{step.then}')
        raise {BREAK: _Break, NEXT_ROUND: _NextRound, END: _End}[step.then]()

    def met(self, cond):
        return any(self.facts.get(name) == value for name, value in cond)


def clock_text(when):
    return datetime.datetime.fromtimestamp(when).strftime('%H:%M')


def end_time(start, hhmm):
    """start 之后第一个 HH:MM；今天已经过了就是明天。"""
    if not hhmm:
        return None
    hour, minute = map(int, hhmm.split(':'))
    begin = datetime.datetime.fromtimestamp(start)
    at = begin.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if at <= begin:
        at += datetime.timedelta(days=1)
    return at.timestamp()
