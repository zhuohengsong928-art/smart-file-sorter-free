"""v2.4.0 升级模块测试：历史记录（SQLite）与重复文件扫描。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_sorter.history import list_actions, list_runs, record_run, summary_stats
from file_sorter.duplicates import delete_duplicates, find_duplicates


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
