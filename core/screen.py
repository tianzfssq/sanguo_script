"""截图工具：基于 pyautogui 的屏幕捕获。"""

from __future__ import annotations

from PIL import Image

import pyautogui


class ScreenCapture:
    def __init__(self, window_mgr):
        self._window = window_mgr

    def full_screen(self) -> Image:
        """全屏截图（坐标体系为屏幕绝对坐标）。"""
        return pyautogui.screenshot()

    def window_screen(self) -> tuple[Image, tuple[int, int]]:
        """截取游戏窗口区域，返回 (截图, 窗口左上偏移)。

        匹配只在游戏窗口内进行，避免屏幕其他内容干扰；
        偏移用于将窗口内坐标转换为屏幕绝对坐标。窗口未定位时回退全屏。
        """
        rect = self._window.get_rect()
        if rect is None:
            return pyautogui.screenshot(), (0, 0)
        left, top, right, bottom = rect
        img = pyautogui.screenshot(region=(left, top, right - left, bottom - top))
        return img, (left, top)

    def clip(self, rect: tuple) -> Image:
        """截取指定区域 (left, top, right, bottom)。"""
        left, top, right, bottom = rect
        return pyautogui.screenshot(region=(left, top, right - left, bottom - top))

    def window_rect(self) -> tuple | None:
        """当前窗口的屏幕坐标，未定位返回 None。"""
        return self._window.get_rect()
