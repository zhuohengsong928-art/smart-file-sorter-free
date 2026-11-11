"""整理历史记录：用 SQLite 保存每次整理的运行与文件级明细。

毕设升级模块（v2.4.0 新增）：
- 每次真实执行整理（非 dry-run）后，把本次运行的汇总与每个文件的
  来源、去向、分类、结果写入本地 SQLite 数据库；
- 支持按运行查询历史、在 GUI / CLI 中回溯“某个文件当时被整理到哪去了”；
- 数据库放在用户主目录 ~/.smart-file-sorter/history.db，
  可用环境变量 SFS_HISTORY_DB 覆盖（测试用）。
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .logger import get_logger

_DB_ENV = "SFS_HISTORY_DB"


def default_db_path() -> Path:
    """返回历史数据库路径（可用环境变量覆盖）。"""
    env = os.environ.get(_DB_ENV)
    if env:
        return Path(env)
    return Path.home() / ".smart-file-sorter" / "history.db"


def _connect(db_path: Optional[str | Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL,
            total_files INTEGER NOT NULL DEFAULT 0,
            moved       INTEGER NOT NULL DEFAULT 0,
            duplicates  INTEGER NOT NULL DEFAULT 0,
            total_size  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id   INTEGER NOT NULL REFERENCES runs(id),
            source   TEXT NOT NULL,
            dest     TEXT NOT NULL,
            category TEXT NOT NULL,
            old_name TEXT NOT NULL,
            new_name TEXT NOT NULL,
            size     INTEGER NOT NULL DEFAULT 0,
            action   TEXT NOT NULL CHECK (action IN ('moved', 'duplicate_skipped'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_run ON actions(run_id)")
    # 迁移：老版本数据库补 undone 列（撤销功能用）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    if "undone" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN undone INTEGER NOT NULL DEFAULT 0")
    return conn


def record_run(
    organized: dict[str, list[dict[str, Any]]],
    db_path: Optional[str | Path] = None,
) -> int:
    """把一次整理结果写入历史库，返回 run_id。

    Args:
        organized: archiver.organize_files 的返回值
                   {分类名: [操作记录, ...]}
    """
    log = get_logger()
    rows: list[dict[str, Any]] = []
    for records in organized.values():
        rows.extend(records)
    moved = sum(1 for r in rows if not r.get("content_duplicate"))
    dups = sum(1 for r in rows if r.get("content_duplicate"))
    total_size = sum(int(r.get("size", 0)) for r in rows)

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO runs (created_at, total_files, moved, duplicates, total_size)"
            " VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), len(rows), moved, dups, total_size),
        )
        run_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO actions (run_id, source, dest, category, old_name, new_name, size, action)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    r["source"],
                    r["dest"],
                    r["category"],
                    r["old_name"],
                    r["new_name"],
                    int(r.get("size", 0)),
                    "duplicate_skipped" if r.get("content_duplicate") else "moved",
                )
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()
    log.info("历史记录已写入: run_id=%d（文件 %d，移动 %d，去重跳过 %d）", run_id, len(rows), moved, dups)
    return run_id


def list_runs(limit: int = 20, db_path: Optional[str | Path] = None) -> list[dict[str, Any]]:
    """按时间倒序返回最近的运行记录。"""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_actions(run_id: int, db_path: Optional[str | Path] = None) -> list[dict[str, Any]]:
    """返回某次运行的全部文件级明细。"""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT * FROM actions WHERE run_id = ? ORDER BY id", (run_id,)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def is_undone(run_id: int, db_path: Optional[str | Path] = None) -> bool:
    """该次运行是否已被撤销。"""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT undone FROM runs WHERE id = ?", (run_id,)).fetchone()
        return bool(row and row["undone"])
    finally:
        conn.close()


def mark_undone(run_id: int, db_path: Optional[str | Path] = None) -> None:
    """把一次运行标记为已撤销（撤销不可重复执行）。"""
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE runs SET undone = 1 WHERE id = ?", (run_id,))
        conn.commit()
    finally:
        conn.close()


def latest_run_id(db_path: Optional[str | Path] = None) -> Optional[int]:
    """最近一次未撤销的运行编号；没有则 None。"""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM runs WHERE undone = 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def summary_stats(db_path: Optional[str | Path] = None) -> dict[str, int]:
    """全局累计统计：总运行次数、累计整理文件数、累计处理字节数。"""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS runs, COALESCE(SUM(total_files),0) AS files,"
            " COALESCE(SUM(total_size),0) AS bytes FROM runs"
        ).fetchone()
        return {"runs": int(row["runs"]), "files": int(row["files"]), "bytes": int(row["bytes"])}
    finally:
        conn.close()
