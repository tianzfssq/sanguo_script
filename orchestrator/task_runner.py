"""任务调度：独立线程运行模块任务，支持优雅停止。"""

from __future__ import annotations

import threading
import time

from modules.base import get_module
from orchestrator.context import Context
from orchestrator.logger import Logger


class TaskRunner:
    def __init__(self, ctx: Context, logger: Logger):
        self._ctx = ctx
        self._logger = logger
        self._thread: threading.Thread | None = None
        self._current: str | None = None
        self._lock = threading.Lock()

    def start(self, module_key: str) -> bool:
        """启动指定模块任务（独立线程）。已有任务运行时拒绝。"""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._logger.warn("已有任务运行中，无法启动新任务")
                return False
            mod_cls = get_module(module_key)
            if mod_cls is None:
                self._logger.error(f"模块不存在: {module_key}")
                return False
            # 任务启动前：重新定位窗口（获取最新位置）并将游戏窗口调到前台，
            # 避免 GUI 或其他窗口遮挡导致点击/截图作用在错误窗口上
            self._ctx.window.find_window()
            if not self._ctx.window.focus():
                self._logger.warn("未能将游戏窗口调到前台，请确认小游戏已打开（也可手动点击游戏窗口）")
            time.sleep(0.5)
            self._ctx.stop_event.clear()
            self._current = module_key
            self._thread = threading.Thread(
                target=self._run, args=(mod_cls,), daemon=True, name=f"task-{module_key}"
            )
            self._thread.start()
            self._logger.info(f"任务启动: {mod_cls.name}")
            return True

    def _run(self, mod_cls) -> None:
        try:
            mod_cls().run(self._ctx)
            self._logger.info(f"任务完成: {mod_cls.name}")
        except Exception as exc:
            self._logger.error(f"任务异常终止 [{mod_cls.name}]: {exc}")
        finally:
            with self._lock:
                self._current = None

    def stop_current(self) -> None:
        """向当前任务发送停止信号（优雅停止，由模块内循环响应）。"""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._logger.info("当前无运行中的任务")
                return
            self._ctx.stop_event.set()
            self._logger.info("已发送停止信号")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def current_task(self) -> str | None:
        with self._lock:
            return self._current
