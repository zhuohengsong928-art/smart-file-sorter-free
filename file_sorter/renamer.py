"""重命名器：根据模板批量重命名文件 + 内容级去重容错。"""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .logger import get_logger

# 计算文件 MD5 的缓冲区大小
_HASH_BUF = 64 * 1024  # 64 KB


def _file_md5(file_path: str) -> str:
    """快速计算文件的 MD5 哈希（用于内容去重）。"""
    h = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(_HASH_BUF):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def generate_new_name(
    original_name: str,
    config: dict[str, Any],
    counter: int = 0,
) -> str:
    """根据重命名模板生成新文件名。

    支持的占位符：
        {date}  — 当前日期（格式由 date_format 控制）
        {name}  — 原文件名
        {ext}   — 扩展名（含点号）
        {counter} — 递进计数器
    """
    date_str = datetime.now().strftime(config.get("date_format", "%Y%m%d"))
    base, ext = os.path.splitext(original_name)
    template = config.get("rename_format", "{date}_{name}")

    new_name = template.format(
        date=date_str,
        name=original_name,
        base=base,
        ext=ext,
        counter=counter,
    )

    return new_name


def resolve_destination(
    source_path: str,
    dest_dir: str,
    new_name: str,
    dedup_by_content: bool = True,
) -> tuple[str, dict[str, Any]]:
    """解析目标路径，自动处理重名冲突。

    容错策略（两层）：
      1. 名称冲突 → 递增后缀 (1), (2), (3) ...
      2. 内容去重 → 若目标已存在且 MD5 相同，标记为「真重复」，跳过移动

    Args:
        source_path: 源文件路径
        dest_dir: 目标目录
        new_name: 期望的新文件名
        dedup_by_content: 是否启用内容去重

    Returns:
        (最终目标路径, 元信息)
        元信息包含:
          - name_conflict: bool — 是否发生名称冲突
          - content_duplicate: bool — 是否为内容重复（真重复）
          - conflict_counter: int — 冲突递增次数
    """
    log = get_logger()
    dest_path = os.path.join(dest_dir, new_name)
    meta: dict[str, Any] = {
        "name_conflict": False,
        "content_duplicate": False,
        "conflict_counter": 0,
    }

    # 无冲突：直接返回
    if not os.path.exists(dest_path):
        return dest_path, meta

    # 内容去重：目标存在 → 比较 MD5
    if dedup_by_content:
        source_md5 = _file_md5(source_path)
        dest_md5 = _file_md5(dest_path)
        if source_md5 and dest_md5 and source_md5 == dest_md5:
            meta["content_duplicate"] = True
            log.info(
                "内容去重命中: %s ≅ %s (MD5=%s)",
                os.path.basename(source_path),
                os.path.basename(dest_path),
                source_md5[:8],
            )
            return dest_path, meta

    # 名称冲突：递增后缀
    meta["name_conflict"] = True
    base, ext = os.path.splitext(new_name)
    counter = 1
    while True:
        candidate = os.path.join(dest_dir, f"{base} ({counter}){ext}")
        if not os.path.exists(candidate):
            meta["conflict_counter"] = counter
            log.warning(
                "名称冲突: %s → %s (%d)",
                new_name,
                os.path.basename(candidate),
                counter,
            )
            return candidate, meta

        # 也检查内容去重
        if dedup_by_content:
            source_md5 = source_md5 if "source_md5" in dir() else _file_md5(source_path)
            candidate_md5 = _file_md5(candidate)
            if source_md5 and candidate_md5 and source_md5 == candidate_md5:
                meta["content_duplicate"] = True
                log.info(
                    "内容去重命中(冲突链): %s ≅ %s (MD5=%s)",
                    os.path.basename(source_path),
                    os.path.basename(candidate),
                    source_md5[:8],
                )
                return candidate, meta

        counter += 1
