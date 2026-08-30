"""窗口管理：定位并激活游戏窗口。"""

from __future__ import annotations

import time

import win32con
import win32gui

DEFAULT_CHILD_CLASS = "Intermediate D3D Window"


class WindowManager:
    """定位微信小游戏的 D3D 子窗口，提供坐标与聚焦能力。"""

    _instance = None

    def __init__(self, child_class: str = DEFAULT_CHILD_CLASS):
        self._child_class = child_class
        self._parent_hwnd = None
        self._child_hwnd = None
        self._rect = None

    @classmethod
    def instance(cls, child_class: str | None = None) -> "WindowManager":
        if cls._instance is None:
            cls._instance = cls(child_class or DEFAULT_CHILD_CLASS)
        elif child_class:
            cls._instance._child_class = child_class
        return cls._instance

    # ---------- 窗口定位 ----------

    def _collect_candidates(self) -> list:
        candidates = []

        def check_children(parent_hwnd, _):
            if not win32gui.IsWindowVisible(parent_hwnd):
                return True

            def find_child(chwnd, __):
                if win32gui.GetClassName(chwnd) != self._child_class:
                    return True
                rect = win32gui.GetWindowRect(chwnd)
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                if w < 200 or h < 200 or w > 3000 or h > 3000:
                    return True
                if rect[0] > 30000 or rect[1] > 30000:
                    return True
                pcls = win32gui.GetClassName(parent_hwnd)
                ptitle = win32gui.GetWindowText(parent_hwnd)
                candidates.append((parent_hwnd, chwnd, rect, pcls, ptitle))
                return True

            win32gui.EnumChildWindows(parent_hwnd, find_child, None)
            return True

        win32gui.EnumWindows(check_children, None)
        return candidates

    def find_window(self) -> bool:
        """定位游戏窗口，成功返回 True。"""
        try:
            candidates = self._collect_candidates()
        except Exception:
            candidates = []
        if not candidates:
            self._parent_hwnd = self._child_hwnd = None
            self._rect = None
            return False

        chrome = [
            (p, c, r, t) for p, c, r, pcls, t in candidates if pcls == "Chrome_WidgetWin_0"
        ]
        if chrome:
            chrome.sort(key=lambda x: (x[2][2] - x[2][0]) * (x[2][3] - x[2][1]))
            self._parent_hwnd, self._child_hwnd, self._rect, _ = chrome[0]
        else:
            self._parent_hwnd, self._child_hwnd, self._rect, _, _ = candidates[0]
        return True

    def wait_until_found(self, timeout: float = 10.0) -> bool:
        """轮询定位窗口，直到成功或超时。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.find_window():
                return True
            time.sleep(1.0)
        return False

    # ---------- 窗口操作 ----------

    def focus(self) -> bool:
        """激活并前置窗口，失败返回 False。"""
        if self._parent_hwnd is None:
            return False
        if win32gui.IsIconic(self._parent_hwnd):
            win32gui.ShowWindow(self._parent_hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
        win32gui.SetForegroundWindow(self._parent_hwnd)
        time.sleep(0.2)
        return True

    def get_rect(self) -> tuple | None:
        """返回窗口屏幕坐标 (left, top, right, bottom)，未定位返回 None。"""
        return self._rect
