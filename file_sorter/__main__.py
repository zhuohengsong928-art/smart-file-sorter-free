"""Smart File Sorter — 命令行入口。"""

import argparse
import sys
import time
from pathlib import Path

from .config import load_config
from .classifier import scan_directory
from .archiver import organize_files
from .stats import compute_stats
from .reporter import (
    print_summary,
    print_dry_run_preview,
    export_json,
    supports_color,
)
from .logger import init_logger, get_logger, get_log_file_path


def main() -> None:
    """主入口。"""
    # 启用 Windows 终端 ANSI 支持
    supports_color()

    parser = argparse.ArgumentParser(
        prog="file-sorter",
        description="🦞 Smart File Sorter — 智能文件分拣管理系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  file-sorter ~/Desktop ~/Downloads              # 整理桌面和下载文件夹
  file-sorter . --dry-run                        # 预览当前目录的整理效果
  file-sorter ~/Downloads -r                     # 递归整理下载文件夹
  file-sorter ~/Desktop -c my_rules.yaml         # 使用自定义规则
  file-sorter ~/Desktop --json report.json       # 导出 JSON 报告
  file-sorter ~/Desktop --log-dir ./logs -v      # 详细日志输出
        """,
    )

    parser.add_argument(
        "directories",
        nargs="+",
        help="要扫描的目录路径（可指定多个）",
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="自定义规则配置文件路径（YAML，默认使用内置规则）",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="统一输出根目录（所有分类文件夹创建在此目录下）",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="递归扫描子目录",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式：仅预览，不实际移动文件",
    )
    parser.add_argument(
        "--json",
        default=None,
        metavar="PATH",
        help="导出 JSON 统计报告到指定路径",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        metavar="PATH",
        help="日志文件输出目录（默认: ./logs）",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细模式：控制台也输出 DEBUG 级别日志",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="查看最近的整理历史记录（来自 SQLite 历史库）后退出",
    )
    parser.add_argument(
        "--dup-scan",
        action="store_true",
        help="重复文件扫描模式：只报告内容重复的文件组，不做整理",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version="Smart File Sorter v2.4.0",
    )

    args = parser.parse_args()

    # === 初始化日志 ===
    log = init_logger(log_dir=args.log_dir, verbose=args.verbose)
    log.info("🦞 Smart File Sorter v2.4.0 启动")
    log.info("日志文件: %s", get_log_file_path())

    # === 历史查看模式 ===
    if args.history:
        from .history import list_runs, summary_stats

        runs = list_runs(limit=10)
        if not runs:
            print("暂无整理历史。先真实执行一次整理（非 --dry-run）就会产生记录。")
            sys.exit(0)
        print("最近的整理历史：")
        for r in runs:
            print(
                f"  #{r['id']} {r['created_at']} | 文件 {r['total_files']}"
                f"（移动 {r['moved']}，去重跳过 {r['duplicates']}）"
            )
        s = summary_stats()
        print(f"累计：运行 {s['runs']} 次，整理 {s['files']} 个文件。")
        sys.exit(0)

    # === 重复文件扫描模式 ===
    if args.dup_scan:
        from .duplicates import find_duplicates
        from .stats import format_size

        groups = find_duplicates(args.directories, recursive=True)
        if not groups:
            print("未发现内容重复的文件。")
            sys.exit(0)
        total = sum(g["reclaimable"] for g in groups)
        print(f"发现 {len(groups)} 组重复文件，可回收约 {format_size(total)}：")
        for g in groups:
            print(f"\n[{format_size(g['size'])} × {len(g['paths'])} 份]")
            for p in g["paths"]:
                print(f"  {p}")
        sys.exit(0)

    t_start = time.perf_counter()

    # 加载配置
    config_path = args.config or str(
        Path(__file__).resolve().parent.parent / "config" / "rules.yaml"
    )
    log.debug("加载配置: %s", config_path)
    config = load_config(config_path)

    # 命令行参数覆盖
    if args.recursive:
        config["recursive"] = True
    if args.output:
        config["output_root"] = args.output

    # 扫描
    all_scanned = []
    for directory in args.directories:
        resolved = str(Path(directory).resolve())
        files = scan_directory(resolved, config)
        all_scanned.extend(files)

    if not all_scanned:
        log.warning("未扫描到任何文件，退出。")
        print("未扫描到任何文件。")
        sys.exit(0)

    # 试运行模式
    if args.dry_run:
        log.info("进入试运行模式（--dry-run）")
        organized = organize_files(all_scanned, config, dry_run=True)
        print_dry_run_preview(organized)
        log.info("试运行结束（无实际文件移动）")
        sys.exit(0)

    # 执行整理
    organized = organize_files(all_scanned, config, dry_run=False)

    # 写入历史库（失败不影响整理结果本身）
    try:
        from .history import record_run

        record_run(organized)
    except Exception as e:  # noqa: BLE001 - 历史记录是附加功能
        log.warning("历史记录写入失败: %s", e)

    # 统计
    stats = compute_stats(all_scanned, organized)
    t_elapsed = time.perf_counter() - t_start

    # 输出报告
    print_summary(stats)

    # JSON 导出
    if args.json:
        export_json(stats, args.json)

    # 结束日志
    if stats["total_organized"] == 0:
        msg = "所有文件已处于整理状态，无需操作。"
        print(f"\n{msg}")
        log.info(msg)
    else:
        msg = f"整理完成！共处理 {stats['total_organized']} 个文件，耗时 {t_elapsed:.2f}s"
        print(f"\n✅ {msg}")
        log.info(msg)

    log.info(
        "运行统计: 扫描=%d 整理=%d 跳过=%d 去重=%d 耗时=%.2fs",
        stats["total_scanned"],
        stats["total_organized"],
        stats["total_skipped"],
        stats.get("total_duplicates", 0),
        t_elapsed,
    )
    log.info("日志文件: %s", get_log_file_path())


if __name__ == "__main__":
    main()
