"""竞技场自动化：自动点击挑战按钮进行挑战。

流程：
1. 进入竞技场（等待界面就绪）
2. 循环：找挑战按钮（challenge1 / challenge2）→ 点击 → 等待战斗
3. 结算自动退出 → 回到竞技场 → 下一次挑战
4. 找不到挑战按钮（次数用完）或停止时结束
"""

from __future__ import annotations

import time

from modules.base import BaseModule, register_action
from orchestrator.context import Context

CHALLENGE_KEYS = ("challenge1", "challenge2")
# 竞技场结算相关场景：黑条结算(野怪) / 竞技场结算界面(模板识别)
SETTLE_SCENES = ("settle", "arena_settle")


def _click_challenge(ctx: Context) -> bool:
    """依次尝试点击挑战按钮，返回是否点击成功。"""
    arena = ctx.states.get_scene("arena")
    for key in CHALLENGE_KEYS:
        element = arena.elements.get(key) if arena else None
        if element and ctx.input_ctrl.click_element(element, ctx.matcher, ctx.screen):
            # 记录实际点击位置，便于排查偏移
            img, (left, top) = ctx.screen.window_screen()
            r = ctx.matcher.find(img, element)
            if r:
                ctx.logger.info(
                    f"点击挑战按钮 {key}：窗口内({r.center[0]},{r.center[1]}) 屏幕({r.center[0]+left},{r.center[1]+top})"
                )
            else:
                ctx.logger.info(f"点击挑战按钮 {key}")
            time.sleep(1.0)  # 等待战斗界面加载
            return True
    return False


def _exit_arena_to_main(ctx: Context) -> None:
    """自动打竞技场结束后：返回主界面（back_to_main 会点击退出按钮 2 次，找不到则 ESC 兜底）。"""
    try:
        ctx.navigator.back_to_main(timeout=15)
    except Exception as e:  # 退出失败不应阻塞收尾
        ctx.logger.warn(f"退出竞技场时异常: {e}")


@register_action("arena_auto", "自动打竞技场", "主界面", "自动挑战竞技场对手，直到次数用尽")
class ArenaAutoModule(BaseModule):
    def run(self, ctx: Context) -> None:
        # 最多挑战次数（settings.toml [arena].max_rounds，0 = 无限）
        max_rounds = int(ctx.settings.get("arena", {}).get("max_rounds", 5))
        if max_rounds > 0:
            ctx.logger.info(f"自动打竞技场启动：最多挑战 {max_rounds} 次")
        else:
            ctx.logger.info("自动打竞技场启动：不限次数，直到挑战用尽或手动停止")

        if not ctx.navigator.enter_scene("arena"):
            ctx.logger.error("自动打竞技场：进入竞技场失败")
            return

        count = 0
        try:
            while not ctx.stop_event.is_set() and (max_rounds <= 0 or count < max_rounds):
                scene, _ = ctx.states.detect()
                if scene in SETTLE_SCENES:
                    ctx.battle.exit_settle()
                    continue
                if scene != "arena":
                    ctx.logger.warn(f"当前不在竞技场界面（{scene}），重新进入")
                    if not ctx.navigator.enter_scene("arena"):
                        return

                if not _click_challenge(ctx):
                    ctx.logger.info("未找到挑战按钮，挑战次数已用完，自动打竞技场结束")
                    return

                count += 1
                ctx.logger.info(f"第 {count} 次挑战开始，等待进入战斗...")
                # 竞技场战斗不依赖黑条检测：以"挑战按钮消失（离开竞技场界面）"作为进入战斗的标志
                if not ctx.states.wait_not("arena", timeout=10.0):
                    ctx.logger.warn("点击挑战后仍停留在竞技场界面，可能挑战未触发，结束")
                    return
                ctx.logger.info("已进入战斗，等待战斗结束...")
                # 等待战斗结束回到竞技场（期间检测到结算界面自动点击底部退出，支持第二轮挑战）
                if not ctx.battle.wait_battle_end_back("arena", exit_scenes=SETTLE_SCENES):
                    ctx.logger.warn("等待战斗结束超时，自动打竞技场结束")
                    return
                ctx.logger.info(f"第 {count} 次挑战结束，准备下一次挑战")
        finally:
            # 无论完成、手动停止还是中途异常，结束后都退出到主界面
            _exit_arena_to_main(ctx)

        if max_rounds > 0 and count >= max_rounds:
            ctx.logger.info(f"已达成挑战次数上限（{count}/{max_rounds}），自动打竞技场完成")
        else:
            ctx.logger.info(f"自动打竞技场已停止（共完成 {count} 次挑战）")
