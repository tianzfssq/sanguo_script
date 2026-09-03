"""群雄竞技自动化：进入竞技场 → 切群雄逐鹿页签 → 自动匹配挑战。

入口与自动打竞技场（arena.py）完全相同（营地 → 二级菜单 → 竞技场），
主要区别：
1. 进入竞技场后先点击「群雄竞技」页签（arena.qunxiong_tab / j_群雄竞技.png）
   切换到群雄逐鹿玩法，等待 2s；
2. 点「匹配」按键（arena.challenge_qx / t_群雄竞技_匹配.png）→ 弹出"选择对手"
   弹窗（3 个相同"挑战"按键，arena.opponent_challenge / t_群雄竞技_挑战.png），
   用 find_all 取全部命中并点击最靠下的一个（对手积分最低），进入战斗；
3. 之后等待战斗、退结算、回界面等流程与竞技场相同。
"""

from __future__ import annotations

import time

from modules.base import BaseModule, register_action
from orchestrator.context import Context

# 竞技场结算相关场景：黑条结算(野怪) / 竞技场结算界面(模板识别)
SETTLE_SCENES = ("settle", "arena_settle")


def _ensure_qunxiong_tab(ctx: Context) -> bool:
    """确保已切到群雄逐鹿页签：挑战按键可见则直接返回；
    否则点击群雄竞技页签（j_群雄竞技.png）后等 2s，并复检挑战按键是否出现，
    未出现（偶发丢点击）则补点一次。"""
    arena = ctx.states.get_scene("arena")
    challenge = arena.elements.get("challenge_qx") if arena else None
    tab = arena.elements.get("qunxiong_tab") if arena else None
    if challenge is None or tab is None:
        ctx.logger.error("arena 场景未配置 challenge_qx / qunxiong_tab 元素（检查 scenes.toml 与模板）")
        return False

    def _challenge_visible() -> bool:
        shot, _ = ctx.screen.window_screen()
        return ctx.matcher.find(shot, challenge) is not None

    for attempt in range(1, 3):
        if _challenge_visible():
            if attempt > 1:
                ctx.logger.info("补点页签后匹配按键已出现")
            return True
        ctx.logger.info(f"匹配按键不可见，点击群雄竞技页签切换玩法（第 {attempt} 次）")
        if not ctx.input_ctrl.click_element(tab, ctx.matcher, ctx.screen):
            ctx.logger.warn("未匹配到群雄竞技页签（j_群雄竞技.png）")
            return False
        time.sleep(2.0)  # 等待页签内容切换
    ctx.logger.warn("点击页签后匹配按键仍未出现")
    return _challenge_visible()


def _click_match(ctx: Context) -> bool:
    """检测「匹配」按键并点击，返回是否点击成功。"""
    arena = ctx.states.get_scene("arena")
    challenge = arena.elements.get("challenge_qx") if arena else None
    if challenge and ctx.input_ctrl.click_element(challenge, ctx.matcher, ctx.screen):
        # 记录实际点击位置，便于排查偏移
        img, (left, top) = ctx.screen.window_screen()
        r = ctx.matcher.find(img, challenge)
        if r:
            ctx.logger.info(
                f"点击匹配按钮 challenge_qx：窗口内({r.center[0]},{r.center[1]}) 屏幕({r.center[0]+left},{r.center[1]+top})"
            )
        else:
            ctx.logger.info("点击匹配按钮 challenge_qx")
        time.sleep(1.0)  # 等待选择对手弹窗弹出
        return True
    return False


def _select_lowest_opponent(ctx: Context) -> bool:
    """等待"选择对手"弹窗出现，点击位置最靠下的"挑战"（对手积分最低）。

    弹窗内有 3 个相同的挑战按键，用 find_all 取全部命中后选 y 最大者。
    """
    arena = ctx.states.get_scene("arena")
    element = arena.elements.get("opponent_challenge") if arena else None
    if element is None:
        ctx.logger.error("arena 场景未配置 opponent_challenge 元素（检查 scenes.toml 与模板）")
        return False
    deadline = time.time() + 8.0
    while time.time() < deadline and not ctx.stop_event.is_set():
        shot, (left, top) = ctx.screen.window_screen()
        matches = ctx.matcher.find_all(shot, element)
        if matches:
            lowest = matches[-1]  # find_all 按 y 升序，取最靠下的一个
            cx, cy = lowest.center
            ctx.logger.info(
                f"选择对手弹窗命中 {len(matches)} 个挑战，点击最靠下的：窗口内({cx},{cy}) 屏幕({cx+left},{cy+top}) 得分 {lowest.confidence:.3f}"
            )
            ctx.input_ctrl.click(cx + left, cy + top)
            time.sleep(1.0)  # 等待战斗界面加载
            return True
        time.sleep(0.8)
    ctx.logger.warn("未弹出选择对手弹窗（未找到挑战按键）")
    return False


def _enter_qunxiong(ctx: Context) -> bool:
    """进入群雄竞技：入口与竞技场相同（回主界面 → 营地 → 二级菜单 → 竞技场）。"""
    if not ctx.navigator.enter_scene("arena"):
        return False
    ctx.logger.info("已进入竞技场界面")
    return True


@register_action("qunxiong_auto", "自动打群雄竞技", "主界面", "进入群雄竞技并自动挑战，直到次数用尽")
class QunxiongAutoModule(BaseModule):
    def run(self, ctx: Context) -> None:
        # 最多挑战次数（settings.toml [qunxiong].max_rounds，0 = 无限）
        max_rounds = int(ctx.settings.get("qunxiong", {}).get("max_rounds", 5))
        if max_rounds > 0:
            ctx.logger.info(f"自动打群雄竞技启动：最多挑战 {max_rounds} 次")
        else:
            ctx.logger.info("自动打群雄竞技启动：不限次数，直到挑战用尽或手动停止")

        count = 0
        try:
            while not ctx.stop_event.is_set() and (max_rounds <= 0 or count < max_rounds):
                scene, _ = ctx.states.detect()
                if scene in SETTLE_SCENES:
                    ctx.battle.exit_settle()
                    continue
                if scene != "arena":
                    ctx.logger.warn(f"当前不在竞技场界面（{scene}），重新进入")
                    if not _enter_qunxiong(ctx):
                        ctx.logger.error("自动打群雄竞技：进入竞技场失败")
                        return

                # 确保切到群雄逐鹿页签（首次进入后需要点一次页签）
                if not _ensure_qunxiong_tab(ctx):
                    return
                if not _click_match(ctx):
                    ctx.logger.info("未找到匹配按钮，挑战次数已用完，自动打群雄竞技结束")
                    return
                if not _select_lowest_opponent(ctx):
                    ctx.logger.warn("选择对手失败，自动打群雄竞技结束")
                    return

                count += 1
                ctx.logger.info(f"第 {count} 次挑战开始，等待进入战斗...")
                # 以"挑战按钮消失（离开竞技场界面）"作为进入战斗的标志
                if not ctx.states.wait_not("arena", timeout=10.0):
                    ctx.logger.warn("点击挑战后仍停留在竞技场界面，可能挑战未触发，结束")
                    return
                ctx.logger.info("已进入战斗，等待战斗结束...")
                # 等待战斗结束回到竞技场（期间检测到结算界面自动点击底部退出）
                if not ctx.battle.wait_battle_end_back("arena", exit_scenes=SETTLE_SCENES):
                    ctx.logger.warn("等待战斗结束超时，自动打群雄竞技结束")
                    return
                ctx.logger.info(f"第 {count} 次挑战结束，准备下一次挑战")
        finally:
            # 无论完成、手动停止还是中途异常，结束后都退出到主界面
            try:
                ctx.navigator.back_to_main(timeout=15)
            except Exception as e:  # 退出失败不应阻塞收尾
                ctx.logger.warn(f"退出群雄竞技时异常: {e}")

        if max_rounds > 0 and count >= max_rounds:
            ctx.logger.info(f"已达成挑战次数上限（{count}/{max_rounds}），自动打群雄竞技完成")
        else:
            ctx.logger.info(f"自动打群雄竞技已停止（共完成 {count} 次挑战）")
