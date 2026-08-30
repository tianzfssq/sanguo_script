"""三国自动挂机助手 — 入口。

启动流程：
1. 加载配置（settings / scenes）
2. 构建核心层基础设施
3. import modules 触发模块注册
4. 构建 Context / TaskRunner / GUI 面板
"""

from __future__ import annotations

import threading
from pathlib import Path

import modules  # noqa: F401  触发 @register_action 注册
from core.config import ConfigLoader
from core.image_match import ImageMatcher
from core.input import InputController
from core.screen import ScreenCapture
from core.state import StateDetector
from core.window import WindowManager
from orchestrator.context import Context
from orchestrator.logger import Logger
from orchestrator.task_runner import TaskRunner
from ui.panel import Panel

ROOT_DIR = Path(__file__).parent


def build_context() -> Context:
    loader = ConfigLoader(ROOT_DIR)
    settings = loader.load_settings()
    scenes = loader.load_scenes()

    logger = Logger()
    logger.info("三国自动挂机助手启动")
    logger.info(f"已加载 {len(scenes)} 个场景定义")

    window = WindowManager.instance(settings.get("window", {}).get("child_class"))
    if window.find_window():
        rect = window.get_rect()
        logger.info(f"已定位游戏窗口: {rect[2]-rect[0]}x{rect[3]-rect[1]}")
    else:
        logger.warn("启动时未找到游戏窗口，可在界面点击「重新定位窗口」")
    screen = ScreenCapture(window)
    matcher = ImageMatcher(
        loader.templates_dir,
        scale_step=float(settings.get("template", {}).get("scale_step", 0.05)),
    )
    input_ctrl = InputController()
    states = StateDetector(scenes, matcher, screen, settings.get("detect", {}))

    stop_event = threading.Event()
    ctx = Context(
        window=window,
        screen=screen,
        matcher=matcher,
        input_ctrl=input_ctrl,
        states=states,
        logger=logger,
        settings=settings,
        stop_event=stop_event,
    )
    # 注入依赖 ctx 的组件（Navigator / BattleHelper）
    from modules.battle import BattleHelper
    from modules.navigation import Navigator

    ctx.battle = BattleHelper(ctx, settings.get("battle", {}))
    ctx.navigator = Navigator(ctx, nav_cfg=loader.load_nav())
    return ctx


def main() -> None:
    ctx = build_context()
    runner = TaskRunner(ctx, ctx.logger)
    panel = Panel(ctx, runner, ctx.logger)
    panel.run()


if __name__ == "__main__":
    main()
