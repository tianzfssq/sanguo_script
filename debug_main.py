"""临时诊断：截取当前屏幕，输出主界面各元素匹配分数并保存标注图，用于对比 debug_主界面分析.png。"""

from dataclasses import replace

from PIL import Image, ImageDraw

import main
from main import ROOT_DIR, build_context

ctx = build_context()
shot, (left, top) = ctx.screen.window_screen()
state, conf = ctx.states.detect()
print(f"当前场景判定: {state} (conf={conf:.3f})")
print(f"窗口 rect: {ctx.window.get_rect()}")

# 保存未标注的原始截图（与 debug_主界面分析.png 同等视角）
shot.save(ROOT_DIR / "debug_主界面当前.png")
print("已保存原始截图: debug_主界面当前.png")

draw = ImageDraw.Draw(shot)
for scene_key in ("main", "camp_menu"):
    scene = ctx.states.get_scene(scene_key)
    if not scene:
        continue
    for key, el in scene.elements.items():
        r = ctx.matcher.find(shot, el)
        if r:
            x1, y1, x2, y2 = r.rect
            draw.rectangle([x1, y1, x2, y2], outline="red", width=2)
            draw.text((x1, y1 - 14), f"{key} {r.confidence:.3f}", fill="red")
            print(f"  [{scene_key}]{key}: 命中 conf={r.confidence:.3f} at ({r.rect})")
        else:
            probe = ctx.matcher.find(shot, replace(el, confidence=0.0))
            if probe:
                print(
                    f"  [{scene_key}]{key}: 未达阈值, 实际最佳 conf={probe.confidence:.3f} at ({probe.rect})"
                )
            else:
                print(f"  [{scene_key}]{key}: 完全无匹配")

out = ROOT_DIR / "debug_主界面分析_当前.png"
shot.save(out)
print(f"已保存标注图: {out}")

# 输出完整场景判定明细
_, _, lines = ctx.states.detect_detail()
for line in lines:
    print("  " + line)
