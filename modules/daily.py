"""每日任务自动化：依次执行 打竞技场 → 打群雄竞技 → 打工会boss → 钓鱼。

流程：
1. 自动打竞技场（结束后自动退回主界面）
2. 自动打群雄竞技（结束后自动退回主界面）
3. 自动打工会boss（结束后自动退回主界面）
4. 钓鱼（领地）（不在领地会自动进入）
5. 全部完成后返回主界面
"""

from __future__ import annotations

from modules.arena import ArenaAutoModule
from modules.base import BaseModule, register_action
from modules.fishing import FishingModule
from modules.guild import GuildBossModule
from modules.qunxiong import QunxiongAutoModule
from orchestrator.context import Context

# 每日任务固定顺序：竞技场 → 群雄竞技 → 工会boss → 钓鱼
DAILY_TASKS = (
    ("自动打竞技场", ArenaAutoModule),
    ("自动打群雄竞技", QunxiongAutoModule),
    ("自动打工会boss", GuildBossModule),
    ("钓鱼（领地）", FishingModule),
)


@register_action(
    "daily_task", "每日任务", "主界面", "依次：打竞技场 → 打群雄竞技 → 打工会boss → 钓鱼"
)
class DailyTaskModule(BaseModule):
    def run(self, ctx: Context) -> None:
        ctx.logger.info("每日任务启动：打竞技场 → 打群雄竞技 → 打工会boss → 钓鱼")
        total = len(DAILY_TASKS)
        for i, (name, mod_cls) in enumerate(DAILY_TASKS, 1):
            if ctx.stop_event.is_set():
                ctx.logger.info("收到停止信号，每日任务结束")
                return
            ctx.logger.info(f"每日任务 {i}/{total}：{name}")
            mod_cls().run(ctx)
            ctx.logger.info(f"{name} 流程结束")
        # 钓鱼结束后可能停留在领地/钓鱼界面，统一返回主界面方便后续操作
        ctx.logger.info("每日任务全部完成，返回主界面")
        ctx.navigator.back_to_main(timeout=15)
