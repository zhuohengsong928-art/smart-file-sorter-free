"""归档器：创建分类文件夹并移动文件。"""

import os
import shutil
from pathlib import Path
from typing import Any

from .renamer import generate_new_name, resolve_destination
from .logger import get_logger


def organize_files(
    file_list: list[dict[str, Any]],
    config: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """执行文件整理：创建分类文件夹、重命名、移动。

    Args:
        file_list: 分类器扫描结果（仅处理 skipped=None 的文件）
        config: 配置字典
        dry_run: 仅预览不实际操作

    Returns:
        { 分类名: [操作记录] }
    """
    log = get_logger()
    output_root = config.get("output_root", "")
    dedup_enabled = config.get("dedup_by_content", True)
    results: dict[str, list[dict[str, Any]]] = {}
    moved_count = 0
    dup_count = 0
    error_count = 0

    log.info("=" * 50)
    log.info("开始文件归档 | dry_run=%s | 内容去重=%s", dry_run, dedup_enabled)
    log.info("=" * 50)

    for idx, file_info in enumerate(file_list):
        if file_info.get("skipped"):
            continue

        category = file_info["category"]
        source_path = file_info["path"]

        # 确定目标目录
        if output_root:
            dest_category_dir = os.path.join(output_root, category)
        else:
            source_parent = os.path.dirname(source_path)
            dest_category_dir = os.path.join(source_parent, category)

        # 生成新文件名
        new_name = generate_new_name(file_info["name"], config, counter=idx)

        try:
            dest_path, meta = resolve_destination(
                source_path, dest_category_dir, new_name,
                dedup_by_content=dedup_enabled,
            )
        except OSError as e:
            log.error(
                "文件处理失败: %s | 原因: %s",
                file_info["name"], e,
            )
            error_count += 1
            continue

        record = {
            "source": source_path,
            "dest": dest_path,
            "category": category,
            "old_name": file_info["name"],
            "new_name": os.path.basename(dest_path),
            "size": file_info["size"],
            "content_duplicate": meta["content_duplicate"],
            "name_conflict": meta["name_conflict"],
        }

        # 内容重复：跳过移动
        if meta["content_duplicate"]:
            if not dry_run:
                log.info(
                    "去重跳过: %s (与 %s 内容相同)",
                    file_info["name"],
                    os.path.basename(dest_path),
                )
            results.setdefault(category, []).append(record)
            dup_count += 1
            continue

        # 执行移动
        if not dry_run:
            try:
                os.makedirs(dest_category_dir, exist_ok=True)
                shutil.move(source_path, dest_path)
                log.info(
                    "移动: %s → [%s]/%s",
                    file_info["name"], category, record["new_name"],
                )
            except OSError as e:
                log.error(
                    "移动失败: %s → %s | 原因: %s",
                    source_path, dest_path, e,
                )
                error_count += 1
                continue

        results.setdefault(category, []).append(record)
        moved_count += 1

    log.info("=" * 50)
    log.info(
        "归档完成: 移动 %d 个 | 去重跳过 %d 个 | 失败 %d 个",
        moved_count, dup_count, error_count,
    )
    log.info("=" * 50)

    return results
