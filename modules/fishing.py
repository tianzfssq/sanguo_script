"""领地钓鱼自动化：进入领地 → 移动到鱼塘 → 循环钓鱼 10 次。

流程：
1. 检测是否已在领地（territory.detect），不在则先自动进入领地
2. 连按 S 键 4 次进入营地，等待 3s
3. 按住 A 4s 松开
4. 按住 W 3s 松开
5. 点击鱼塘（territory.pond / 固定坐标），等待 1s
6. 点击钓鱼（territory.fish），等待 1s
7. 等待 4s 进入钓鱼游戏 → 点击确定（fish_confirm）
   → 等待获得奖励（fish_gain）出现 → 点击屏幕下方退出结算（点 1 次等 1s 再点 1 次）
8. 循环 6~7 共 10 次
"""

from __future__ import annotations

import time

from modules.base import BaseModule, register_action
from orchestrator.context import Context

TERRITORY_SCENE = "territory"
FISHING_SCENE = "fishing"      # 钓鱼小游戏场景（scene.fishing，优先判定）
FISH_TIMES = 10            # 钓鱼循环次数（默认值，可被 settings.toml [fishing].fish_times 覆盖）
MOVE_A_SECONDS = 4.0       # 按下 A 的时长
MOVE_W_SECONDS = 3.0       # 按下 W 的时长
CLICK_SETTLE_DELAY = 1.0   # 点击鱼塘/钓鱼后的等待


def _fish_times(ctx: Context) -> int:
    """钓鱼循环次数（settings.toml [fishing].fish_times）。"""
    return int(ctx.settings.get("fishing", {}).get("fish_times", FISH_TIMES))


def _click_element(
    ctx: Context, elem_key: str, wait: float = 0.0, scene_key: str = FISHING_SCENE
) -> bool:
    """匹配并点击指定场景中的元素，返回是否成功。"""
    scene = ctx.states.get_scene(scene_key)
    element = scene.elements.get(elem_key) if scene else None
    if element is None:
        ctx.logger.error(f"未配置元素: {scene_key}.{elem_key}")
        return False
    if not ctx.input_ctrl.click_element(element, ctx.matcher, ctx.screen):
        ctx.logger.warn(f"未匹配到 {elem_key}，请确认当前界面可见")
        return False
    ctx.logger.info(f"已点击 {elem_key}")
    if wait > 0:
        time.sleep(wait)
    return True


def _wait_element(
    ctx: Context, elem_key: str, timeout: float = 15.0, scene_key: str = FISHING_SCENE
) -> bool:
    """等待指定场景中的元素出现，返回是否出现。"""
    scene = ctx.states.get_scene(scene_key)
    element = scene.elements.get(elem_key) if scene else None
    if element is None:
        ctx.logger.error(f"未配置元素: {scene_key}.{elem_key}")
        return False
    start = time.time()
    while time.time() - start < timeout and not ctx.stop_event.is_set():
        shot, _ = ctx.screen.window_screen()
        if ctx.matcher.find(shot, element):
            return True
        time.sleep(0.5)
    ctx.logger.warn(f"等待 {elem_key} 超时（{timeout}s）")
    return False


def _click_pond(ctx: Context) -> bool:
    """按固定位置点击鱼塘（settings.toml [fishing].pond_pos，窗口内相对坐标）。"""
    pos = ctx.settings.get("fishing", {}).get("pond_pos", [200, 345])
    x, y = int(pos[0]), int(pos[1])
    if not ctx.input_ctrl.click_in_window(x, y, ctx.window):
        ctx.logger.warn("窗口未定位，无法点击鱼塘")
        return False
    ctx.logger.info(f"点击鱼塘（窗口内 {x},{y}）")
    time.sleep(CLICK_SETTLE_DELAY)
    return True


def _move_into_camp(ctx: Context) -> None:
    """连按 S 键 4 次进入营地（每次间隔 300ms），完成后等待 3s 加载。"""
    for i in range(1, 5):
        if ctx.stop_event.is_set():
            break
        ctx.input_ctrl.press_key("s")
        ctx.logger.info(f"按 S 键 {i}/4")
        time.sleep(0.3)
    time.sleep(3.0)  # 等待进入营地加载


def _is_scene(ctx: Context, scene_key: str) -> bool:
    """静默检测指定场景特征（scene.<key>.elements.detect）当前是否出现。"""
    scene = ctx.states.get_scene(scene_key)
    element = scene.elements.get("detect") if scene else None
    if element is None:
        return False
    shot, _ = ctx.screen.window_screen()
    return ctx.matcher.find(shot, element) is not None


def _fish_round(ctx: Context) -> bool:
    """第 7 步：点击钓鱼后等待 4s（进入钓鱼游戏）→ 点击确定 → 等待获得奖励 → 点击屏幕下方关闭弹窗。

    退出结算（简单方法）：点击屏幕下方 1 次，等 1s，再点击 1 次，
    关闭可能连续弹出的 2 次结算弹窗，随后再点钓鱼。
    """
    time.sleep(3.0)  # 点击钓鱼按键后已等待 1s，再等 3s，共 4s 进入钓鱼游戏
    if not _click_element(ctx, "fish_confirm"):
        return False
    if not _wait_element(ctx, "fish_gain", timeout=15):
        ctx.logger.warn("未检测到获得奖励，本轮钓鱼异常")
        return False
    # 退出结算：点击屏幕下方 1 次，等 1s，再点击 1 次（应对连续 2 次结算弹窗）
    ctx.logger.info("点击屏幕下方退出结算")
    ctx.battle.exit_settle()
    time.sleep(1.0)
    ctx.logger.info("再次点击屏幕下方（关闭可能的第 2 次结算弹窗）")
    ctx.battle.exit_settle()
    return True


def _run_fishing(ctx: Context) -> None:
    """完整钓鱼流程。"""
    # 1. 检测是否在领地界面，不在则先进入领地
    if _is_scene(ctx, TERRITORY_SCENE):
        ctx.logger.info("已在领地界面")
    else:
        ctx.logger.info("不在领地界面，先进入领地...")
        if not ctx.navigator.enter_scene(TERRITORY_SCENE):
            ctx.logger.error("进入领地失败，钓鱼中止")
            return
    # 2. 连按 S 键 4 次进入营地，等待 3s
    _move_into_camp(ctx)
    # 3. 按住 A 4s
    ctx.logger.info("按住 A 4 秒...")
    ctx.input_ctrl.press_key("a", MOVE_A_SECONDS)
    # 4. 按住 W 3s
    ctx.logger.info("按住 W 3 秒...")
    ctx.input_ctrl.press_key("w", MOVE_W_SECONDS)
    # 5. 点击鱼塘（固定位置），等待 1s
    if not _click_pond(ctx):
        return
    # 6~8. 钓鱼循环 fish_times 次
    times = _fish_times(ctx)
    ctx.logger.info(f"开始钓鱼循环（{times} 次）")
    for i in range(1, times + 1):
        if ctx.stop_event.is_set():
            break
        ctx.logger.info(f"第 {i} 次钓鱼...")
        if not _click_element(ctx, "fish", wait=CLICK_SETTLE_DELAY):
            break
        if not _fish_round(ctx):
            break
    ctx.logger.info("钓鱼结束")


@register_action("fish_auto", "钓鱼（领地）", "领地", "进入营地后移动到鱼塘自动钓鱼 10 次")
class FishingModule(BaseModule):
    def run(self, ctx: Context) -> None:
        _run_fishing(ctx)


@register_action("fish_loop", "钓鱼循环10次", "领地", "在钓鱼界面自动循环钓鱼 10 次")
class FishingLoopModule(BaseModule):
    def run(self, ctx: Context) -> None:
        times = _fish_times(ctx)
        ctx.logger.info(f"开始钓鱼循环（{times} 次）")
        for i in range(1, times + 1):
            if ctx.stop_event.is_set():
                break
            ctx.logger.info(f"第 {i} 次钓鱼...")
            if not _click_element(ctx, "fish", wait=CLICK_SETTLE_DELAY):
                break
            if not _fish_round(ctx):
                break
        ctx.logger.info("钓鱼循环结束")
