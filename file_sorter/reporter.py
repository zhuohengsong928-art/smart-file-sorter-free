"""报告生成器：富文本终端输出 + JSON 导出。"""

import json
import os
import sys
from typing import Any


# ANSI 颜色码
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"


def supports_color() -> bool:
    """检测终端是否支持颜色。"""
    if os.name == "nt":
        # 强制 stdout 使用 UTF-8 编码
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            mode = ctypes.c_ulong()
            handle = kernel32.GetStdHandle(-11)
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x4)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    """条件着色。"""
    if supports_color():
        return f"{code}{text}{C_RESET}"
    return text


def print_header(title: str) -> None:
    """打印区段标题。"""
    bar = "=" * 58
    print(f"\n{_c(C_BLUE + C_BOLD, bar)}")
    print(f"{_c(C_BOLD, '  ' + title)}")
    print(f"{_c(C_BLUE + C_BOLD, bar)}\n")


def print_summary(stats: dict[str, Any]) -> None:
    """打印整理汇总。"""
    print_header("📊 整理汇总")

    items = [
        ("扫描文件", str(stats["total_scanned"])),
        ("已整理", _c(C_GREEN, str(stats["total_organized"]))),
        ("去重跳过", _c(C_CYAN, str(stats.get("total_duplicates", 0)))),
        ("已跳过", _c(C_DIM, str(stats["total_skipped"]))),
        ("处理总量", _c(C_YELLOW, stats["total_size"])),
    ]
    for label, value in items:
        print(f"  {label:　<8}  {value}")

    if not stats["categories"]:
        print(f"\n  {_c(C_DIM, '（无文件需要整理）')}")
        return

    print(f"\n{_c(C_BOLD, '  📂 分类明细：')}\n")

    # 按文件数量排序
    sorted_cats = sorted(
        stats["categories"].items(),
        key=lambda x: x[1]["count"],
        reverse=True,
    )

    for cat, info in sorted_cats:
        icon = _category_icon(cat)
        count = info["count"]
        size = info["size"]
        print(f"  {icon} {_c(C_BOLD, cat):　<10} {count:>3} 个  │  {size}")

        # 文件列表（最多展示 5 个）
        files = info["files"]
        shown = files[:5]
        for f in shown:
            print(f"      {_c(C_DIM, '└ ' + f)}")
        if len(files) > 5:
            print(f"      {_c(C_DIM, f'└ ... 及其他 {len(files) - 5} 个文件')}")

    # 跳过的文件
    if stats["skipped"]:
        print(f"\n{_c(C_BOLD, '  ⏭️  已跳过：')}\n")
        for s in stats["skipped"][:10]:
            print(f"      {_c(C_DIM, s['name'] + '  (' + s['reason'] + ')')}")
        if len(stats["skipped"]) > 10:
            print(f"      {_c(C_DIM, f'... 及其他 {len(stats["skipped"]) - 10} 个文件')}")


def print_dry_run_preview(organized: dict[str, list[dict[str, Any]]]) -> None:
    """打印试运行预览。"""
    print_header("🔍 试运行预览（--dry-run）")

    total = 0
    for cat, files in organized.items():
        icon = _category_icon(cat)
        print(f"\n  {icon} {_c(C_BOLD, cat)} ({len(files)} 个文件)")
        for f in files:
            print(f"      {_c(C_YELLOW, f['old_name'])}")
            print(f"      {_c(C_DIM, '→ ' + f['new_name'])}")
            total += 1

    if total == 0:
        print(f"\n  {_c(C_DIM, '（无文件需要整理）')}")

    print(f"\n  {_c(C_BOLD, f'共 {total} 个文件将被整理')}")


def export_json(stats: dict[str, Any], path: str) -> None:
    """导出统计报告为 JSON。"""
    # 清理不可序列化的内容
    export = {
        "total_scanned": stats["total_scanned"],
        "total_skipped": stats["total_skipped"],
        "total_organized": stats["total_organized"],
        "total_duplicates": stats.get("total_duplicates", 0),
        "total_size": stats["total_size"],
        "categories": {
            cat: {"count": info["count"], "size": info["size"]}
            for cat, info in stats["categories"].items()
        },
        "skipped_count": len(stats["skipped"]),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 报告已导出: {path}")


def _category_icon(cat: str) -> str:
    """返回分类对应的 emoji 图标。"""
    icons = {
        "PDF文档": "📑",
        "图片": "🖼️",
        "代码脚本": "💻",
        "办公文档": "📄",
        "压缩包": "📦",
        "音视频": "🎬",
        "其他": "📁",
    }
    return icons.get(cat, "📁")
