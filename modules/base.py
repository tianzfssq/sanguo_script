"""模块基类与注册机制。

新增功能的扩展方式：
1. 新建模块文件，实现 BaseModule.run()；
2. 用 @register_action(...) 注册；
3. 在 modules/__init__.py 中 import 该文件（触发注册）；
4. GUI 会自动按 category 生成按钮，无需改动其他代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from orchestrator.context import Context

_MODULES: dict[str, type["BaseModule"]] = {}


def register_action(key: str, name: str, category: str, description: str = ""):
    """装饰器：注册模块到全局注册表。"""

    def deco(cls):
        cls.action_key = key
        cls.name = name
        cls.category = category
        cls.description = description
        _MODULES[key] = cls
        return cls

    return deco


def get_all_modules() -> list[type["BaseModule"]]:
    return list(_MODULES.values())


def get_module(key: str) -> type["BaseModule"] | None:
    return _MODULES.get(key)


class BaseModule(ABC):
    """所有自动化模块的基类。

    子类必须实现 run(ctx)：
    - 通过 ctx.stop_event.is_set() 响应停止信号；
    - 通过 ctx.logger 输出日志；
    - 复用 ctx 中的核心层能力。
    """

    action_key: str = ""
    name: str = ""
    category: str = ""
    description: str = ""

    @abstractmethod
    def run(self, ctx: Context) -> None:
        raise NotImplementedError
