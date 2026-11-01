"""按顺序跑流程的每一步。

每一步直接调子任务的 run()，不走 enable()：enable() 只会把它排进队列，等流程跑完才轮到。
流程自己一直是 executor 的 current_task，停止和暂停都跟着流程走。
"""
from dataclasses import dataclass

from ok.task.exceptions import FinishedException, TaskDisabledException


@dataclass
class StepResult:
    index: int
    title: str
    error: str = ''

    @property
    def ok(self):
        return not self.error

    def line(self):
        return f'第 {self.index} 步 {self.title}：' + ('完成' if self.ok else f'失败，{self.error}')


class StepFailed(Exception):
    def __init__(self, results):
        self.results = results
        failed = next(r for r in reversed(results) if not r.ok)
        super().__init__(failed.line())


def run_steps(routine, steps, tasks, keep_going=False):
    """tasks 是 {类名: 任务}。返回每一步的结果；有一步失败就抛 StepFailed，keep_going 时跑完再抛。"""
    results = []
    for index, step in enumerate(steps, 1):
        child = tasks[step.task]
        result = StepResult(index, child.name)
        routine.log_info(f'第 {index} 步：{child.name}')
        saved_config, saved_info = child.config, child.info
        # 临时设置只放在这份副本里：ok-script 的 Config 一赋值就写盘
        child.config = dict(saved_config)
        child.config.update(step.overrides)
        child.info = routine.info
        try:
            child.run()
        except (TaskDisabledException, FinishedException):
            raise
        except Exception as e:
            result.error = str(e) or type(e).__name__
        finally:
            child.config, child.info = saved_config, saved_info
        results.append(result)
        routine.log_info(result.line())
        # 两个子任务都会自己吞掉 TaskDisabledException 后正常返回，只能回头看流程本身还开着没有
        if not routine.enabled:
            raise TaskDisabledException()
        if not result.ok and not keep_going:
            raise StepFailed(results)
    if not all(r.ok for r in results):
        raise StepFailed(results)
    return results
