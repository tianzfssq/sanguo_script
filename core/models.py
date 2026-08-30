"""数据模型：界面元素 Element、场景 Scene、匹配结果 MatchResult。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Element:
    """一个可被模板匹配识别的界面按钮/图标。

    template 为相对 templates/ 目录的文件名；alt_templates 为备选模板
    （同一按钮多种外观，命中任一即算命中）；confidence 为匹配置信度阈值；
    click_offset 为相对匹配中心点的点击偏移 (dx, dy)。
    """

    key: str
    template: str
    alt_templates: tuple = ()
    confidence: float = 0.80
    click_offset: tuple = (0, 0)
    scale_min: float = 1.0
    scale_max: float = 1.0
    enabled: bool = True


@dataclass
class Scene:
    """一类界面（主界面、竞技场、营地二级菜单…），由特征元素组成。

    required 为判定该场景所需全部命中的元素 key 列表（全部命中才判定）；
    未指定 required 时，任一特征元素命中即判定为该场景。
    forbidden 为排除元素 key 列表——命中任一则判定该场景失败
    （用于表达"主界面 = 找到三键 且 没有二级菜单"这类规则）。
    fallback 场景（如主界面）最后判定，避免抢占子场景的识别。
    """

    key: str
    elements: dict[str, Element] = field(default_factory=dict)
    required: list[str] | None = None
    forbidden: list[str] | None = None
    fallback: bool = False


@dataclass
class MatchResult:
    """模板匹配结果，rect 为屏幕绝对坐标 (left, top, right, bottom)。"""

    element: Element
    rect: tuple
    confidence: float

    @property
    def center(self) -> tuple:
        left, top, right, bottom = self.rect
        cx = (left + right) // 2 + self.element.click_offset[0]
        cy = (top + bottom) // 2 + self.element.click_offset[1]
        return (cx, cy)
