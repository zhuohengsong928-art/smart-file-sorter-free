"""撤销恢复：把某次整理移动过的文件按历史记录原路送回。

毕设升级模块（v2.4.0 新增）：
- 依据 history 历史库中该次运行的 actions 记录（source → dest），
  逆序把文件从 dest 移回 source，并恢复原文件名；
- 安全边界：只移动历史里 action='moved' 的文件；目标位置被占用、
  或文件已不在原地时跳过并报告，绝不覆盖任何现有文件；
- 撤销成功后把该 run 标记为 undone，不可重复撤销；
- dry_run=True 时只报告计划，不实际移动。
"""

import os
import shutil
from pathlib import Path
from typing import Any, Optional

from . import history
from .logger import get_logger


def undo_run(
    run_id: Optional[int] = None,
    dry_run: bool = False,
    db_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """撤销一次整理运行（默认撤销最近一次未撤销的运行）。

    Returns:
        {run_id, restored: [原路径...], skipped: [{path, reason}...]}
    """
    log = get_logger()
    if run_id is None:
        run_id = history.latest_run_id(db_path)
        if run_id is None:
            return {"run_id": None, "restored": [], "skipped": []}
    if history.is_undone(run_id, db_path):
        raise ValueError(f"运行 #{run_id} 已经撤销过，不能重复撤销。")

    actions = [
        a for a in history.list_actions(run_id, db_path) if a["action"] == "moved"
    ]
    restored: list[str] = []
    skipped: list[dict[str, str]] = []

    # 逆序还原，避免同目录内改名链互相干扰
    for a in reversed(actions):
        cur, back = a["dest"], a["source"]
        if not os.path.exists(cur):
            skipped.append({"path": cur, "reason": "文件已不在整理后的位置（可能被手动移动或删除）"})
            continue
        if os.path.exists(back):
            skipped.append({"path": back, "reason": "原位置已被其他文件占用，未覆盖"})
            continue
        if dry_run:
            restored.append(back)
            continue
        try:
            os.makedirs(os.path.dirname(back), exist_ok=True)
            shutil.move(cur, back)
            restored.append(back)
            log.info("撤销还原: %s → %s", cur, back)
        except OSError as e:
            skipped.append({"path": cur, "reason": f"移动失败: {e}"})

    if not dry_run and restored:
        history.mark_undone(run_id, db_path)
    log.info(
        "撤销运行 #%s 完成: 还原 %d 个，跳过 %d 个（dry_run=%s）",
        run_id, len(restored), len(skipped), dry_run,
    )
    return {"run_id": run_id, "restored": restored, "skipped": skipped}
