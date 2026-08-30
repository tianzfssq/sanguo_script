"""
三国自动挂机脚本
定位游戏窗口 → 前台聚焦 → A/S 移动 → 检测底部黑条 → 点击退出 → 循环
"""

import time
import pyautogui
import win32gui
import win32con
from pynput.keyboard import Controller
from PIL import Image

# ========== 游戏窗口 ==========
CHILD_CLASS = "Intermediate D3D Window"

# ========== 可配置参数 ==========
SAMPLE_BOTTOM_RATIO = 0.15   # 窗口底部检测区域比例
BLACK_THRESHOLD = 40         # RGB 各通道低于此值视为黑像素
SETTLE_RATIO = 0.88          # 黑像素占比 > 此值 = 结算画面
DETECT_INTERVAL = 2.0        # 检测间隔（秒）
MOVE_DURATION = 1.5          # 单方向按住时长（秒）
EXIT_DELAY = 1.5             # 点击退出后等待地图加载（秒）
DOWNSIZE_RATIO = 0.15        # 样本缩放比例

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

keyboard = Controller()


def hold_key(key_char, duration):
    """模拟按住按键"""
    keyboard.press(key_char)
    time.sleep(duration)
    keyboard.release(key_char)


# ========== 窗口定位 ==========

def find_game_window():
    candidates = []

    def check_children(parent_hwnd, _):
        if not win32gui.IsWindowVisible(parent_hwnd):
            return True
        def find_child(chwnd, __):
            if win32gui.GetClassName(chwnd) != CHILD_CLASS:
                return True
            rect = win32gui.GetWindowRect(chwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200 or w > 3000 or h > 3000:
                return True
            if rect[0] > 30000 or rect[1] > 30000:
                return True
            pcls = win32gui.GetClassName(parent_hwnd)
            ptitle = win32gui.GetWindowText(parent_hwnd)
            candidates.append((parent_hwnd, chwnd, rect, pcls, ptitle))
            return True
        win32gui.EnumChildWindows(parent_hwnd, find_child, None)
        return True

    win32gui.EnumWindows(check_children, None)

    print("找到的 D3D 子窗口:")
    for _, _, r, pcls, ptitle in candidates:
        w, h = r[2] - r[0], r[3] - r[1]
        print(f"  - 父窗口=\"{ptitle}\" 类=\"{pcls}\" 尺寸={w}x{h}")

    chrome = [(p, c, r, t) for p, c, r, pcls, t in candidates if pcls == "Chrome_WidgetWin_0"]
    if chrome:
        chrome.sort(key=lambda x: (x[2][2] - x[2][0]) * (x[2][3] - x[2][1]))
        parent, child, rect, ptitle = chrome[0]
        print(f"选中游戏窗口: 父窗口=\"{ptitle}\"")
        return parent, child, rect

    if candidates:
        parent, child, rect, _, ptitle = candidates[0]
        print(f"选中游戏窗口(兜底): 父窗口=\"{ptitle}\"")
        return parent, child, rect

    raise RuntimeError(f"未找到子窗口类名 '{CHILD_CLASS}'，请确认小游戏已打开")


def focus_window(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.3)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.2)


# ========== 画面检测 ==========

def get_bottom_black_ratio(rect):
    left, top, right, bottom = rect
    w = right - left
    h = bottom - top
    region_h = int(h * SAMPLE_BOTTOM_RATIO)

    img = pyautogui.screenshot(region=(left, bottom - region_h, w, region_h))

    new_w = max(1, int(w * DOWNSIZE_RATIO))
    new_h = max(1, int(region_h * DOWNSIZE_RATIO))
    img = img.resize((new_w, new_h), Image.NEAREST)

    pixels = list(img.get_flattened_data())
    black_count = sum(
        1 for r, g, b in pixels
        if r < BLACK_THRESHOLD and g < BLACK_THRESHOLD and b < BLACK_THRESHOLD
    )
    return black_count / len(pixels)


def detect_state(rect):
    ratio = get_bottom_black_ratio(rect)
    if ratio > SETTLE_RATIO:
        return 'settle', ratio
    elif ratio > 0.3:
        return 'battle', ratio
    else:
        return 'map', ratio


def exit_battle(rect):
    left, top, right, bottom = rect
    cx = (left + right) // 2
    cy = bottom - 20
    pyautogui.click(cx, cy)
    time.sleep(EXIT_DELAY)


# ========== 主循环 ==========

def main():
    print("=" * 40)
    print("三国自动挂机脚本")

    print("正在定位游戏窗口...")
    parent_hwnd, child_hwnd, rect = find_game_window()
    left, top, right, bottom = rect
    print(f"游戏区域: ({left}, {top})-({right}, {bottom}) {right-left}x{bottom-top}")

    print("正在激活窗口...")
    focus_window(parent_hwnd)
    print("窗口已激活")

    print(f"检测间隔: {DETECT_INTERVAL}s | 移动切换: {MOVE_DURATION}s")
    print(f"结算阈值: 黑像素>{SETTLE_RATIO}")
    print("Ctrl+C 停止 | 鼠标移到左上角急停")
    print("=" * 40)
    time.sleep(2)

    direction = "a"
    last_detect = 0.0
    prev_state = None

    try:
        while True:
            now = time.time()

            hold_key(direction, MOVE_DURATION)
            direction = "d" if direction == "a" else "a"

            if now - last_detect >= DETECT_INTERVAL:
                state, ratio = detect_state(rect)
                if state != prev_state:
                    names = {'map': '地图', 'battle': '战斗中', 'settle': '结算'}
                    print(f"[状态] {names[state]} (黑像素: {ratio:.1%})")
                    prev_state = state

                if state == 'settle':
                    print("[动作] 结算画面，点击退出")
                    exit_battle(rect)
                    prev_state = None

                last_detect = now

    except KeyboardInterrupt:
        print("\n脚本已停止")
    except pyautogui.FailSafeException:
        print("\n触发安全机制，脚本已停止")


if __name__ == "__main__":
    main()
