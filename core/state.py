"""场景状态检测：优先模板匹配识别业务场景，回退底部黑条检测。"""

from __future__ import annotations

import time

import pyautogui
from PIL import Image
from dataclasses import replace

from .image_match import ImageMatcher
from .models import Scene


class StateDetector:
    """识别当前游戏处于哪个场景。

    场景判定顺序：
    1. 对每个已配置的 Scene 做元素匹配，命中即判定为该场景（含战斗界面）；
    2. 全部未命中时回退到黑条检测（settle / map）。
    """

    def __init__(
        self,
        scenes: dict[str, Scene],
        matcher: ImageMatcher,
        screen,
        detect_cfg: dict | None = None,
    ):
        self._scenes = scenes
        self._matcher = matcher
        self._screen = screen
        cfg = detect_cfg or {}
        self._sample_bottom_ratio = float(cfg.get("sample_bottom_ratio", 0.15))
        self._black_threshold = int(cfg.get("black_threshold", 40))
        self._settle_ratio = float(cfg.get("settle_ratio", 0.88))
        self._downsize_ratio = float(cfg.get("downsize_ratio", 0.15))

    # ---------- 场景访问 ----------

    def get_scene(self, scene_key: str) -> Scene | None:
        """返回指定场景定义，未配置返回 None。"""
        return self._scenes.get(scene_key)

    def scene_keys(self) -> list[str]:
        return list(self._scenes.keys())

    # ---------- 场景识别 ----------

    def detect(self) -> tuple[str, float]:
        """返回 (场景key, 置信度)。"""
        scene = self._match_scene()
        if scene is not None:
            return scene
        # 战斗界面已改用模板判定（scene.battle），黑条回退只区分结算/地图
        ratio = self._bottom_black_ratio()
        if ratio > self._settle_ratio:
            return ("settle", ratio)
        return ("map", ratio)

    def detect_detail(self) -> tuple[str, float, list[str]]:
        """场景判定 + 逐场景元素得分明细（诊断误判用）。

        返回 (场景key, 置信度, 明细行列表)；判定逻辑与 detect() 完全一致，
        只是额外输出每个场景各元素的匹配分，便于排查"为什么被判成某个场景"。
        """
        screen, _ = self._screen.window_screen()
        lines: list[str] = []
        hit: str | None = None
        hit_conf = 0.0
        ordered = [s for s in self._scenes.values() if not s.fallback] + [
            s for s in self._scenes.values() if s.fallback
        ]
        for scene in ordered:
            if not scene.elements:
                continue
            parts = [f"{k}={self._probe(screen, el):.3f}" for k, el in scene.elements.items()]
            extra = ""
            for fkey in scene.forbidden or []:
                fel = self._resolve_element(fkey)
                if fel is not None:
                    extra += f" 排除[{fkey}]={self._probe(screen, fel):.3f}"
            req = f" required={scene.required}" if scene.required else ""
            if hit is None and self._scene_matches(scene, screen):
                hit = scene.key
                hit_conf = self._scene_confidence(scene, screen)
                lines.append(
                    f"[{scene.key}]{req}: {' '.join(parts)}{extra} -> 判定命中 ({hit_conf:.3f})"
                )
            else:
                lines.append(f"[{scene.key}]{req}: {' '.join(parts)}{extra}")
        if hit is None:
            ratio = self._bottom_black_ratio()
            hit = "settle" if ratio > self._settle_ratio else "map"
            hit_conf = ratio
            lines.append(f"全部场景未命中 -> 黑条回退 占比{ratio:.3f} -> {hit}")
        return hit, hit_conf, lines

    def _probe(self, screen, element) -> float:
        """元素匹配分（忽略置信度阈值，取主模板+备选模板的最高分）。"""
        result = self._matcher.find(screen, replace(element, confidence=0.0))
        return result.confidence if result else 0.0

    def _match_scene(self) -> tuple[str, float] | None:
        """通过元素匹配识别业务场景，未命中返回 None。

        判定规则：非 fallback 场景优先、fallback（如主界面）最后判定；
        每个场景按 required / forbidden / 任一元素 三种模式命中。
        """
        screen, _ = self._screen.window_screen()
        normal = [s for s in self._scenes.values() if not s.fallback]
        fallback = [s for s in self._scenes.values() if s.fallback]
        for scene in normal + fallback:
            if not scene.elements:
                continue
            if self._scene_matches(scene, screen):
                return (scene.key, self._scene_confidence(scene, screen))
        return None

    def _resolve_element(self, key: str):
        """解析 "场景.元素" 形式的 key 为 Element。"""
        scene_key, _, elem_key = key.partition(".")
        scene = self._scenes.get(scene_key)
        if scene is None:
            return None
        return scene.elements.get(elem_key)

    def _scene_matches(self, scene: Scene, screen) -> bool:
        """判断当前截图是否属于该场景。"""
        # 排除元素：命中任一则不算该场景
        for fkey in scene.forbidden or []:
            el = self._resolve_element(fkey)
            if el is not None and self._matcher.find(screen, el) is not None:
                return False
        # 必需元素：全部命中才算
        if scene.required:
            for k in scene.required:
                el = scene.elements.get(k)
                if el is None or self._matcher.find(screen, el) is None:
                    return False
            return True
        # 默认：任一元素命中即算
        for el in scene.elements.values():
            if self._matcher.find(screen, el) is not None:
                return True
        return False

    def _scene_confidence(self, scene: Scene, screen) -> float:
        """计算场景判定的置信度（命中元素置信度的最大值）。"""
        best = 0.0
        for el in scene.elements.values():
            r = self._matcher.find(screen, el)
            if r and r.confidence > best:
                best = r.confidence
        return best

    def wait_for(self, scene_key: str, timeout: float = 10.0, interval: float = 0.5) -> bool:
        """等待进入指定场景，成功返回 True。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.detect()[0] == scene_key:
                return True
            time.sleep(interval)
        return False

    def wait_any(self, scene_keys: list[str], timeout: float = 10.0) -> str | None:
        """等待进入列表中任一场景，返回命中的场景 key，超时返回 None。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            key, _ = self.detect()
            if key in scene_keys:
                return key
            time.sleep(0.5)
        return None

    def wait_not(self, scene_key: str, timeout: float = 10.0, interval: float = 0.5) -> bool:
        """等待离开指定场景（detect 返回非该场景），成功返回 True。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.detect()[0] != scene_key:
                return True
            time.sleep(interval)
        return False

    # ---------- 黑条检测（沿用 auto_battle.py）----------

    def _bottom_black_ratio(self) -> float:
        rect = self._screen.window_rect()
        if rect is None:
            return 0.0
        left, top, right, bottom = rect
        w = right - left
        h = bottom - top
        region_h = int(h * self._sample_bottom_ratio)

        img = pyautogui.screenshot(region=(left, bottom - region_h, w, region_h))

        new_w = max(1, int(w * self._downsize_ratio))
        new_h = max(1, int(region_h * self._downsize_ratio))
        img = img.resize((new_w, new_h), Image.NEAREST)

        pixels = list(img.convert("RGB").getdata())
        black_count = sum(
            1
            for r, g, b in pixels
            if r < self._black_threshold
            and g < self._black_threshold
            and b < self._black_threshold
        )
        return black_count / len(pixels)
