"""临时诊断：截取当前屏幕，输出领地各元素匹配分数并保存标注图。"""

from dataclasses import replace

from PIL import Image, ImageDraw

import main
from main import ROOT_DIR, build_context

ctx = build_context()
shot, (left, top) = ctx.screen.window_screen()
state, conf = ctx.states.detect()
print(f"当前场景判定: {state} (conf={conf:.3f})")
print(f"窗口 rect: {ctx.window.get_rect()}")

territory = ctx.states.get_scene("territory")
draw = ImageDraw.Draw(shot)
for key, el in territory.elements.items():
    r = ctx.matcher.find(shot, el)
    if r:
        x1, y1, x2, y2 = r.rect
        draw.rectangle([x1, y1, x2, y2], outline="red", width=2)
        draw.text((x1, y1 - 14), f"{key} {r.confidence:.3f}", fill="red")
        print(f"  {key}: 命中 ({r.rect}) conf={r.confidence:.3f}")
    else:
        # 用 0 阈值查找真实最佳分数（即使低于配置阈值），用于诊断差距
        probe = ctx.matcher.find(shot, replace(el, confidence=0.0))
        if probe:
            print(f"  {key}: 未达阈值, 实际最佳 conf={probe.confidence:.3f} at ({probe.rect})")
        else:
            print(f"  {key}: 完全无匹配")

out = ROOT_DIR / "debug_camp.png"
shot.save(out)
print(f"已保存标注图: {out}")

