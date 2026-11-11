"""v2.4.0 升级模块测试：历史记录（SQLite）与重复文件扫描。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_sorter.history import list_actions, list_runs, record_run, summary_stats
from file_sorter.duplicates import delete_duplicates, find_duplicates
from file_sorter.magic import sniff_format, verify_category
from file_sorter.classifier import scan_directory
from file_sorter.config import DEFAULT_CONFIG
from file_sorter.archiver import organize_files
from file_sorter.undo import undo_run


def _fake_organized():
    return {
        "PDF文档": [
            {
                "source": "/tmp/a.pdf",
                "dest": "/tmp/PDF文档/20260101_a.pdf",
                "category": "PDF文档",
                "old_name": "a.pdf",
                "new_name": "20260101_a.pdf",
                "size": 100,
                "content_duplicate": False,
                "name_conflict": False,
            },
            {
                "source": "/tmp/b.pdf",
                "dest": "/tmp/PDF文档/b.pdf",
                "category": "PDF文档",
                "old_name": "b.pdf",
                "new_name": "b.pdf",
                "size": 50,
                "content_duplicate": True,
                "name_conflict": True,
            },
        ]
    }


class TestHistory:
    def test_record_and_query(self, tmp_path):
        db = tmp_path / "h.db"
        run_id = record_run(_fake_organized(), db_path=db)
        assert run_id == 1

        runs = list_runs(db_path=db)
        assert len(runs) == 1
        assert runs[0]["total_files"] == 2
        assert runs[0]["moved"] == 1
        assert runs[0]["duplicates"] == 1

        actions = list_actions(run_id, db_path=db)
        assert len(actions) == 2
        assert {a["action"] for a in actions} == {"moved", "duplicate_skipped"}

        stats = summary_stats(db_path=db)
        assert stats == {"runs": 1, "files": 2, "bytes": 150}


class TestDuplicates:
    def _make(self, root: Path):
        (root / "x").mkdir(parents=True)
        (root / "y").mkdir(parents=True)
        (root / "x" / "a.txt").write_bytes(b"hello world")
        (root / "y" / "b.txt").write_bytes(b"hello world")
        (root / "y" / "c.txt").write_bytes(b"different!")

    def test_find(self, tmp_path):
        self._make(tmp_path)
        groups = find_duplicates([tmp_path])
        assert len(groups) == 1
        g = groups[0]
        assert len(g["paths"]) == 2
        assert g["size"] == len(b"hello world")
        assert g["reclaimable"] == g["size"]

    def test_delete_dry_run_keeps_files(self, tmp_path):
        self._make(tmp_path)
        g = find_duplicates([tmp_path])[0]
        targets = delete_duplicates(g, dry_run=True)
        assert len(targets) == 1
        assert all(Path(p).exists() for p in g["paths"])

    def test_delete_real(self, tmp_path):
        self._make(tmp_path)
        g = find_duplicates([tmp_path])[0]
        targets = delete_duplicates(g, dry_run=False)
        assert len(targets) == 1
        assert not Path(targets[0]).exists()
        assert Path(g["paths"][0]).exists()


class TestMagic:
    """文件头魔数校验：改名欺骗要被纠正，纯文本不强判。"""

    def test_fake_pdf_is_corrected(self, tmp_path):
        p = tmp_path / "photo.pdf"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        assert sniff_format(p) == ("PNG", "图片")
        final, fmt, corrected = verify_category(p, "PDF文档")
        assert (final, fmt, corrected) == ("图片", "PNG", True)

    def test_real_pdf_passes(self, tmp_path):
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"%PDF-1.7\n" + b"\x00" * 16)
        final, fmt, corrected = verify_category(p, "PDF文档")
        assert (final, fmt, corrected) == ("PDF文档", "PDF", False)

    def test_docx_zip_container_fine(self, tmp_path):
        p = tmp_path / "a.docx"
        p.write_bytes(b"PK\x03\x04" + b"\x00" * 16)
        final, fmt, corrected = verify_category(p, "办公文档")
        assert fmt == "DOCX" and corrected is False

    def test_plain_text_not_forced(self, tmp_path):
        p = tmp_path / "n.txt"
        p.write_text("just some plain text", encoding="utf-8")
        final, fmt, corrected = verify_category(p, "办公文档")
        assert (final, fmt, corrected) == ("办公文档", None, False)

    def test_scan_corrects_category(self, tmp_path):
        (tmp_path / "fake.pdf").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)
        scanned = scan_directory(tmp_path, dict(DEFAULT_CONFIG))
        item = next(f for f in scanned if f["name"] == "fake.pdf")
        assert item["category"] == "图片"
        assert item["corrected"] is True
        assert item["detected_format"] == "JPEG"


class TestUndo:
    """整理 → 历史 → 撤销，全链路回到原样。"""

    def test_undo_restores_files(self, tmp_path):
        db = tmp_path / "h.db"
        src = tmp_path / "messy"
        src.mkdir()
        (src / "a.pdf").write_bytes(b"%PDF-1.4 data")
        (src / "b.txt").write_text("hello", encoding="utf-8")

        config = dict(DEFAULT_CONFIG)
        scanned = scan_directory(src, config)
        organized = organize_files(scanned, config, dry_run=False)
        record_run(organized, db_path=db)
        assert not (src / "a.pdf").exists()  # 已被整理走

        result = undo_run(db_path=db)
        assert result["run_id"] == 1
        assert len(result["restored"]) == 2
        assert (src / "a.pdf").exists() and (src / "b.txt").exists()

        # 重复撤销必须被拒绝：显式指定同一 run，或已无可撤销运行
        try:
            undo_run(run_id=1, db_path=db)
            raise AssertionError("重复撤销应抛 ValueError")
        except ValueError:
            pass
        assert undo_run(db_path=db)["run_id"] is None
