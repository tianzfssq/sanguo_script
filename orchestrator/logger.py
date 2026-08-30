"""日志总线：线程安全的日志分发，GUI 订阅后实时显示。"""

from __future__ import annotations

import threading
import time
from typing import Callable

MAX_HISTORY = 200


class Logger:
    def __init__(self):
        self._handlers: list[Callable[[str], None]] = []
        self._history: list[str] = []
        self._lock = threading.Lock()

    def info(self, msg: str) -> None:
        self._emit("INFO", msg)

    def warn(self, msg: str) -> None:
        self._emit("WARN", msg)

    def error(self, msg: str) -> None:
        self._emit("ERROR", msg)

    def subscribe(self, handler: Callable[[str], None]) -> None:
        """订阅日志（handler 可能在 worker 线程被调用，GUI 需自行调度到主线程）。"""
        with self._lock:
            self._handlers.append(handler)

    def history(self) -> list[str]:
        with self._lock:
            return list(self._history)

    def _emit(self, level: str, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}"
        with self._lock:
            self._history.append(line)
            if len(self._history) > MAX_HISTORY:
                self._history.pop(0)
            handlers = list(self._handlers)
        for h in handlers:
            try:
                h(line)
            except Exception:
                pass
