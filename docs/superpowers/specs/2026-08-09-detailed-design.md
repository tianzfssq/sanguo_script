# 三国自动挂机助手 — 详细设计文档

- 版本：v1.0
- 日期：2026-08-09
- 关联文档：[需求文档](./2026-08-09-expansion-requirements.md)

---

## 1. 设计目标

1. **可扩展性（首要）**：新增一个游戏功能模块时，无需改动核心层与 GUI 层代码，只需新增模块文件 + 少量配置。
2. **可测试性**：GUI 提供独立功能按钮，每个功能可以单独点击触发，方便按步骤验证。
3. **可配置性**：UI 模板、操作坐标、阈值、超时等全部外部化到配置文件，避免硬编码。
4. **向后兼容**：保留现有 `auto_battle.py` 挂机逻辑，新架构将其作为"模块"复用。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        UI 层 (ui/)                          │
│           Panel：按钮区(自动生成) + 日志区 + 状态栏           │
├─────────────────────────────────────────────────────────────┤
│                    编排层 (orchestrator/)                    │
│   Context(共享上下文)  TaskRunner(任务调度)  Logger(日志总线) │
├─────────────────────────────────────────────────────────────┤
│                    模块层 (modules/)                         │
│   BaseModule(基类) + 业务模块(Arena/Guild/Territory/Daily…)   │
│   ↓ 使用 Action 原语 + 场景/元素定义 (声明式配置)              │
├─────────────────────────────────────────────────────────────┤
│                     核心层 (core/)                           │
│   WindowManager  ScreenCapture  ImageMatcher  InputController│
│   StateDetector  ConfigLoader   Element/Scene(数据模型)      │
└─────────────────────────────────────────────────────────────┘
        ↑ 依赖方向：上层依赖下层，下层绝不反向依赖上层
```

**扩展性核心思想**：

- **配置驱动**：场景（Scene）、界面元素（Element，即模板+坐标）用 TOML 配置声明；新增界面元素只需加配置 + 放模板图片。
- **装饰器注册**：模块通过 `@register_action(...)` 注册，GUI 扫描注册表自动生成按钮。
- **Action 原语**：模块内流程由可组合的原子操作（点击、等待、匹配、移动）拼装，公共逻辑复用。

---

## 3. 核心层设计 (core/)

### 3.1 数据模型 (core/models.py)

```python
# ========== 界面元素 ==========
@dataclass
class Element:
    key: str                    # 唯一标识，如 "main.arena"
    template: str               # 模板文件名（相对 templates/）
    confidence: float = 0.80    # 匹配置信度阈值
    click_offset: tuple = (0, 0)  # 匹配中心点的点击偏移 (dx, dy)
    scale_min: float = 1.0      # 多尺度匹配缩放范围
    scale_max: float = 1.0
    enabled: bool = True

    def match(self, matcher, screen, window_rect) -> MatchResult | None: ...
    def click(self, input_ctrl, screen, window_rect) -> bool: ...

# ========== 场景 ==========
@dataclass
class Scene:
    key: str                    # 如 "main", "arena", "guild", "battle", "settle"
    elements: dict[str, Element]  # 该场景的特征元素（用于识别当前处于哪个场景）
    required: list[str] = None  # 判定场景所需命中的元素 key 列表，默认命中任意一个即算

# ========== 匹配结果 ==========
@dataclass
class MatchResult:
    element: Element
    rect: tuple                  # 屏幕绝对坐标 (left, top, right, bottom)
    confidence: float
    @property
    def center(self) -> tuple: ...
```

### 3.2 窗口管理 (core/window.py)

封装现有 `find_game_window()` / `focus_window()` 逻辑为单例类：

```python
class WindowManager:
    @classmethod
    def instance(cls) -> WindowManager
    def find_window(self) -> bool          # 定位 D3D 子窗口，失败返回 False
    def focus(self) -> None                # 激活 + 恢复窗口
    def get_rect(self) -> tuple            # (left, top, right, bottom)
    def wait_until_found(self, timeout: float) -> bool
```

### 3.3 截图 (core/screen.py)

```python
class ScreenCapture:
    def __init__(self, window_mgr): ...
    def full_screen(self) -> Image          # 全屏截图（用于匹配，坐标体系为屏幕绝对坐标）
    def window_rect(self) -> tuple          # 当前窗口屏幕坐标
    def clip(self, rect) -> Image           # 截取指定区域
```

### 3.4 图像匹配 (core/image_match.py)

基于 OpenCV 的模板匹配封装：

```python
class ImageMatcher:
    def __init__(self, templates_dir: Path): ...
    def load(self, element: Element) -> np.ndarray | None
    def find(self, screen: Image, element: Element) -> MatchResult | None:
        """多尺度模板匹配，返回最佳匹配；低于 confidence 返回 None"""
    def find_any(self, screen, elements: list[Element]) -> MatchResult | None:
        """在多个元素中找置信度最高的那个"""
```

关键实现点：

- 截图转灰度 numpy 数组；模板同样灰度化。
- 多尺度：对模板按 `scale_min~scale_max` 步进缩放（默认 0.05 步长），取置信度最高者。
- 命中条件：`max_val >= element.confidence`，坐标映射回屏幕绝对坐标。

### 3.5 输入控制 (core/input.py)

封装键盘/鼠标操作，全部基于窗口屏幕绝对坐标：

```python
class InputController:
    def click(self, x: int, y: int) -> None              # pyautogui 点击
    def click_element(self, element, screen) -> bool     # 匹配元素并点击
    def press_key(self, key: str, duration: float = 0)   # pynput 按键/长按
    def move_and_click(self, x, y, duration=0.3)         # 模拟人手的移动点击
```

注意：键盘模拟必须使用 pynput（参考 [keyboard-simulation-lessons.md](../../keyboard-simulation-lessons.md)，需同时提供 VK 码 + 扫描码）。

### 3.6 场景状态检测 (core/state.py)

复用现有黑条检测 + 新增元素匹配检测：

```python
class StateDetector:
    def __init__(self, scenes: dict[str, Scene], matcher, screen, ...): ...
    def detect(self) -> tuple[str, float]:
        """返回 (场景key, 置信度)。先按元素匹配识别业务场景，
           匹配不到再回退到黑条检测：settle / battle / map"""
    def wait_for(self, scene_key: str, timeout: float) -> bool
    def wait_any(self, scene_keys: list[str], timeout) -> str | None
```

黑条阈值从 `auto_battle.py` 迁移：结算 > 0.88、战斗 > 0.3、地图其余。

### 3.7 配置加载 (core/config.py)

```python
class ConfigLoader:
    def __init__(self, config_path: Path, templates_dir: Path): ...
    def load_scenes(self) -> dict[str, Scene]
    def load_settings(self) -> dict          # 全局参数（阈值、间隔、超时等）
```

- 配置文件格式：**TOML**（Python 3.11 标准库 `tomllib`，零额外依赖，支持注释）。
- 配置文件位置：`config/scenes.toml`、`config/settings.toml`。

---

## 4. 场景与元素配置（扩展性的关键）

### 4.1 概念

- **Element（元素）**：游戏界面上一个可被模板匹配识别的按钮/图标。一个元素 = 模板图片 + 匹配参数 + 点击偏移。
- **Scene（场景）**：一类界面（主界面、竞技场、领地…），由若干特征元素组成，用于判断"当前在哪个界面"。

### 4.2 配置示例 (config/scenes.toml)

```toml
[scene.main]                      # 主界面
[scene.main.elements.arena]
template = "main_arena.png"       # templates/main_arena.png
confidence = 0.82

[scene.main.elements.guild]
template = "main_guild.png"
confidence = 0.82

[scene.main.elements.territory]
template = "main_territory.png"
confidence = 0.82

[scene.arena]                     # 竞技场界面
[scene.arena.elements.challenge]
template = "arena_challenge.png"
confidence = 0.8
[scene.arena.elements.title]
template = "arena_title.png"

[scene.guild]
[scene.guild.elements.bargain]
template = "guild_bargain.png"
[scene.guild.elements.boss]
template = "guild_boss.png"

[scene.territory]
[scene.territory.elements.task_list]
template = "territory_tasklist.png"
```

**扩展界面元素的方式**：在对应 `[scene.*.elements.*]` 下新增一段配置 + 放一张模板图即可，无需改代码。

---

## 5. 模块层设计 (modules/)

### 5.1 模块基类 (modules/base.py)

```python
class BaseModule(ABC):
    # ---- 注册信息（类属性，供 GUI 自动生成按钮）----
    action_key: str        # 唯一动作标识，如 "arena_auto"
    name: str              # 按钮显示名，如 "自动打竞技场"
    category: str          # 分组，如 "导航" / "主界面" / "领地" / "工会" / "日常"
    description: str = ""
    stop_priority: int = 0 # 停止时优先级（用于复杂任务先停内层）

    # ---- 执行接口 ----
    @abstractmethod
    def run(self, ctx: Context) -> None:
        """执行模块主体逻辑；内部通过 ctx.stop_event 检查是否被要求停止"""
```

```python
# ========== 模块注册表 ==========
_MODULES: dict[str, type[BaseModule]] = {}

def register_action(key, name, category, description=""):
    """装饰器：注册模块到全局注册表"""
    def deco(cls):
        cls.action_key, cls.name = key, name
        cls.category, cls.description = category, description
        _MODULES[key] = cls
        return cls
    return deco

def get_all_modules() -> list[type[BaseModule]]: ...
def get_module(key: str) -> type[BaseModule]: ...
```

### 5.2 Action 原语 (modules/actions.py)

模块流程由以下原子操作拼接，公共逻辑不重复写：

```python
class Action(ABC):
    def execute(self, ctx: Context) -> bool: ...
    def should_stop(self, ctx) -> bool: return ctx.stop_event.is_set()

# ---- 常用原语 ----
class WaitAction(Action):            # 固定等待
    def __init__(self, seconds: float): ...
class WaitSceneAction(Action):       # 等待进入指定场景
    def __init__(self, scene: str, timeout: float = 10): ...
class ClickElementAction(Action):    # 匹配并点击元素
    def __init__(self, element_key: str, wait_after: float = 1.0): ...
class MoveAction(Action):            # 长按方向键（复用挂机移动）
    def __init__(self, direction: str, duration: float): ...
class LoopAction(Action):            # 循环执行子动作序列
    def __init__(self, max_times: int | None, actions: list[Action]): ...
class RandomDelayAction(Action):     # 随机延迟（拟人化，防检测）
    def __init__(self, min_s: float, max_s: float): ...
```

### 5.3 业务模块编写范式

以"自动打竞技场"为例（伪代码）：

```python
@register_action("arena_auto", "自动打竞技场", "主界面")
class ArenaAutoModule(BaseModule):
    def run(self, ctx: Context) -> None:
        nav = ctx.navigator
        nav.enter_scene("arena")                       # 若不在竞技场则进入
        while not ctx.stop_event.is_set():
            if not ctx.states.wait_for("arena", 5): break
            Action(ClickElementAction("arena.challenge", 2)).execute(ctx)
            ctx.states.wait_for("battle", 8)           # 进入战斗
            ctx.battle.loop_until_settle()             # 复用挂机战斗循环
            ctx.states.wait_for("settle", 10)
            ctx.input.press_key("esc")                 # 退出结算
            Action(RandomDelayAction(0.5, 1.5)).execute(ctx)
```

**结论：新增一个功能 = 新建一个模块文件（实现 `run`）+ 注册装饰器 +（可选）补充场景元素配置。GUI 零改动自动出现按钮。**

---

## 6. 编排层设计 (orchestrator/)

### 6.1 共享上下文 Context (orchestrator/context.py)

所有模块/动作通过 Context 访问基础设施，避免全局单例泛滥：

```python
@dataclass
class Context:
    window: WindowManager
    screen: ScreenCapture
    matcher: ImageMatcher
    input_ctrl: InputController
    states: StateDetector
    navigator: Navigator
    battle: BattleHelper          # 挂机战斗循环封装（从 auto_battle.py 迁移）
    logger: Logger
    settings: dict
    stop_event: threading.Event   # 全局停止信号（Ctrl+C 或 GUI 停止按钮）
    data: dict                    # 模块间共享的临时数据（如计数）
```

### 6.2 任务调度 TaskRunner (orchestrator/task_runner.py)

```python
class TaskRunner:
    def start(self, module_key: str) -> bool: ...
    def stop_current(self) -> None: ...
    def is_running(self) -> bool
    def current_task(self) -> str | None
```

- 每个任务在**独立线程**运行（`threading.Thread(daemon=True)`），GUI 线程不被阻塞。
- `stop_current()` 设置 `ctx.stop_event`；模块内所有 Action 在 `should_stop()` 处响应，实现优雅停止。
- 任务结束自动清理 stop_event（置位后重置，保证下次任务可用）。
- 同一时刻只允许一个任务运行：`start` 前检查 `is_running()`。

### 6.3 日志总线 Logger (orchestrator/logger.py)

```python
class Logger:
    def info(self, msg: str): ...
    def warn(self, msg: str): ...
    def error(self, msg: str): ...
    def subscribe(self, handler: Callable[[str], None]): ...  # GUI 订阅显示
```

- 线程安全：内部加锁；GUI 通过 `root.after()` 定时拉取或回调刷新日志区。
- 每条日志带时间戳 `[HH:MM:SS] [级别] 内容`。

---

## 7. GUI 层设计 (ui/)

### 7.1 按钮自动生成 (ui/panel.py)

```python
class Panel:
    def __init__(self, task_runner, modules, logger): ...
    def build(self):
        for category, mods in group_by(modules, lambda m: m.category):
            frame = ttk.LabelFrame(self.root, text=category)
            for m in mods:
                ttk.Button(frame, text=m.name,
                           command=lambda k=m.action_key: self.task_runner.start(k))
```

- **按钮布局按 `category` 分组**（导航 / 主界面 / 领地 / 工会 / 日常 / 控制），新增模块自动归组。
- 控制区固定按钮：`开始挂机`、`停止`、`采集模板`、`重新定位窗口`。
- 运行中按钮置灰（disabled），防止并发启动。
- 窗口 `-topmost` 置顶，可拖动，尺寸 ~420×600。

### 7.2 日志区

- 右侧 `scrolledtext` 只读日志框，自动滚动到末尾，最多保留 200 行。
- 状态栏显示：当前任务 / 当前场景 / 上次检测。

### 7.3 模板采集工具 (ui/template_collector.py)

```python
class TemplateCollector:
    def collect(self, template_name: str): ...
```

交互流程：点击"采集模板" → 提示"把鼠标移到目标按钮上" → 全局监听鼠标（pynput）→ 按 `F2` 以鼠标位置为中心截取 60×60 区域 → 保存到 `templates/<name>.png` → 提示下一项。采集清单从 `config/scenes.toml` 中 `template` 字段缺失的文件生成，闭环支持"缺什么采什么"。

---

## 8. 业务模块详细设计

### 8.1 导航模块 modules/navigation.py

```python
class Navigator:
    """通用场景切换，被所有业务模块依赖"""
    def current_scene(self) -> str                 # 通过 StateDetector 识别
    def enter_scene(self, target: str, timeout: float = 20) -> bool:
        """从主界面进入目标场景：回到主界面 → 点击对应入口元素"""
    def back_to_main(self, timeout: float = 20) -> bool:
        """按 ESC/返回按钮回到主界面，带超时与兜底"""
```

主界面入口元素映射（配置声明）：

| 目标场景 | 主界面入口元素 |
|----------|----------------|
| arena | `main.arena` |
| guild | `main.guild` |
| territory | `main.territory` |

### 8.2 挂机战斗 BattleHelper (modules/battle.py)

从 `auto_battle.py` 迁移逻辑，封装为可复用组件：

```python
class BattleHelper:
    def loop_until_settle(self, max_time: float = 300) -> bool:
        """A/D 移动遇敌 → 黑条检测战斗 → 结算 → 点击退出 → 循环，直到出现结算或超时"""
    def exit_settle(self) -> None: ...
```

### 8.3 竞技场 modules/arena.py

| 动作 | 逻辑 |
|------|------|
| `arena_auto`（自动打竞技场） | `Navigator.enter_scene("arena")` → 循环：点挑战 → 等待进入战斗 → `BattleHelper.loop_until_settle()` → 退出结算 → 返回竞技场 → 继续；stop 或识别到"次数不足"文案模板则停止 |
| `arena_enter`（进入竞技场） | 仅 `enter_scene("arena")` |

### 8.4 工会 modules/guild.py

| 动作 | 逻辑 |
|------|------|
| `guild_enter`（进入工会） | `enter_scene("guild")` |
| `guild_bargain`（自动砍价） | 进入工会 → 点砍价元素 → 循环点"砍价"直到匹配到"砍价完成"模板或 stop；每次间隔随机延迟 |
| `guild_boss`（工会打 Boss） | 进入工会 → 点 Boss 入口 → 进入战斗后复用 `BattleHelper` → 结算退出 |

### 8.5 领地 modules/territory.py

| 动作 | 逻辑 |
|------|------|
| `territory_enter`（进入领地） | `enter_scene("territory")` |
| `territory_task`（自动领地任务） | 进入领地 → 打开任务列表 → 依次匹配"可接取/可完成"按钮模板 → 点击 → 完成任务后点"领取奖励" → 循环直到无可执行任务 |

### 8.6 日常 modules/daily.py

锻造 / 钓鱼 / 烹饪三个动作同构，统一由"日常入口元素 + 完成判定元素"驱动：

| 动作 | 入口元素 | 完成判定 |
|------|----------|----------|
| `daily_forge`（锻造日常） | `territory.forge` | 次数/可领取模板命中 |
| `daily_fish`（钓鱼日常） | `territory.fish` | 同上 |
| `daily_cook`（烹饪日常） | `territory.cook` | 同上 |

三个模块继承同一个抽象父类 `DailyTaskModule`，仅覆盖元素 key 和按钮文案，避免重复代码：

```python
class DailyTaskModule(BaseModule):
    entry_element: str      # 子类覆盖
    done_element: str       # 子类覆盖
    def run(self, ctx): ... # 通用流程，模板化
```

### 8.7 钓鱼小游戏 modules/fishing_game.py

| 动作 | 逻辑 |
|------|------|
| `fishing_game`（钓鱼小游戏） | 进入钓鱼 → 等待进度条/指针区域出现（模板匹配定位区域）→ 高频截图（0.05s）分析指针位置 → 指针进入目标区间时点击 → 重复至一轮结束 |

检测策略：匹配指针模板 → 计算指针中心 x 与目标区间（通过两张参考模板标定）的相对位置 → 决策点击。该模块是**唯一允许高频截图**的模块，配置项 `poll_interval` 独立控制。

---

## 9. 新增功能扩展指南（完整步骤）

以新增"每日签到"功能为例：

1. **截图放模板**：将签到按钮截图放入 `templates/main_checkin.png`。
2. **加配置**：在 `config/scenes.toml` 的 `[scene.main.elements]` 下加 `checkin` 元素（模板、置信度）；如签到界面有独立特征再加 `[scene.checkin]`。
3. **新建模块** `modules/checkin.py`：

```python
from .base import BaseModule, register_action
from .actions import *

@register_action("checkin_daily", "每日签到", "主界面")
class CheckinModule(BaseModule):
    def run(self, ctx: Context) -> None:
        if not Action(ClickElementAction("main.checkin", 1.5)).execute(ctx):
            ctx.logger.warn("未找到签到入口")
            return
        ctx.logger.info("签到完成")
```

4. **无需改动任何其他代码**：重启程序，GUI 自动在"主界面"分组出现"每日签到"按钮。

---

## 10. 目录结构与文件清单

```
d:\Tools\scripe-sanguo\
├── auto_battle.py                  # 旧脚本（保留，作为 BattleHelper 实现参考）
├── main.py                         # 新入口：加载配置 → 构建 Context → 启动 GUI
├── config/
│   ├── settings.toml               # 全局参数：阈值/间隔/超时/窗口参数
│   └── scenes.toml                 # 场景与元素定义（扩展点）
├── templates/                      # 模板图片（用户采集或手工放置）
├── core/
│   ├── __init__.py
│   ├── models.py                   # Element / Scene / MatchResult
│   ├── window.py                   # WindowManager
│   ├── screen.py                   # ScreenCapture
│   ├── image_match.py              # ImageMatcher
│   ├── input.py                    # InputController
│   ├── state.py                    # StateDetector
│   └── config.py                   # ConfigLoader
├── modules/
│   ├── __init__.py                 # 导入所有子模块触发注册
│   ├── base.py                     # BaseModule / register_action
│   ├── actions.py                  # Action 原语
│   ├── navigation.py               # Navigator
│   ├── battle.py                   # BattleHelper
│   ├── arena.py
│   ├── guild.py
│   ├── territory.py
│   ├── daily.py
│   └── fishing_game.py
├── orchestrator/
│   ├── __init__.py
│   ├── context.py                  # Context
│   ├── task_runner.py              # TaskRunner
│   └── logger.py                   # Logger
├── ui/
│   ├── __init__.py
│   ├── panel.py                    # 主面板（按钮自动生成）
│   └── template_collector.py       # 模板采集
└── requirements.txt                # 依赖：pyautogui pynput pillow opencv-python pywin32 numpy
```

`modules/__init__.py` 必须 import 所有子模块（触发装饰器注册）；GUI 只依赖注册表，不认识具体模块——这是"零侵入扩展"的关键。

---

## 11. 线程模型

```
main thread:  Tkinter 主循环（GUI 事件）
worker thread: 当前任务（TaskRunner 启动），独占使用 InputController
GUI→worker:   仅通过 stop_event / start() 交互
worker→GUI:   仅通过 Logger.subscribe 回调（root.after 调度刷新）
```

- 所有 pyautogui/pynput 操作**只允许在 worker 线程**执行，避免与 GUI 抢焦点。
- `stop_event` 由 TaskRunner 维护：启动时清空、停止时置位、结束后重置。

---

## 12. 测试策略

| 层面 | 方式 |
|------|------|
| 单元测试 | ImageMatcher 的匹配逻辑（用模拟图）、ConfigLoader 解析、Logger 线程安全 |
| 冒烟测试 | GUI 启动 → 点击"进入竞技场"→ 验证窗口聚焦与场景识别 |
| 分步验收 | 借助 GUI 按钮逐个验证：进入领地 → 进入竞技场 → 进入工会 → 各自动化按钮 → 停止 |
| 回退测试 | 模板缺失/窗口未找到/游戏弹窗 等异常路径不得崩溃，应有日志与兜底 |

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 模板在不同分辨率失配 | 多尺度匹配 + 模板重采集工具 + 置信度阈值可调 |
| 游戏弹窗干扰 | Navigator.back_to_main 增加"关闭弹窗"兜底（匹配通用关闭按钮） |
| 长时间运行漂移（点击失效） | 每次关键操作前 `wait_for` 目标场景，超时则重试/回主界面重进 |
| 误触 GUI | worker 线程与 GUI 线程分离，输入操作仅发生在 worker 线程 |
| 反作弊检测 | RandomDelayAction 拟人化间隔；所有重复操作带随机扰动 |

---

## 14. 分阶段实施计划

| 阶段 | 内容 | 验收标准 |
|------|------|----------|
| P1 | core 层全部 + Context + Logger + GUI 骨架 | 启动 GUI，日志显示，窗口定位成功 |
| P2 | Navigator + BattleHelper + 模板采集工具 | 采集模板后能点按钮进领地/竞技场/工会 |
| P3 | arena_auto + arena_enter | 按钮可触发，能自动打竞技场并停止 |
| P4 | territory_task + daily_* | 领地任务与日常可自动化 |
| P5 | guild_bargain + guild_boss | 工会功能可用 |
| P6 | fishing_game | 钓鱼小游戏可运行 |
