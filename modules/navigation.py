"""导航模块：场景切换（进入/返回主界面）+ 导航按钮 + 测试点击。

Navigator.enter_scene 支持两种模式：
1. 路径模式（[nav.paths] 配置）：按"场景.元素"序列依次点击（如 营地→竞技场）
2. 单步模式：主界面直接点击目标入口元素

返回主界面的策略：非主界面时，战斗中/结算中先退出结算，再按 ESC 逐层返回。
"""

from __future__ import annotations

import time

from modules.base import BaseModule, register_action
from orchestrator.context import Context


class Navigator:
    def __init__(self, ctx: Context, nav_cfg: dict[str, list[str]] | None = None):
        self._ctx = ctx
        self._nav = nav_cfg or {}

    def current_scene(self) -> str:
        return self._ctx.states.detect()[0]

    def back_to_main(self, timeout: float = 20.0) -> bool:
        """从任意场景返回主界面。战斗中/结算中先退出结算；小场景点击退出按钮 2 次；其余按 ESC 逐层返回。"""
        ctx = self._ctx
        deadline = time.time() + timeout
        while time.time() < deadline and not ctx.stop_event.is_set():
            key, _ = ctx.states.detect()
            if key == "main":
                return True
            if key in ("battle", "settle"):
                ctx.logger.info(f"当前处于 {key}，先退出结算")
                ctx.battle.exit_settle()
            elif self._click_exit_twice():
                pass  # 已点击退出按钮 2 次，等循环重新检测
            else:
                ctx.input_ctrl.press_key("esc")
                ctx.logger.info("按 ESC 尝试返回主界面")
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
        """进入目标场景：优先按 [nav.paths] 路径，否则在主界面单步点击入口。"""
        path = self._nav.get(target)
        if path:
            return self._enter_by_path(path, target, timeout)
        return self._enter_single(target, timeout)

    def _click_by_key(self, key: str) -> bool:
        """解析并点击"场景.元素"。"""
        ctx = self._ctx
        scene_key, _, elem_key = key.partition(".")
        scene = ctx.states.get_scene(scene_key)
        element = scene.elements.get(elem_key) if scene else None
        if element is None:
            ctx.logger.error(f"元素未配置: {key}（请在 scenes.toml 补充）")
            return False
        if not ctx.input_ctrl.click_element(element, ctx.matcher, ctx.screen):
            ctx.logger.error(f"未找到元素 {key}（请确认模板 {element.template} 存在且当前界面可见）")
            return False
        return True

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

    def _enter_by_path(self, path: list[str], target: str, timeout: float) -> bool:
        """按路径依次点击元素进入目标场景。

        点击某元素后，应等待"点击后出现的下一场景"再执行下一步：
        - 中间步骤：等待下一个元素的所属场景（如点营地后等 camp_menu 弹出）
        - 最后一步：等待最终目标场景
        """
        ctx = self._ctx
        if not self.back_to_main(timeout):
            ctx.logger.error(f"进入 {target} 失败：无法回到主界面")
            return False
        ctx.logger.info(f"按路径进入 {target}: {' -> '.join(path)}")
        for i, step in enumerate(path):
            if not self._click_by_key(step):
                return False
            expect = path[i + 1].partition(".")[0] if i < len(path) - 1 else target
            if not self._wait_step_scene(expect, timeout):
                ctx.logger.warn(f"点击 {step} 后等待场景 {expect} 超时")
                return False
        ctx.logger.info(f"已进入场景: {target}")
        return True

    def _enter_single(self, target: str, timeout: float) -> bool:
        """单步模式：回到主界面后直接点击目标入口元素。"""
        ctx = self._ctx
        if not self.back_to_main(timeout):
            ctx.logger.error(f"进入 {target} 失败：无法回到主界面")
            return False

        main_scene = ctx.states.get_scene("main")
        if main_scene is None or target not in main_scene.elements:
            ctx.logger.error(f"主界面未配置入口元素: {target}（请在 scenes.toml 补充）")
            return False

        if not self._click_by_key(f"main.{target}"):
            return False
        if not self._wait_step_scene(target, timeout):
            ctx.logger.warn(f"未能确认进入场景: {target}")
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


@register_action("back_main", "回到主界面", "导航", "按 ESC 返回主界面")
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
