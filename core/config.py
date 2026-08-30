"""配置加载：读取 TOML 配置，构建 Scene/Element 数据模型。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from .models import Element, Scene


class ConfigLoader:
    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self.config_dir = self.root_dir / "config"
        self.templates_dir = self.root_dir / "templates"
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def _read(self, name: str) -> dict:
        path = self.config_dir / name
        if not path.exists():
            return {}
        with open(path, "rb") as f:
            return tomllib.load(f)

    def load_settings(self) -> dict:
        """读取 settings.toml。"""
        return self._read("settings.toml")

    def load_scenes(self) -> dict[str, Scene]:
        """读取 scenes.toml，构建 {场景key: Scene}。"""
        raw = self._read("scenes.toml")
        scenes: dict[str, Scene] = {}
        for scene_key, sdata in raw.get("scene", {}).items():
            elements: dict[str, Element] = {}
            for ekey, edata in (sdata.get("elements") or {}).items():
                elements[ekey] = Element(
                    key=f"{scene_key}.{ekey}",
                    template=str(edata.get("template", "")),
                    alt_templates=tuple(edata.get("alt_templates", ())),
                    confidence=float(edata.get("confidence", 0.8)),
                    click_offset=tuple(edata.get("click_offset", (0, 0))),
                    scale_min=float(edata.get("scale_min", 1.0)),
                    scale_max=float(edata.get("scale_max", 1.0)),
                    enabled=bool(edata.get("enabled", True)),
                )
            scenes[scene_key] = Scene(
                key=scene_key,
                elements=elements,
                required=sdata.get("required"),
                forbidden=sdata.get("forbidden"),
                fallback=bool(sdata.get("fallback", False)),
            )
        return scenes

    def load_nav(self) -> dict[str, list[str]]:
        """读取导航路径配置 [nav.paths]，如 {"arena": ["main.camp", "camp_menu.arena_entry"]}。"""
        raw = self._read("scenes.toml")
        return {k: list(v) for k, v in raw.get("nav", {}).get("paths", {}).items()}
