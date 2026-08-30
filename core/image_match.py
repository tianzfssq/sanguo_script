"""图像模板匹配：基于 OpenCV 的多尺度模板匹配封装。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .models import Element, MatchResult


class ImageMatcher:
    """对截图执行多尺度模板匹配，返回屏幕绝对坐标下的最佳匹配。"""

    def __init__(self, templates_dir: Path, scale_step: float = 0.05):
        self._templates_dir = Path(templates_dir)
        self._scale_step = scale_step
        self._cache: dict[str, np.ndarray | None] = {}

    @property
    def templates_dir(self) -> Path:
        """模板目录路径。"""
        return self._templates_dir

    def _load(self, name: str) -> np.ndarray | None:
        """按文件名加载模板灰度图；缺失或读取失败返回 None。"""
        if name in self._cache:
            return self._cache[name]
        path = self._templates_dir / name
        tpl = None
        if path.exists():
            try:
                # np.fromfile + imdecode 兼容中文路径
                data = np.fromfile(str(path), dtype=np.uint8)
                tpl = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
            except Exception:
                tpl = None
        self._cache[name] = tpl
        return tpl

    def _element_template_names(self, element: Element) -> list[str]:
        """元素的全部模板文件名（主模板 + 备选模板）。"""
        return [element.template, *element.alt_templates]

    def has_template(self, element: Element) -> bool:
        """任一模板文件存在且可加载即为 True。"""
        return any(self._load(n) is not None for n in self._element_template_names(element))

    def find(self, screen: Image, element: Element) -> MatchResult | None:
        """在截图中查找元素，命中返回 MatchResult，否则返回 None。

        元素可配置多个模板（同一按钮多种外观），命中任一即算命中，取置信度最高者。
        """
        if not element.enabled:
            return None
        img = np.array(screen.convert("L"))

        best: tuple[float, tuple] | None = None
        for name in self._element_template_names(element):
            tpl = self._load(name)
            if tpl is None:
                continue
            scale = element.scale_min
            while scale <= element.scale_max + 1e-6:
                ts = cv2.resize(tpl, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                if ts.shape[0] <= img.shape[0] and ts.shape[1] <= img.shape[1]:
                    res = cv2.matchTemplate(img, ts, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= element.confidence and (best is None or max_val > best[0]):
                        h, w = ts.shape
                        rect = (max_loc[0], max_loc[1], max_loc[0] + w, max_loc[1] + h)
                        best = (max_val, rect)
                scale += self._scale_step

        if best is None:
            return None
        return MatchResult(element, best[1], best[0])

    def find_any(self, screen: Image, elements: list[Element]) -> MatchResult | None:
        """在多个元素中找置信度最高的匹配。"""
        best: MatchResult | None = None
        for el in elements:
            r = self.find(screen, el)
            if r and (best is None or r.confidence > best.confidence):
                best = r
        return best
