"""Smart File Sorter 单元测试。"""

import os
import tempfile
from pathlib import Path

# 将项目根目录加入 sys.path（方便直接运行 pytest）
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_sorter.config import (
    load_config,
    should_skip,
    classify_file,
    DEFAULT_CONFIG,
)
from file_sorter.classifier import scan_directory
from file_sorter.renamer import generate_new_name, resolve_destination
from file_sorter.stats import format_size, compute_stats
from file_sorter.logger import init_logger, get_logger, get_log_file_path


class TestConfig:
    """配置模块测试。"""

    def test_default_config(self):
        """默认配置应包含所有必要字段。"""
        assert "categories" in DEFAULT_CONFIG
        assert len(DEFAULT_CONFIG["categories"]) >= 6
        assert "skip_extensions" in DEFAULT_CONFIG
        assert ".lnk" in DEFAULT_CONFIG["skip_extensions"]

    def test_should_skip_shortcuts(self):
        """应跳过快捷方式。"""
        config = DEFAULT_CONFIG.copy()
        assert should_skip("chrome.lnk", config) is True
        assert should_skip("game.url", config) is True

    def test_should_skip_system_files(self):
        """应跳过系统文件。"""
        config = DEFAULT_CONFIG.copy()
        assert should_skip("desktop.ini", config) is True
        assert should_skip("Thumbs.db", config) is True
        assert should_skip("~$temp.docx", config) is True

    def test_should_not_skip_normal_files(self):
        """不应跳过正常文件。"""
        config = DEFAULT_CONFIG.copy()
        assert should_skip("report.pdf", config) is False
        assert should_skip("photo.png", config) is False
        assert should_skip("main.py", config) is False

    def test_classify_pdf(self):
        """PDF 文件应归类到 PDF文档。"""
        config = DEFAULT_CONFIG.copy()
        assert classify_file("book.pdf", config) == "PDF文档"
        assert classify_file("novel.epub", config) == "PDF文档"

    def test_classify_image(self):
        """图片文件应归类到 图片。"""
        config = DEFAULT_CONFIG.copy()
        assert classify_file("photo.jpg", config) == "图片"
        assert classify_file("screenshot.png", config) == "图片"
        assert classify_file("icon.svg", config) == "图片"

    def test_classify_code(self):
        """代码文件应归类到 代码脚本。"""
        config = DEFAULT_CONFIG.copy()
        assert classify_file("main.py", config) == "代码脚本"
        assert classify_file("index.html", config) == "代码脚本"
        assert classify_file("data.json", config) == "代码脚本"

    def test_classify_unknown(self):
        """未知扩展名应归类到 其他。"""
        config = DEFAULT_CONFIG.copy()
        assert classify_file("setup.exe", config) == "其他"
        assert classify_file("unknown.xyz", config) == "其他"


class TestRenamer:
    """重命名模块测试。"""

    def test_generate_new_name_default(self):
        """默认模板：日期_原文件名。"""
        config = DEFAULT_CONFIG.copy()
        new_name = generate_new_name("report.pdf", config)
        assert new_name.endswith("_report.pdf")
        assert len(new_name) > len("report.pdf")

    def test_resolve_destination_no_conflict(self):
        """无冲突时直接返回路径。"""
        init_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest, meta = resolve_destination(
                "/some/source.pdf", tmpdir, "20260528_file.pdf"
            )
            assert dest == os.path.join(tmpdir, "20260528_file.pdf")
            assert meta["name_conflict"] is False
            assert meta["content_duplicate"] is False

    def test_resolve_destination_name_conflict(self):
        """名称冲突时自动递增后缀。"""
        init_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir, "20260528_file.txt")
            existing.write_text("existing content")
            source = Path(tmpdir, "original.txt")
            source.write_text("different content")
            dest, meta = resolve_destination(
                str(source), tmpdir, "20260528_file.txt",
                dedup_by_content=True,
            )
            assert "(1)" in dest
            assert meta["name_conflict"] is True
            assert meta["content_duplicate"] is False

    def test_resolve_destination_content_duplicate(self):
        """内容相同时标记为重复。"""
        init_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            content = "same content for dedup test"
            existing = Path(tmpdir, "20260528_file.txt")
            existing.write_text(content)
            source = Path(tmpdir, "original.txt")
            source.write_text(content)
            dest, meta = resolve_destination(
                str(source), tmpdir, "20260528_file.txt",
                dedup_by_content=True,
            )
            assert meta["content_duplicate"] is True


class TestLogger:
    """日志模块测试。"""

    def test_init_logger(self):
        """初始化日志系统并写入文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = init_logger(log_dir=tmpdir)
            assert logger is not None
            assert get_logger() is logger
            log_path = get_log_file_path()
            assert log_path is not None
            assert os.path.exists(log_path)

    def test_logger_singleton(self):
        """get_logger 返回同一实例。"""
        log1 = init_logger()
        log2 = get_logger()
        assert log1 is log2


class TestStats:
    """统计模块测试。"""

    def test_format_size(self):
        """文件大小格式化。"""
        assert format_size(0) == "0.0 B"
        assert format_size(500) == "500.0 B"
        assert format_size(1024) == "1.0 KB"
        assert format_size(1048576) == "1.0 MB"
        assert format_size(1073741824) == "1.0 GB"

    def test_compute_stats_empty(self):
        """空结果统计。"""
        scanned = []
        organized = {}
        stats = compute_stats(scanned, organized)
        assert stats["total_scanned"] == 0
        assert stats["total_organized"] == 0
        assert stats["total_duplicates"] == 0

    def test_compute_stats_with_duplicates(self):
        """统计包含去重计数。"""
        scanned = [
            {"path": "/a.txt", "name": "a.txt", "ext": ".txt",
             "size": 100, "category": "办公文档", "skipped": None},
            {"path": "/b.txt", "name": "b.txt", "ext": ".txt",
             "size": 100, "category": "办公文档", "skipped": None},
        ]
        organized = {
            "办公文档": [
                {"old_name": "a.txt", "new_name": "20260528_a.txt",
                 "size": 100, "content_duplicate": True},
                {"old_name": "b.txt", "new_name": "20260528_b.txt",
                 "size": 100, "content_duplicate": False},
            ]
        }
        stats = compute_stats(scanned, organized)
        assert stats["total_organized"] == 2
        assert stats["total_duplicates"] == 1


class TestClassifier:
    """分类扫描集成测试。"""

    def test_scan_empty_directory(self):
        """空目录应返回空列表。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = scan_directory(tmpdir, DEFAULT_CONFIG)
            assert results == []

    def test_scan_with_files(self):
        """扫描包含测试文件的目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件
            Path(tmpdir, "report.pdf").touch()
            Path(tmpdir, "photo.png").touch()
            Path(tmpdir, "script.py").touch()
            Path(tmpdir, "shortcut.lnk").touch()
            Path(tmpdir, "desktop.ini").touch()

            results = scan_directory(tmpdir, DEFAULT_CONFIG)

            # 各文件状态
            by_name = {r["name"]: r for r in results}

            assert by_name["report.pdf"]["category"] == "PDF文档"
            assert by_name["report.pdf"]["skipped"] is None

            assert by_name["photo.png"]["category"] == "图片"
            assert by_name["script.py"]["category"] == "代码脚本"

            assert by_name["shortcut.lnk"]["skipped"] is not None
            assert by_name["desktop.ini"]["skipped"] is not None
