"""统计模块：收集和展示文件整理统计数据。"""

from typing import Any


def format_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读字符串。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def compute_stats(
    scanned: list[dict[str, Any]],
    organized: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """计算整理统计数据。

    Returns:
        {
            "total_scanned": int,       # 扫描到的文件总数
            "total_skipped": int,       # 跳过的文件数
            "total_organized": int,     # 实际移动的文件数
            "total_size": str,          # 处理的总大小
            "categories": {             # 每分类统计
                "分类名": {
                    "count": int,
                    "size": str,
                    "files": [文件名列表]
                }
            },
            "skipped": [跳过记录]
        }
    """
    total_scanned = len(scanned)
    skipped = [f for f in scanned if f.get("skipped")]
    total_skipped = len(skipped)

    # 统计去重数量
    total_duplicates = 0
    for files in organized.values():
        total_duplicates += sum(1 for f in files if f.get("content_duplicate"))

    # 实际整理 = 移动 + 去重跳过（均为操作覆盖）
    total_organized = sum(len(v) for v in organized.values())

    total_size = sum(
        f["size"] for files in organized.values() for f in files
    )

    categories = {}
    for cat, files in organized.items():
        cat_size = sum(f["size"] for f in files)
        categories[cat] = {
            "count": len(files),
            "size": format_size(cat_size),
            "size_bytes": cat_size,
            "files": [f["new_name"] for f in files],
        }

    return {
        "total_scanned": total_scanned,
        "total_skipped": total_skipped,
        "total_organized": total_organized,
        "total_duplicates": total_duplicates,
        "total_size": format_size(total_size),
        "total_size_bytes": total_size,
        "categories": categories,
        "skipped": [{"name": f["name"], "reason": f["skipped"]} for f in skipped],
    }
