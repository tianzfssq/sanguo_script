"""挂机战斗封装：移动遇敌 → 黑条检测战斗 → 结算退出。

逻辑迁移自 auto_battle.py，封装为可复用的 BattleHelper，
供挂机、竞技场、工会 Boss 等模块共用。
"""

from __future__ import annotations

import time

from modules.base import BaseModule, register_action
from orchestrator.context import Context


class BattleHelper:
    """战斗循环工具。依赖 Context 中的窗口/输入/状态检测。"""

    def __init__(self, ctx: Context, battle_cfg: dict | None = None):
        self._ctx = ctx
        cfg = battle_cfg or {}
        self._move_duration = float(cfg.get("move_duration", 1.5))
        self._exit_delay = float(cfg.get("exit_delay", 1.5))
        self._detect_interval = float(cfg.get("detect_interval", 2.0))

    def exit_settle(self) -> None:
        """点击窗口底部中央退出结算画面（沿用 auto_battle.py 的做法）。

        窗口未定位时先尝试自动定位；仍失败则给出明确提示。
        """
        ctx = self._ctx
        rect = ctx.window.get_rect()
        if rect is None:
            ctx.logger.info("窗口未定位，尝试自动定位...")
            if not ctx.window.find_window():
                ctx.logger.warn("窗口定位失败，无法退出结算（请确认小游戏已打开，并点击「重新定位窗口」）")
                return
            rect = ctx.window.get_rect()
        left, top, right, bottom = rect
        cx = (left + right) // 2
        cy = bottom - 20
        ctx.input_ctrl.click(cx, cy)
        ctx.logger.info("点击退出结算画面")
        time.sleep(self._exit_delay)

    def loop_until_settle(self, max_time: float | None = None) -> bool:
        """A/D 移动遇敌 → 检测到结算 → 自动退出。

        max_time 为 None 时无限循环（直到停止信号）。
        返回 True 表示打完一轮并退出结算；False 表示超时或被停止。
        """
        ctx = self._ctx
        start = time.time()
        direction = "a"
        last_detect = 0.0

        while True:
            if ctx.stop_event.is_set():
                ctx.logger.info("战斗循环收到停止信号")
                return False
            if max_time is not None and time.time() - start > max_time:
                ctx.logger.warn("战斗循环超时")
                return False

            ctx.input_ctrl.press_key(direction, self._move_duration, stop_event=ctx.stop_event)
            direction = "d" if direction == "a" else "a"

            now = time.time()
            if now - last_detect >= self._detect_interval:
                state, ratio = ctx.states.detect()
                if state == "settle":
                    ctx.logger.info(f"检测到结算画面 (黑像素 {ratio:.1%})")
                    self.exit_settle()
                    return True
                last_detect = now


    def wait_battle_settle(self, max_time: float = 180.0, min_wait: float = 3.0) -> bool:
        """不移动等待战斗结算（竞技场/工会 Boss 等自动战斗场景使用）。

        - settle 出现：自动退出结算，返回 True
        - 已回到 arena/map：视为战斗结束，返回 True（min_wait 内不判定，
          避免刚点击挑战还没切换界面就误判）
        """
        ctx = self._ctx
        start = time.time()
        while time.time() - start < max_time and not ctx.stop_event.is_set():
            state, _ = ctx.states.detect()
            elapsed = time.time() - start
            if state == "settle":
                self.exit_settle()
                return True
            if state in ("arena", "map") and elapsed > min_wait:
                return True
            time.sleep(0.8)
        ctx.logger.warn("等待战斗结算超时")
        return False

    def wait_battle_end_back(
        self,
        back_scene: str,
        exit_scenes: tuple[str, ...] = ("settle",),
        max_time: float = 180.0,
    ) -> bool:
        """等待战斗结束并回到指定场景，期间自动退出结算界面。

        竞技场/工会 Boss 等自动战斗场景使用：战斗画面不依赖黑条检测，
        以"回到 back_scene 界面"作为战斗结束标志（挑战按钮重新可见）。
        exit_scenes 为结算类场景（如黑条 settle / 竞技场结算 arena_settle），
        命中任一即点击窗口底部退出，然后继续等待回到 back_scene。
        返回 True 表示已回到 back_scene。
        """
        ctx = self._ctx
        start = time.time()
        while time.time() - start < max_time and not ctx.stop_event.is_set():
            state, _ = ctx.states.detect()
            if state == back_scene:
                return True
            if state in exit_scenes:
                self.exit_settle()
            time.sleep(0.8)
        ctx.logger.warn(f"等待战斗结束超时（{max_time}s 内未回到 {back_scene}）")
        return False


@register_action("afk_farm", "开始挂机", "主界面", "A/D 移动遇敌自动打怪循环")
class AfkFarmModule(BaseModule):
    def run(self, ctx: Context) -> None:
        # 挂机依赖窗口坐标（结算退出点击底部），先确保窗口已定位
        if ctx.window.get_rect() is None:
            ctx.logger.info("窗口未定位，尝试自动定位...")
            if not ctx.window.find_window():
                ctx.logger.warn("窗口定位失败，请确认小游戏已打开，并点击「重新定位窗口」后再开始挂机")
                return
            ctx.logger.info("已定位游戏窗口")
        ctx.logger.info("开始挂机：A/D 移动遇敌，点击「停止任务」结束")
        while not ctx.stop_event.is_set():
            ctx.battle.loop_until_settle(max_time=None)
        ctx.logger.info("挂机已停止")
