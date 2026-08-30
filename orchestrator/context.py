"""共享上下文：所有模块/动作通过 Context 访问基础设施。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from core.image_match import ImageMatcher
from core.input import InputController
from core.screen import ScreenCapture
from core.state import StateDetector
from core.window import WindowManager
from orchestrator.logger import Logger


@dataclass
class Context:
    window: WindowManager
    screen: ScreenCapture
    matcher: ImageMatcher
    input_ctrl: InputController
    states: StateDetector
    logger: Logger
    settings: dict
    stop_event: threading.Event
    data: dict = field(default_factory=dict)  # 模块间共享的临时数据（如计数）
    # 由 main.py 在构造后注入（依赖 ctx 本身，需先有 Context 实例）
    navigator: object = None
    battle: object = None
