"""输入控制：鼠标点击与键盘模拟。

注意：键盘模拟必须使用 pynput（同时提供 VK 码 + 扫描码），
否则 Chromium WebView 无法推导出正确的 event.code，游戏不响应。
参考 docs/keyboard-simulation-lessons.md
"""

from __future__ import annotations

import time

import pyautogui
from pynput.keyboard import Controller, Key

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# pynput 字符串只接受单字符，特殊键需映射到 Key 枚举（直接传 "esc" 会抛 ValueError）
_SPECIAL_KEYS = {"esc": Key.esc}


class InputController:
    def __init__(self):
        self._keyboard = Controller()

    def click(self, x: int, y: int, hold: float = 0.08) -> None:
        """在屏幕绝对坐标处左键点击。

        按下后按住 hold 秒再松开：立即按下松开（pyautogui.click）会被
        Chromium WebView 小游戏忽略，点击不生效。
        """
        pyautogui.moveTo(x, y)
        pyautogui.mouseDown(x, y)
        time.sleep(hold)
        pyautogui.mouseUp(x, y)

    def click_element(self, element, matcher, screen) -> bool:
        """在游戏窗口内匹配元素并点击其中心（含偏移），未命中返回 False。"""
        img, (left, top) = screen.window_screen()
        result = matcher.find(img, element)
        if result is None:
            return False
        x, y = result.center
        # 窗口内坐标 → 屏幕绝对坐标
        self.click(x + left, y + top)
        return True

    def click_in_window(self, x: int, y: int, window_mgr) -> bool:
        """按游戏窗口内相对坐标点击（左上角为 0,0），窗口未定位返回 False。"""
        rect = window_mgr.get_rect()
        if rect is None:
            return False
        left, top, _, _ = rect
        self.click(left + x, top + y)
        return True

    def press_key(self, key: str, duration: float = 0.0, stop_event=None) -> None:
        """短按或长按按键。duration > 0 时为长按。

        短按时按住 50ms 再松开：立即按下松开（pynput tap）会被
        Chromium WebView 忽略，游戏不响应（参考 keyboard-simulation-lessons.md）。

        全局规则：停止任务时必须先松开已按下的按键。
        - 长按期间按 0.1s 分片睡眠并检查 stop_event，收到停止信号立即松开，
          避免停止后角色仍持续移动（挂机 A/D、钓鱼 A/W）；
        - release 放在 finally 中，中途异常也不会残留按下状态。
        """
        key = _SPECIAL_KEYS.get(key, key)
        self._keyboard.press(key)
        try:
            if duration > 0:
                remaining = duration
                while remaining > 0:
                    if stop_event is not None and stop_event.is_set():
                        break
                    step = min(0.1, remaining)
                    time.sleep(step)
                    remaining -= step
            else:
                time.sleep(0.05)
        finally:
            self._keyboard.release(key)

    def move_and_click(self, x: int, y: int, duration: float = 0.3) -> None:
        """模拟人手移动后点击（减少被检测风险），点击同样带按住逻辑。"""
        pyautogui.moveTo(x, y, duration=duration)
        self.click(x, y)
