"""调试工具：把全屏坐标区域换算到游戏窗口内并截图标注，核对模板截图区域。

用法:
    python debug_area.py                     # 默认区域 1688,608 1778,603，等待 8 秒后截图
    python debug_area.py 1688 508 1778 603   # 自定义区域（左上x 左上y 右下x 右下y [等待秒数]）

输出（项目根目录）:
    debug_全屏标注.png   绿框=定位到的游戏窗口区域，红框=指定全屏区域，蓝框=模板匹配位置
    debug_指定区域.png   指定区域放大 2 倍
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui

from core.config import ConfigLoader
from core.image_match import ImageMatcher
from core.models import Element
from core.window import WindowManager

ROOT = Path(__file__).parent
TEMPLATE = "y_营地竞技场.png"


def _save(path: Path, img: np.ndarray) -> None:
    """imencode + tofile 保存（兼容中文路径）。"""
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(str(path))


def main() -> None:
    vals = [int(v) for v in sys.argv[1:]]
    if len(vals) >= 4:
        x1, y1, x2, y2 = vals[:4]
        wait = vals[4] if len(vals) > 4 else 8
    else:
        x1, y1, x2, y2, wait = 1688, 608, 1778, 603, 8
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)

    wm = WindowManager.instance()
    if not wm.find_window():
        print("未找到游戏窗口，请确认小游戏已打开")
        return
    L, T, R, B = wm.get_rect()
    print(f"窗口区域(屏幕): ({L},{T})-({R},{B})  大小 {R-L}x{B-T}")
    print(f"指定区域(屏幕): ({x1},{y1})-({x2},{y2})  大小 {x2-x1}x{y2-y1}")
    if y2 - y1 < 20:
        print("  ! 该区域高度不足 20px，请核对坐标（左上 y 应小于右下 y，如 1688,508 1778,603）")
    print(f"指定区域(窗口内): ({x1-L},{y1-T})-({x2-L},{y2-T})")
    print("指定区域完全在窗口内:", x1 >= L and y1 >= T and x2 <= R and y2 <= B)

    print(f"\n{wait} 秒后截图——请在此期间切到游戏并保持要核对的界面（如弹出二级菜单）...")
    time.sleep(wait)

    full = np.array(pyautogui.screenshot().convert("RGB"))[:, :, ::-1].copy()
    h, w = full.shape[:2]
    print(f"\n截图尺寸: {w}x{h}（若明显大于屏幕分辨率设置，说明存在显示缩放，坐标与像素不一致）")

    # 指定区域放大 2 倍（先存干净裁剪图）
    crop = full[max(0, y1):y2, max(0, x1):x2]
    if crop.size:
        big = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        _save(ROOT / "debug_指定区域.png", big)

    cv2.rectangle(full, (L, T), (R, B), (0, 255, 0), 3)      # 绿=窗口区域
    cv2.rectangle(full, (x1, y1), (x2, y2), (0, 0, 255), 3)  # 红=指定区域

    # 窗口截图内 0 阈值模板匹配，蓝框标出匹配位置
    win = pyautogui.screenshot(region=(L, T, R - L, B - T))
    matcher = ImageMatcher(ConfigLoader(ROOT).templates_dir)
    el = Element(key="probe", template=TEMPLATE, confidence=0.0)
    r = matcher.find(win, el)
    if r:
        rl, rt, rr, rb = r.rect
        cv2.rectangle(full, (rl + L, rt + T), (rr + L, rb + T), (255, 0, 0), 3)
        cx, cy = (rl + rr) // 2, (rt + rb) // 2
        print(f"模板 {TEMPLATE} 匹配: 得分 {r.confidence:.3f} 窗口内({cx},{cy}) 屏幕({cx + L},{cy + T})")
    else:
        print(f"模板 {TEMPLATE} 在窗口截图内无法匹配")
    _save(ROOT / "debug_全屏标注.png", full)
    print("已生成: debug_全屏标注.png（绿=窗口区域 红=指定区域 蓝=模板匹配位置）")
    if crop.size:
        print("已生成: debug_指定区域.png（指定区域放大 2 倍）")


if __name__ == "__main__":
    main()
