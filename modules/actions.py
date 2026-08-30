"""Action 原语：模块流程的可组合原子操作，公共逻辑复用。

每个 Action 必须响应 ctx.stop_event（通过 should_stop 检查），
保证停止信号可以穿透嵌套流程。
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod

from orchestrator.context import Context


class Action(ABC):
    @abstractmethod
    def execute(self, ctx: Context) -> bool:
        """执行动作，返回是否成功（False 表示失败或已停止）。"""
        raise NotImplementedError

    def should_stop(self, ctx: Context) -> bool:
        return ctx.stop_event.is_set()


class WaitAction(Action):
    """固定时长等待（期间响应停止信号，可被中断）。"""

    def __init__(self, seconds: float):
        self._seconds = seconds

    def execute(self, ctx: Context) -> bool:
        deadline = time.time() + self._seconds
        while time.time() < deadline and not self.should_stop(ctx):
            time.sleep(0.05)
        return not self.should_stop(ctx)


class RandomDelayAction(Action):
    """拟人化随机延迟，降低被检测风险。"""

    def __init__(self, min_s: float, max_s: float):
        self._min, self._max = min_s, max_s

    def execute(self, ctx: Context) -> bool:
        return WaitAction(random.uniform(self._min, self._max)).execute(ctx)


class WaitSceneAction(Action):
    """等待进入指定场景。"""

    def __init__(self, scene: str, timeout: float = 10.0):
        self._scene = scene
        self._timeout = timeout

    def execute(self, ctx: Context) -> bool:
        while not self.should_stop(ctx):
            if ctx.states.detect()[0] == self._scene:
                return True
            time.sleep(0.2)
        return False
