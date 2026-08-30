"""工会自动化：自动打工会 Boss。

流程（参考已调通的自动打竞技场）：
1. 进入工会界面（等待界面就绪）
2. 点击工会 Boss 按键（guild.boss / guild_boss.png）打开挑战面板（仅第一次）
3. 循环 rounds 次（默认 2 次）：
   - 检测挑战按键（guild.challenge1 / challenge_1.png）并点击进入 Boss 战斗；
     未检测到时点击屏幕下方关闭可能的弹窗后重试，最多连续检测 3 次
   - 等待进入战斗（离开工会界面）
   - 等待战斗结束（结算自动点击底部退出）→ 回到挑战面板
4. 全部结束后点击退出按钮返回主界面（需点击 2 次，间隔 2s；找不到则 ESC 兜底）

注意：Boss 战斗结束点击下方退出后，会停留在「挑战面板」（挑战按键可见），
因此第 2 次及以后无需再点 Boss 按键，直接点挑战按键即可。
"""

from __future__ import annotations

import time

from modules.base import BaseModule, register_action
from orchestrator.context import Context

DEFAULT_ROUNDS = 2
# 战斗结算相关场景：黑条结算(野怪) / 竞技场结算界面(模板识别)
SETTLE_SCENES = ("settle", "arena_settle")


def _click_guild_element(ctx: Context, key: str, wait: float = 1.0) -> bool:
    """匹配并点击工会场景中的元素，返回是否成功。"""
    guild = ctx.states.get_scene("guild")
    element = guild.elements.get(key) if guild else None
    if element is None:
        ctx.logger.error(f"工会场景未配置元素: {key}（请在 scenes.toml 补充）")
        return False
    if not ctx.input_ctrl.click_element(element, ctx.matcher, ctx.screen):
        ctx.logger.warn(f"未匹配到工会元素 {key}，请确认当前界面可见")
        return False
    ctx.logger.info(f"已点击工会元素 {key}")
    if wait > 0:
        time.sleep(wait)
    return True


def _guild_element_visible(ctx: Context, key: str) -> bool:
    """检测工会场景中指定元素当前是否可见（只检测不点击）。"""
    guild = ctx.states.get_scene("guild")
    element = guild.elements.get(key) if guild else None
    if element is None:
        return False
    shot, _ = ctx.screen.window_screen()
    return ctx.matcher.find(shot, element) is not None


def _click_challenge(ctx: Context) -> bool:
    """检测挑战按键并点击；未检测到则点击屏幕下方后重试，最多连续检测 3 次。

    Boss 战斗结束点击下方退出后，可能仍有弹窗遮挡挑战按键，
    需再点击下方关闭后挑战按键才可见，因此做多次"检测→点击下方"重试。
    """
    for attempt in range(1, 4):
        if _guild_element_visible(ctx, "challenge1"):
            ctx.logger.info(f"第 {attempt} 次检测到挑战按键，点击挑战")
            return _click_guild_element(ctx, "challenge1", wait=1.0)
        ctx.logger.info(f"第 {attempt} 次未检测到挑战按键，点击屏幕下方")
        ctx.battle.exit_settle()
    # 3 次检测均未命中，最后再确认一次
    if _guild_element_visible(ctx, "challenge1"):
        ctx.logger.info("检测到挑战按键，点击挑战")
        return _click_guild_element(ctx, "challenge1", wait=1.0)
    ctx.logger.warn("连续检测未找到挑战按键，无法挑战")
    return False


def _boss_round(ctx: Context, index: int, need_open: bool) -> bool:
    """单次 Boss 战斗：(可选)点 Boss 按键打开面板 → 点挑战 → 等待战斗结束回到挑战面板。"""
    ctx.logger.info(f"第 {index} 次 Boss 战斗开始")
    if need_open:
        # 点击工会 Boss 按键打开挑战面板（仅第一次需要）
        if not _click_guild_element(ctx, "boss"):
            return False
    # 检测挑战按键并点击（未出现则点击下方重试）
    if not _click_challenge(ctx):
        return False
    ctx.logger.info(f"第 {index} 次挑战已点击，等待进入战斗...")
    # 以"挑战按键消失（离开工会界面）"作为进入战斗的标志
    if not ctx.states.wait_not("guild", timeout=10.0):
        ctx.logger.warn("点击挑战后仍停留在工会界面，可能挑战未触发")
        return False
    ctx.logger.info("已进入 Boss 战斗，等待战斗结束...")
    # 等待战斗结束回到工会界面（期间检测到结算界面自动点击底部退出）
    if not ctx.battle.wait_battle_end_back("guild", exit_scenes=SETTLE_SCENES):
        ctx.logger.warn("等待 Boss 战斗结束超时")
        return False
    ctx.logger.info(f"第 {index} 次 Boss 战斗结束")
    return True


def _exit_guild_to_main(ctx: Context) -> None:
    """自动打工会 Boss 结束后：返回主界面（back_to_main 会点击退出按钮 2 次，找不到则 ESC 兜底）。"""
    try:
        ctx.navigator.back_to_main(timeout=15)
    except Exception as e:  # 退出失败不应阻塞收尾
        ctx.logger.warn(f"退出工会时异常: {e}")


@register_action("guild_boss_auto", "自动打工会boss", "工会", "自动点击工会 Boss 并挑战，共 2 次")
class GuildBossModule(BaseModule):
    def run(self, ctx: Context) -> None:
        rounds = int(ctx.settings.get("guild", {}).get("rounds", DEFAULT_ROUNDS))
        ctx.logger.info(f"自动打工会 Boss 启动：共挑战 {rounds} 次")

        if not ctx.navigator.enter_scene("guild"):
            ctx.logger.error("自动打工会 Boss：进入工会失败")
            return

        count = 0
        need_open = True  # 第一次需先点 Boss 按键打开挑战面板
        try:
            for i in range(1, rounds + 1):
                if ctx.stop_event.is_set():
                    ctx.logger.info("收到停止信号，自动打工会 Boss 结束")
                    break
                scene, _ = ctx.states.detect()
                if scene in SETTLE_SCENES:
                    ctx.battle.exit_settle()
                    continue
                if scene != "guild":
                    ctx.logger.warn(f"当前不在工会界面（{scene}），重新进入")
                    if not ctx.navigator.enter_scene("guild"):
                        return
                    need_open = True  # 重新进入后回到工会主界面，需重新打开面板
                if not _boss_round(ctx, i, need_open):
                    ctx.logger.warn(f"第 {i} 次 Boss 战斗失败，自动打工会 Boss 结束")
                    return
                count = i
                # 战斗结束后停留在挑战面板，后续无需再点 Boss 按键
                need_open = False
        finally:
            # 无论完成、手动停止还是中途异常，结束后都退出到主界面（对齐自动打竞技场）
            _exit_guild_to_main(ctx)

        if count >= rounds:
            ctx.logger.info(f"已完成全部 {count} 次 Boss 挑战，自动打工会 Boss 完成")
        else:
            ctx.logger.info(f"自动打工会 Boss 已停止（共完成 {count} 次挑战）")
