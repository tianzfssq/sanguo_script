"""导航模块：场景切换（进入/返回主界面）+ 导航按钮 + 测试点击。

Navigator.enter_scene 支持两种模式：
1. 路径模式（[nav.paths] 配置）：按"场景.元素"序列依次点击（如 营地→竞技场）
2. 单步模式：直接点击目标入口元素

每一步都是"轮询等待元素出现并点击"（如点营地后二级菜单弹出前匹配不到
会自动重试），不依赖中间场景判定；最后一步点击后等待目标场景确认。
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from modules.base import BaseModule, register_action
from orchestrator.context import Context


class Navigator:
    def __init__(self, ctx: Context, nav_cfg: dict[str, list[str]] | None = None):
        self._ctx = ctx
        self._nav = nav_cfg or {}

    def current_scene(self) -> str:
        return self._ctx.states.detect()[0]

    def back_to_main(self, timeout: float = 20.0) -> bool:
        """从任意场景返回主界面（仅收尾用）。战斗中/结算中先退出结算；其余点击退出按钮 2 次。

        游戏内按 ESC 无法返回主界面，不做 ESC 兜底；退出按钮也匹配不到时
        静默等待重试直至超时（避免误判时刷日志）。
        """
        ctx = self._ctx
        deadline = time.time() + timeout
        while time.time() < deadline and not ctx.stop_event.is_set():
            key, _ = ctx.states.detect()
            if key == "main":
                return True
            if key in ("battle", "settle"):
                ctx.logger.info(f"当前处于 {key}，先退出结算")
                ctx.battle.exit_settle()
            else:
                self._click_exit_twice()
            time.sleep(1.0)
        ctx.logger.warn("返回主界面超时")
        return False

    def _click_exit_twice(self) -> bool:
        """点击小场景通用退出按钮 2 次（间隔 2s），未匹配到返回 False 由调用方 ESC 兜底。

        退出按钮是各小场景通用的（竞技场/工会/钓鱼共用），直接复用竞技场场景的 exit_main 元素。
        """
        ctx = self._ctx
        arena = ctx.states.get_scene("arena")
        el = arena.elements.get("exit_main") if arena else None
        if el is None or not ctx.input_ctrl.click_element(el, ctx.matcher, ctx.screen):
            return False
        ctx.logger.info("已点击退出按钮，2s 后再点击一次")
        time.sleep(2.0)
        if ctx.input_ctrl.click_element(el, ctx.matcher, ctx.screen):
            ctx.logger.info("已再次点击退出按钮")
        return True

    # ---------- 进入场景 ----------

    def enter_scene(self, target: str, timeout: float = 20.0) -> bool:
        """进入目标场景：不在主界面时先点退出按钮返回，再按路径/单步进入。"""
        ctx = self._ctx
        current, _ = ctx.states.detect()
        if current != "main":
            ctx.logger.info(f"当前场景 {current} 不是主界面，先返回主界面")
            if not self.back_to_main(timeout=timeout):
                ctx.logger.error(f"无法返回主界面，放弃进入 {target}")
                return False
        path = self._nav.get(target)
        if path:
            return self._enter_by_path(path, target, timeout)
        return self._enter_single(target, timeout)

    def _click_step_with_retry(self, key: str, timeout: float, interval: float = 0.5) -> bool:
        """轮询尝试点击路径中的元素（等待其出现），成功返回 True。

        元素未出现（如点营地后二级菜单还在弹出）时匹配不到，自动重试，
        避免依赖中间场景判定（场景判定慢且易受主界面 fallback 干扰）。
        等待期间每 2s 用 0 阈值探测一次并打印当前最高匹配得分，便于定位
        模板失效（得分很低）还是阈值过高（得分接近阈值）。
        """
        ctx = self._ctx
        scene_key, _, elem_key = key.partition(".")
        scene = ctx.states.get_scene(scene_key)
        element = scene.elements.get(elem_key) if scene else None
        if element is None:
            ctx.logger.error(f"元素未配置: {key}（请在 scenes.toml 补充）")
            return False
        rect = ctx.window.get_rect()
        ctx.logger.info(
            f"等待点击 {key}（模板 {element.template}），匹配范围为窗口区域 {rect}（屏幕绝对坐标）..."
        )
        probe = replace(element, confidence=0.0)  # 0 阈值探测用
        deadline = time.time() + timeout
        next_probe = time.time()  # 首轮立即探测一次
        best = 0.0
        while time.time() < deadline and not ctx.stop_event.is_set():
            if ctx.input_ctrl.click_element(element, ctx.matcher, ctx.screen):
                ctx.logger.info(f"已点击 {key}")
                return True
            if time.time() >= next_probe:
                shot, (wl, wt) = ctx.screen.window_screen()
                r = ctx.matcher.find(shot, probe)
                score = r.confidence if r else 0.0
                best = max(best, score)
                if r:
                    cx, cy = r.center
                    pos = f" 窗口内({cx},{cy}) 屏幕({cx + wl},{cy + wt})"
                else:
                    pos = ""
                ctx.logger.info(
                    f"仍在等待 {key}：最高得分 {score:.3f}{pos}（阈值 {element.confidence}）"
                )
                next_probe = time.time() + 2.0
            time.sleep(interval)
        ctx.logger.error(
            f"等待点击 {key} 超时：等待期间最高得分 {best:.3f}，阈值 {element.confidence}。"
            "得分接近阈值可在 scenes.toml 调低 confidence；得分很低说明模板与界面不符，需重截模板"
        )
        return False

    def _wait_step_scene(self, step_scene: str, timeout: float) -> bool:
        """等待某场景出现；该场景无可用模板时按固定延迟兜底。"""
        ctx = self._ctx
        scene = ctx.states.get_scene(step_scene)
        has_templates = bool(
            scene
            and scene.elements
            and any(ctx.matcher.has_template(el) for el in scene.elements.values())
        )
        if has_templates:
            return ctx.states.wait_for(step_scene, timeout=timeout)
        time.sleep(1.5)
        return True

    def _dump_scene_detail(self) -> None:
        """打印场景判定明细（各场景元素得分）并保存现场截图，用于失败定位。"""
        ctx = self._ctx
        try:
            img, _ = ctx.screen.window_screen()
            name = f"debug_进入失败_{time.strftime('%H%M%S')}.png"
            img.save(Path(__file__).resolve().parent.parent / name)
            ctx.logger.info(f"  已保存现场截图: {name}")
        except Exception as exc:
            ctx.logger.warn(f"  现场截图保存失败: {exc}")
        try:
            _, _, lines = ctx.states.detect_detail()
            for line in lines:
                ctx.logger.info("  " + line)
        except Exception as exc:
            ctx.logger.warn(f"场景明细输出失败: {exc}")

    def _enter_by_path(self, path: list[str], target: str, timeout: float) -> bool:
        """按路径依次点击元素进入目标场景。

        每一步轮询等待元素出现并点击（如点营地后等二级菜单弹出再点竞技场），
        不依赖中间场景判定；最后一步点击后等待目标场景确认。
        """
        ctx = self._ctx
        ctx.logger.info(f"按路径进入 {target}: {' -> '.join(path)}")
        for step in path:
            if not self._click_step_with_retry(step, timeout):
                return False
        if not ctx.states.wait_for(target, timeout=timeout):
            ctx.logger.warn(f"已点击全部路径元素，但未确认进入场景 {target}，场景判定明细:")
            self._dump_scene_detail()
            return False
        ctx.logger.info(f"已进入场景: {target}")
        return True

    def _enter_single(self, target: str, timeout: float) -> bool:
        """单步模式：直接点击目标入口元素（不先回主界面）。"""
        ctx = self._ctx

        main_scene = ctx.states.get_scene("main")
        if main_scene is None or target not in main_scene.elements:
            ctx.logger.error(f"主界面未配置入口元素: {target}（请在 scenes.toml 补充）")
            return False

        if not self._click_step_with_retry(f"main.{target}", timeout):
            return False
        # 点击后场景切换有过渡动画，立即判定会误命中（如主界面上领地检测
        # 模板可得 0.839，接近阈值），先固定等待再确认场景
        time.sleep(3.0)
        if not self._wait_step_scene(target, timeout):
            ctx.logger.warn(f"未能确认进入场景: {target}，场景判定明细:")
            self._dump_scene_detail()
            return False
        ctx.logger.info(f"已进入场景: {target}")
        return True


# ========== 导航按钮 ==========

class _EnterSceneModule(BaseModule):
    """通用"进入某场景"模块，子类只需设置 target 与场景名称。"""

    target: str = ""
    scene_name: str = ""

    def run(self, ctx: Context) -> None:
        ok = ctx.navigator.enter_scene(self.target)
        ctx.logger.info(f"进入{self.scene_name}: {'成功' if ok else '失败'}")


@register_action("territory_enter", "进入领地", "导航", "进入领地地图")
class TerritoryEnterModule(_EnterSceneModule):
    target = "territory"
    scene_name = "领地"


@register_action("arena_enter", "进入竞技场", "导航", "营地→二级菜单→竞技场")
class ArenaEnterModule(_EnterSceneModule):
    target = "arena"
    scene_name = "竞技场"


@register_action("guild_enter", "进入工会", "导航", "进入工会界面")
class GuildEnterModule(_EnterSceneModule):
    target = "guild"
    scene_name = "工会"


@register_action("back_main", "回到主界面", "导航", "点击退出按钮返回主界面")
class BackToMainModule(BaseModule):
    def run(self, ctx: Context) -> None:
        ok = ctx.navigator.back_to_main()
        ctx.logger.info(f"回到主界面: {'成功' if ok else '失败'}")


# ========== 测试点击按键（验证模板匹配与点击） ==========

class _TestClickModule(BaseModule):
    """点击指定元素并报告匹配结果，用于分步验证截图与配置。"""

    element_key: str = ""

    def run(self, ctx: Context) -> None:
        scene_key, _, elem_key = self.element_key.partition(".")
        scene = ctx.states.get_scene(scene_key)
        element = scene.elements.get(elem_key) if scene else None
        if element is None:
            ctx.logger.error(f"元素未配置: {self.element_key}（检查 scenes.toml）")
            return
        ok = ctx.input_ctrl.click_element(element, ctx.matcher, ctx.screen)
        ctx.logger.info(f"点击 {self.element_key}: {'成功' if ok else '未找到，请确认当前界面可见'}")


@register_action("test_click_camp", "点击营地(测试)", "测试", "匹配并点击主界面营地入口")
class TestClickCamp(_TestClickModule):
    element_key = "main.camp"


@register_action("test_click_arena", "点击竞技场(测试)", "测试", "匹配并点击营地二级菜单的竞技场按钮")
class TestClickArena(_TestClickModule):
    element_key = "camp_menu.arena_entry"
