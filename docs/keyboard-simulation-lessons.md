# 微信小游戏按键模拟经验总结

## 问题

PyAutoGUI `keyDown`/`keyUp` 发送的按键能被游戏输入框接收（出现 "aaaaa"），但游戏画面不响应角色移动。

## 根因

游戏底层（Chromium WebView）对键盘事件的 `event.code` 字段有依赖。`event.code` 由按键的**硬件扫描码**推导而来：

| 方案 | VK码 | 扫描码 | `event.code` | 结果 |
|------|------|--------|-------------|------|
| PyAutoGUI (`keybd_event`) | 有 | **无** | 为空或 `Unidentified` | 输入框能打字，游戏不动 |
| 自定义 SendInput + SCANCODE flag | **无** | 有 | 可能异常 | 游戏不动 |
| **pynput** | 有 | 有 | 正确 | **正常工作** |

PyAutoGUI 底层调用 `keybd_event` 时只传了虚拟键码，扫描码字段为 0。Chromium 无法从扫描码推算出正确的 `event.code`，游戏引擎拿到事件后因 `code` 缺失而丢弃。

我们自己写的 SendInput 版本走了另一个极端——设了 `KEYEVENTF_SCANCODE` flag 但 `wVk=0`，同样不完整。

## 正确做法

`SendInput` 需要**同时设置虚拟键码和扫描码**，且**不加 `KEYEVENTF_SCANCODE` flag**：

```python
ki = KEYBDINPUT(
    wVk=vk_code,      # 虚拟键码
    wScan=scan_code,  # MapVirtualKeyW 获取的扫描码
    dwFlags=0,        # 不要加 KEYEVENTF_SCANCODE
    ...
)
```

`pynput` 恰好就是这么实现的，所以直接用它就行。

## 其他踩坑

1. **窗口定位**：微信小游戏的 `Intermediate D3D Window` 是子窗口，`FindWindow` 找不到，需要 `EnumChildWindows` 枚举
2. **状态检测**：不能用单一黑色阈值区分"战斗"和"结算"。地图底部 ~4% 黑、战斗 ~76% 黑、结算 ~98% 黑，需要两个阈值分层判断
