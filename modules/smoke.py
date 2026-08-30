"""测试模块：验证「注册 → 按钮 → 任务线程 → 日志 → 停止」完整链路。"""

from __future__ import annotations

import time

from .actions import WaitAction
from .base import BaseModule, register_action


@register_action("test_hello", "测试日志模块", "测试", "验证按钮/任务/停止链路")
class HelloTestModule(BaseModule):
    def run(self, ctx) -> None:
        ctx.logger.info("测试模块开始运行")
        for i in range(6):
            if ctx.stop_event.is_set():
                ctx.logger.info("测试模块收到停止信号，提前结束")
                return
            time.sleep(0.5)
            ctx.logger.info(f"测试步骤 {i + 1}/6")
        ctx.logger.info("测试模块执行完毕")

    def run_with_action(self, ctx) -> None:
        """演示 Action 原语用法（作为参考）。"""
        if WaitAction(1.0).execute(ctx):
            ctx.logger.info("等待结束")
