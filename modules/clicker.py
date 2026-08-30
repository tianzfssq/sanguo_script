"""连点模块：定位 eat 图标后高频左键连点，按 ` 键退出连点模式。"""

from __future__ import annotations

import threading
import time

import pyautogui
from pynput import keyboard as pynput_keyboard
from pynput.mouse import Button, Controller as MouseController

from .base import BaseModule, register_action

CLICK_HOLD = 0.05  # 每次按住时长（秒）
CLICK_GAP = 0.05  # 松开后间隔（秒）


def _is_backtick(key) -> bool:
    """判断按键是否为 ` 键（char 或 vk=192 兜底）。"""
    if getattr(key, "char", None) == "`":
        return True
    return getattr(key, "vk", None) == 192


@register_action("eat_clicker", "连点（eat图标）", "主界面", "定位 eat.png 后左键连点，按 ` 键退出")
class EatClickerModule(BaseModule):
    def run(self, ctx) -> None:
        scene = ctx.states.get_scene("main")
        element = scene.elements.get("eat") if scene else None
        if element is None:
            ctx.logger.error("未配置 main.eat 元素，无法连点")
            return

        # 定位 eat 图标（连点目标位置固定，找一次即可）
        img, (left, top) = ctx.screen.window_screen()
        result = ctx.matcher.find(img, element)
        if result is None:
            ctx.logger.warn("未匹配到 eat 图标，请确认当前界面可见")
            return
        x = result.center[0] + left
        y = result.center[1] + top
        ctx.logger.info(f"已定位 eat 图标 ({x},{y})，开始连点，按 ` 键退出")

        exit_event = threading.Event()

        def on_press(key) -> None:
            if _is_backtick(key):
                exit_event.set()

        listener = pynput_keyboard.Listener(on_press=on_press)
        listener.start()

        ctx.window.focus()
        pyautogui.moveTo(x, y)
        mouse = MouseController()
        pressed = False
        count = 0
        try:
            while not exit_event.is_set() and not ctx.stop_event.is_set():
                mouse.press(Button.left)
                pressed = True
                time.sleep(CLICK_HOLD)
                mouse.release(Button.left)
                pressed = False
                count += 1
                time.sleep(CLICK_GAP)
        finally:
            # 退出时若仍处于按下状态，补发松开
            if pressed:
                mouse.release(Button.left)
                pressed = False
            listener.stop()
        ctx.logger.info(f"连点结束，共点击 {count} 次")
