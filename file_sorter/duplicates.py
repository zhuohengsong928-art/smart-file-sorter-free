"""重复文件扫描与清理。

毕设升级模块（v2.4.0 新增）：
- 两阶段比对：先按文件大小粗筛（大小不同绝不重复），
  再对同大小文件计算 MD5 确认内容完全一致，避免全量哈希的浪费；
- 输出每组重复文件的可回收空间，帮助用户决定是否清理；
- 删除操作默认 dry_run（只报告不动手），且每组至少保留一份。
"""

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable

from .logger import get_logger

_CHUNK = 1024 * 1024  # 1 MiB 分块读，避免大文件一次进内存


def file_md5(path: str | Path) -> str:
    """计算文件 MD5（分块读取）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _iter_files(directories: Iterable[str | Path], recursive: bool) -> Iterable[Path]:
    for d in directories:
        root = Path(d)
        if not root.exists():
            continue
        it = root.rglob("*") if recursive else root.glob("*")
        for p in it:
            if p.is_file():
                yield p


def find_duplicates(
    directories: Iterable[str | Path],
    recursive: bool = True,
    min_size: int = 1,
) -> list[dict[str, Any]]:
    """扫描目录，返回内容重复的文件组。

    Returns:
        每组一个字典：{md5, size, paths, reclaimable}
        reclaimable = size * (份数 - 1)，按可回收空间从大到小排序。
    """
    log = get_logger()
    # 第一阶段：按大小分组
    by_size: dict[int, list[Path]] = {}
    for p in _iter_files(directories, recursive):
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < min_size:
            continue
        by_size.setdefault(size, []).append(p)

    # 第二阶段：同大小组内按 MD5 分组
    groups: list[dict[str, Any]] = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for p in paths:
            try:
                digest = file_md5(p)
            except OSError as e:
                log.warning("读取失败跳过: %s (%s)", p, e)
                continue
            by_hash.setdefault(digest, []).append(str(p))
        for digest, same in by_hash.items():
            if len(same) >= 2:
                groups.append(
                    {
                        "md5": digest,
                        "size": size,
                        "paths": sorted(same),
                        "reclaimable": size * (len(same) - 1),
                    }
                )
    groups.sort(key=lambda g: g["reclaimable"], reverse=True)
    total = sum(g["reclaimable"] for g in groups)
    log.info("重复扫描完成: %d 组，可回收约 %d 字节", len(groups), total)
    return groups


def delete_duplicates(
    group: dict[str, Any],
    keep_index: int = 0,
    dry_run: bool = True,
) -> list[str]:
    """删除一组重复文件中的多余副本（保留 paths[keep_index]）。

    默认 dry_run=True 只返回将删除的路径、不实际删除。
    Returns:
        （将）删除的路径列表。
    """
    log = get_logger()
    paths = list(group["paths"])
    if not 0 <= keep_index < len(paths):
        raise ValueError("keep_index 越界")
    targets = [p for i, p in enumerate(paths) if i != keep_index]
    for p in targets:
        if dry_run:
            log.info("[dry-run] 将删除重复副本: %s", p)
        else:
            os.remove(p)
            log.info("已删除重复副本: %s", p)
    return targets
