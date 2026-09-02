# AGENT.md — 大模型协作须知

本项目的检测/判断逻辑文档为 **docs/判断逻辑.md**，记录所有场景判定、模板匹配、
导航、战斗与各业务模块的判断规则及历史踩坑。

## 强制要求

**任何涉及以下内容的改动，必须同步更新 docs/判断逻辑.md 的对应章节：**

- `config/scenes.toml`：新增/修改场景、元素、required/forbidden、alt_templates、导航路径；
- `core/state.py`：判定顺序、命中规则、黑条回退、诊断输出；
- `core/image_match.py` / `core/models.py`：匹配算法、阈值语义、多模板机制；
- `config/settings.toml` 中 detect/template 相关参数；
- `modules/navigation.py` 的 back_to_main / enter_scene 逻辑；
- `modules/battle.py` 的战斗结束/结算判定；
- 各业务模块（arena/guild/fishing/daily/clicker 等）中"何时判定成功/失败/重试"的分支逻辑。

## 更新方式

- 改哪节就更新哪节，保持文档与代码一致（过时的描述直接删改，不留"曾经"）；
- 新增踩坑经验追加到文档第 9 节「历史经验」；
- 表格中的模板名、阈值、次数等具体数值需与 toml/代码实际值一致。

## 全局规则（强制）

- **停止任务必须先松开按键**：所有长按按键操作（`press_key` 且 `duration > 0`，
  如挂机 A/D、钓鱼 A/W）必须把 `ctx.stop_event` 传入 `press_key`，停止任务时立即
  松开按键，不允许停止后按键仍处于按下状态；`release` 必须放在 `finally` 中，
  保证中途异常也不残留按下状态。
- **停止任务热键 `~`**：任务运行期间按 `~`（` 键）触发 `TaskRunner.stop_current()`
  停止当前任务（见 `orchestrator/task_runner.py`）。新增模块的循环/长按逻辑必须
  响应 `ctx.stop_event`（及时 return/break），不得阻塞或忽略停止信号。

## 项目约定（简版）

- 分层：core（窗口/截图/匹配/输入/状态）→ modules（业务）→ orchestrator → ui（Tkinter 面板）；
- 新功能：实现 BaseModule.run() + `@register_action(key, name, category, desc)` +
  在 `modules/__init__.py` import，GUI 自动生成按钮；
- 模板放 `templates/`（支持中文文件名），元素配置在 `config/scenes.toml`；
- **模板命名规范**：`首字拼音首字母_中文名.png`（如 `c_吃.png`、`z_主界面营地.png`），
  同一元素多种外观加序号后缀（`z_主界面营地1.png`）；新增模板必须遵守并同步 scenes.toml；
- **模板裁剪规则（强制）**：裁剪模板时只截目标自身的特征区域（文字/图标），**严禁带周边背景**，
  也要避开临时性元素（红点、角标、高亮描边等）。带背景的模板在场景背景变化后即失配
  （案例：`j_竞技场检测.png` 裁剪时带了背景，页签底色从暗底变选中亮黄后仅 0.554 导致进场景判定失败）；
  若目标本身存在多种外观状态（未选中/选中、普通/高亮），为每种状态各裁一个模板并配置 alt_templates。
- 回复与代码注释使用中文。
