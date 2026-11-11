"""文件分类器：扫描目录、识别类型、过滤无关文件。"""

import os
from pathlib import Path
from typing import Any

from .config import should_skip, classify_file
from .logger import get_logger


def scan_directory(
    source_dir: str | Path,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """扫描目录，返回待处理文件列表。

    每个文件记录包含：
        - path: 完整路径
        - name: 文件名
        - ext: 扩展名（小写）
        - size: 文件大小（字节）
        - category: 分类名称
        - skipped: 是否被跳过及原因
    """
    log = get_logger()
    source_dir = Path(source_dir)
    results: list[dict[str, Any]] = []

    if not source_dir.exists():
        log.warning("目录不存在: %s", source_dir)
        return results

    log.info("开始扫描: %s", source_dir)

    # 遍历模式
    if config.get("recursive", False):
        files = source_dir.rglob("*")
        log.debug("扫描模式: 递归")
    else:
        files = source_dir.glob("*")
        log.debug("扫描模式: 顶层")

    scan_count = 0
    skip_count = 0

    for file_path in files:
        if not file_path.is_file():
            continue

        name = file_path.name
        ext = file_path.suffix.lower()

        try:
            size = file_path.stat().st_size
        except OSError as e:
            log.error("无法读取文件信息: %s (%s)", file_path, e)
            continue

        # 系统隐藏属性检查
        try:
            attrs = file_path.stat().st_file_attributes  # Windows
            if attrs & 0x2 or attrs & 0x4:  # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
                results.append({
                    "path": str(file_path), "name": name, "ext": ext,
                    "size": size, "category": None, "skipped": "隐藏/系统文件",
                    "detected_format": None, "corrected": False,
                })
                skip_count += 1
                log.debug("跳过(隐藏/系统): %s", name)
                continue
        except AttributeError:
            # Linux/macOS：检查以 . 开头的隐藏文件
            if name.startswith(".") and not config.get("include_hidden", False):
                results.append({
                    "path": str(file_path), "name": name, "ext": ext,
                    "size": size, "category": None, "skipped": "隐藏文件",
                    "detected_format": None, "corrected": False,
                })
                skip_count += 1
                log.debug("跳过(隐藏): %s", name)
                continue

        # 配置规则跳过
        if should_skip(name, config):
            results.append({
                "path": str(file_path), "name": name, "ext": ext,
                "size": size, "category": None, "skipped": "规则过滤",
                "detected_format": None, "corrected": False,
            })
            skip_count += 1
            log.debug("跳过(规则): %s", name)
            continue

        # 分类：先按扩展名，再用文件头魔数校验纠正
        category = classify_file(name, config)
        detected_format = None
        corrected = False
        if config.get("verify_content", True):
            from .magic import verify_category

            category, detected_format, corrected = verify_category(file_path, category)
            if corrected:
                log.info(
                    "内容校验纠正: %s 扩展名类别→内容类别 [%s]（真实格式 %s）",
                    name, category, detected_format,
                )
        results.append({
            "path": str(file_path), "name": name, "ext": ext,
            "size": size, "category": category, "skipped": None,
            "detected_format": detected_format, "corrected": corrected,
        })
        scan_count += 1
        log.debug("分类: [%s] %s (%s)", category, name, _fmt_size(size))

    log.info(
        "扫描完成: %s → 待处理 %d 个, 跳过 %d 个",
        source_dir.name, scan_count, skip_count,
    )

    return results


def _fmt_size(size_bytes: int) -> str:
    """精简文件大小格式（日志用）。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes}{unit}"
        size_bytes //= 1024
    return f"{size_bytes}TB"
