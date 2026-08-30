"""任务调度：独立线程运行模块任务，支持优雅停止。"""

from __future__ import annotations

import threading
import time

from pynput import keyboard as pynput_keyboard

from modules.base import get_module
from orchestrator.context import Context
from orchestrator.logger import Logger

# 停止热键 `~`（与 ` 同一物理键），US 布局虚拟键码 192，兼容中文输入法
_STOP_HOTKEY_VK = 192


def _is_stop_hotkey(key) -> bool:
    """判断按键是否为停止热键 `~`（char 或 vk 兜底）。"""
    ch = getattr(key, "char", None)
    if ch in ("`", "~"):
        return True
    return getattr(key, "vk", None) == _STOP_HOTKEY_VK


class TaskRunner:
    def __init__(self, ctx: Context, logger: Logger):
        self._ctx = ctx
        self._logger = logger
        self._thread: threading.Thread | None = None
        self._current: str | None = None
        self._lock = threading.Lock()
        self._hotkey_listener: pynput_keyboard.Listener | None = None

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
            self._start_stop_hotkey()
            self._logger.info(f"任务启动: {mod_cls.name}")
            return True

    def _run(self, mod_cls) -> None:
        try:
            mod_cls().run(self._ctx)
            self._logger.info(f"任务完成: {mod_cls.name}")
        except Exception as exc:
            self._logger.error(f"任务异常终止 [{mod_cls.name}]: {exc}")
        finally:
            self._stop_hotkey_listener()
            with self._lock:
                self._current = None

    # ---------- 停止热键（`~`）----------

    def _start_stop_hotkey(self) -> None:
        """任务运行期间开启全局停止热键监听（按 `~` 触发停止任务）。"""
        if self._hotkey_listener is not None:
            return

        def on_press(key) -> None:
            if _is_stop_hotkey(key):
                self._logger.info("收到停止热键 `~`")
                self.stop_current()

        self._hotkey_listener = pynput_keyboard.Listener(on_press=on_press)
        self._hotkey_listener.start()

    def _stop_hotkey_listener(self) -> None:
        """任务结束后关闭停止热键监听。"""
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

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
