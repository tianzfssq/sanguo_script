"""主面板：控制按钮 + 模块按钮（自动生成）+ 日志区 + 状态栏。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext, ttk

from core.models import Element
from modules.base import get_all_modules
from orchestrator.context import Context
from orchestrator.logger import Logger
from orchestrator.task_runner import TaskRunner

MAX_LOG_LINES = 200
POLL_MS = 300


class Panel:
    def __init__(self, ctx: Context, task_runner: TaskRunner, logger: Logger):
        self._ctx = ctx
        self._runner = task_runner
        self._logger = logger
        self._mod_buttons: dict[str, ttk.Button] = {}

        self.root = tk.Tk()
        self.root.title("三国自动挂机助手")
        self.root.geometry("760x820")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        logger.subscribe(lambda line: self.root.after(0, self._append_log, line))
        self._poll()

    # ---------- 界面构建 ----------

    def _build(self) -> None:
        self._status_var = tk.StringVar(value="状态: 空闲")
        status = ttk.Label(self.root, textvariable=self._status_var, anchor="w", relief="sunken")
        status.pack(side="bottom", fill="x")

        # 日志区（下方固定 350 高度）
        log_frame = ttk.Frame(self.root)
        log_frame.pack(side="bottom", fill="x", padx=8, pady=(0, 4))
        log_frame.configure(height=350)
        log_frame.pack_propagate(False)
        self._log = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="word")
        self._log.pack(fill="both", expand=True)
        self._log.tag_configure("error", foreground="red")
        self._log.tag_configure("warn", foreground="#c06000")

        # 按键区（上方，占剩余空间）
        top = ttk.Frame(self.root)
        top.pack(side="top", fill="both", expand=True, padx=8, pady=(8, 4))
        self._build_ctrl(top)
        self._build_modules(top)

    def _build_ctrl(self, parent) -> None:
        ctrl = ttk.LabelFrame(parent, text="控制")
        ctrl.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(ctrl)
        row.pack(fill="x")
        ttk.Button(row, text="重新定位窗口", command=self._relocate).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="检测当前场景", command=self._detect_scene).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="停止任务", command=self._stop).pack(side="left")

        # 测试：输入模板文件名，查找当前页面是否能匹配到
        test = ttk.LabelFrame(parent, text="测试：模板查找")
        test.pack(fill="x", pady=(0, 8))
        row2 = ttk.Frame(test)
        row2.pack(fill="x")
        self._tpl_var = tk.StringVar()
        entry = ttk.Entry(row2, textvariable=self._tpl_var)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        entry.bind("<Return>", lambda e: self._find_template())
        ttk.Button(row2, text="查找模板", command=self._find_template).pack(side="left")

    def _build_modules(self, parent) -> None:
        modules = get_all_modules()
        if not modules:
            return
        # 分组固定顺序：主界面 → 导航 → 领地 → 工会 → 测试（未列出的分类排在最后）
        cat_order = ("主界面", "导航", "领地", "工会", "测试")

        def cat_sort_key(mod):
            try:
                return (cat_order.index(mod.category), mod.name)
            except ValueError:
                return (len(cat_order), mod.category, mod.name)

        groups: dict[str, list] = {}
        for mod in sorted(modules, key=cat_sort_key):
            groups.setdefault(mod.category, []).append(mod)

        wrap = ttk.LabelFrame(parent, text="功能")
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, height=230, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind(
            "<Enter>",
            lambda e: canvas.bind_all(
                "<MouseWheel>", lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units")
            ),
        )
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        MAX_COLS = 4
        row = 0
        for cat, mods in groups.items():
            ttk.Label(frame, text=cat, font=("", 10, "bold")).grid(
                row=row, column=0, columnspan=MAX_COLS, sticky="w", pady=(6, 0)
            )
            row += 1
            col = 0
            for mod in mods:
                btn = ttk.Button(
                    frame,
                    text=mod.name,
                    command=lambda k=mod.action_key: self._start(k),
                )
                btn.grid(row=row, column=col, sticky="ew", padx=2, pady=2)
                frame.columnconfigure(col, weight=1)
                self._mod_buttons[mod.action_key] = btn
                col += 1
                if col >= MAX_COLS:
                    col = 0
                    row += 1
            if col:
                row += 1

    # ---------- 动作 ----------

    def _start(self, module_key: str) -> None:
        if not self._runner.start(module_key):
            self._logger.warn("无法启动：已有任务运行中或模块不存在")

    def _stop(self) -> None:
        self._runner.stop_current()

    def _relocate(self) -> None:
        def work() -> None:
            self._logger.info("正在定位游戏窗口...")
            ok = self._ctx.window.wait_until_found(10)
            if ok:
                rect = self._ctx.window.get_rect()
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                self._logger.info(f"窗口已定位: {w}x{h}")
                self._ctx.window.focus()
                self._logger.info("窗口已激活")
            else:
                self._logger.error("未找到游戏窗口，请确认小游戏已打开")

        self._spawn(work)

    def _detect_scene(self) -> None:
        def work() -> None:
            self._logger.info("正在检测当前场景...")
            try:
                scene, conf, lines = self._ctx.states.detect_detail()
                self._logger.info(f"当前场景: {scene} (置信度 {conf:.1%})")
                for line in lines:
                    self._logger.info("  " + line)
            except Exception as exc:
                self._logger.error(f"场景检测失败: {exc}")

        self._spawn(work)

    def _find_template(self) -> None:
        """测试工具：按文件名在 templates/ 找模板并匹配当前页面，打印位置。"""
        name = self._tpl_var.get().strip()
        if not name:
            self._logger.warn("请输入模板文件名，如 c_吃.png")
            return
        name = Path(name).name  # 只取文件名，防路径
        if not name.lower().endswith(".png"):
            name += ".png"

        def work() -> None:
            tpl_path = self._ctx.matcher.templates_dir / name
            if not tpl_path.exists():
                self._logger.error(f"模板不存在: templates/{name}")
                return
            # 置信度设 0 做探测，无论是否过阈值都能拿到最高得分
            element = Element(key=f"probe.{name}", template=name, confidence=0.0)
            try:
                img, (left, top) = self._ctx.screen.window_screen()
                result = self._ctx.matcher.find(img, element)
            except Exception as exc:
                self._logger.error(f"查找失败: {exc}")
                return
            if result is None:
                self._logger.error(f"{name}: 模板比截图还大，无法匹配")
                return
            if result.confidence >= 0.8:
                cx, cy = result.center
                self._logger.info(
                    f"{name}: 找到 (置信度 {result.confidence:.3f}) "
                    f"窗口内({cx},{cy}) 屏幕({cx + left},{cy + top})"
                )
            else:
                self._logger.warn(
                    f"{name}: 未找到（最高得分 {result.confidence:.3f}，低于阈值 0.8）"
                )

        self._spawn(work)

    def _spawn(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    # ---------- 日志与刷新 ----------

    def _append_log(self, line: str) -> None:
        self._log.configure(state="normal")
        tag = "error" if "[ERROR]" in line else "warn" if "[WARN]" in line else None
        self._log.insert("end", line + "\n", tag)
        lines = int(self._log.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:
            self._log.delete("1.0", f"{lines - MAX_LOG_LINES}.0")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _poll(self) -> None:
        running = self._runner.is_running()
        for key, btn in self._mod_buttons.items():
            desired = "disabled" if running else "normal"
            if str(btn["state"]) != desired:
                btn.configure(state=desired)
        task = self._runner.current_task()
        win_ok = self._ctx.window.get_rect() is not None
        state = f"运行中: {task}" if running else "空闲"
        self._status_var.set(f"{state} | 窗口: {'已定位' if win_ok else '未定位'}")
        self.root.after(POLL_MS, self._poll)

    # ---------- 生命周期 ----------

    def _on_close(self) -> None:
        self._runner.stop_current()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
