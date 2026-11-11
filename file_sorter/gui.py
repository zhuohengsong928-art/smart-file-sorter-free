"""图形界面（Tkinter）：Smart File Sorter 桌面端。

毕设升级模块（v2.4.0 新增）：把原命令行工具包装为窗口程序——
- 选择一个或多个待整理目录；
- 先「扫描预览」查看每个文件将被分到哪个类别、改成什么名（不移动文件）；
- 确认后「执行整理」，结果自动写入 SQLite 历史库；
- 「历史记录」窗口回溯每次整理的汇总与累计统计；
- 「重复文件」窗口按内容（MD5）列出重复组，可回收空间一目了然，
  删除前有二次确认，且每组必留一份。

启动方式：python -m file_sorter.gui  或  file-sorter-gui
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .classifier import scan_directory
from .config import load_config
from .stats import compute_stats, format_size

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "rules.yaml"


def _load_cfg() -> dict[str, Any]:
    try:
        return load_config(str(_DEFAULT_CONFIG))
    except Exception:
        from .config import DEFAULT_CONFIG

        return dict(DEFAULT_CONFIG)


class SorterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Smart File Sorter — 智能文件分类管理")
        self.geometry("860x540")
        self.config_data = _load_cfg()
        self.directories: list[str] = []
        self._scanned: list[dict[str, Any]] = []
        self._organized: dict[str, list[dict[str, Any]]] = {}

        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)
        ttk.Button(top, text="添加目录", command=self._add_dir).pack(side=tk.LEFT)
        ttk.Button(top, text="移除选中", command=self._remove_dir).pack(side=tk.LEFT, padx=4)
        self.dir_list = tk.Listbox(top, height=3)
        self.dir_list.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        bar = ttk.Frame(self, padding=(8, 0))
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="① 扫描预览", command=self._preview).pack(side=tk.LEFT)
        ttk.Button(bar, text="② 执行整理", command=self._execute).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="重复文件扫描", command=self._dup_window).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="历史记录", command=self._history_window).pack(side=tk.LEFT, padx=4)

        cols = ("name", "category", "new_name", "size", "state")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, text, width in [
            ("name", "原文件名", 240),
            ("category", "分类", 110),
            ("new_name", "整理后文件名", 240),
            ("size", "大小", 90),
            ("state", "状态", 130),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.status = tk.StringVar(value="先添加目录，再点「扫描预览」。")
        ttk.Label(self, textvariable=self.status).pack(fill=tk.X, padx=8, pady=(0, 8))

    # ---------- 目录管理 ----------
    def _add_dir(self) -> None:
        d = filedialog.askdirectory(title="选择待整理的目录")
        if d and d not in self.directories:
            self.directories.append(d)
            self.dir_list.insert(tk.END, d)

    def _remove_dir(self) -> None:
        for i in reversed(self.dir_list.curselection()):
            self.dir_list.delete(i)
            del self.directories[i]

    # ---------- 预览与执行 ----------
    def _scan_all(self) -> list[dict[str, Any]]:
        scanned: list[dict[str, Any]] = []
        for d in self.directories:
            scanned.extend(scan_directory(d, self.config_data))
        return scanned

    def _preview(self) -> None:
        if not self.directories:
            messagebox.showinfo("提示", "请先添加至少一个目录。")
            return
        from .archiver import organize_files

        self._scanned = self._scan_all()
        self._organized = organize_files(self._scanned, self.config_data, dry_run=True)
        self._fill_tree()
        self.status.set(
            f"预览完成：共 {len(self._scanned)} 个文件（未实际移动）。确认无误后点「执行整理」。"
        )

    def _fill_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for category, records in self._organized.items():
            for r in records:
                state = "内容重复·将跳过" if r.get("content_duplicate") else "待移动"
                self.tree.insert(
                    "",
                    tk.END,
                    values=(r["old_name"], category, r["new_name"], format_size(r["size"]), state),
                )
        skipped = [f for f in self._scanned if f.get("skipped")]
        for f in skipped:
            self.tree.insert(
                "", tk.END, values=(f["name"], "—", "—", format_size(f["size"]), "跳过")
            )

    def _execute(self) -> None:
        if not self._scanned:
            messagebox.showinfo("提示", "请先点「扫描预览」。")
            return
        if not messagebox.askyesno("确认", "将按预览结果真实移动文件，确定执行吗？"):
            return
        from .archiver import organize_files

        organized = organize_files(self._scanned, self.config_data, dry_run=False)
        run_id = None
        try:
            from .history import record_run

            run_id = record_run(organized)
        except Exception:
            pass
        stats = compute_stats(self._scanned, organized)
        msg = f"整理完成：共处理 {stats['total_organized']} 个文件。"
        if run_id:
            msg += f"\n已写入历史记录（#{run_id}），可在「历史记录」中回溯。"
        self.status.set(msg)
        messagebox.showinfo("完成", msg)
        self._scanned = []
        self._organized = {}

    # ---------- 历史窗口 ----------
    def _history_window(self) -> None:
        from .history import list_runs, summary_stats

        win = tk.Toplevel(self)
        win.title("整理历史记录")
        win.geometry("640x360")
        cols = ("id", "time", "files", "moved", "dups")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for col, text in [("id", "编号"), ("time", "时间"), ("files", "文件数"), ("moved", "已移动"), ("dups", "去重跳过")]:
            tree.heading(col, text=text)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        try:
            runs = list_runs(limit=50)
            s = summary_stats()
        except Exception as e:
            messagebox.showerror("错误", f"读取历史失败：{e}", parent=win)
            return
        for r in runs:
            tree.insert("", tk.END, values=(r["id"], r["created_at"], r["total_files"], r["moved"], r["duplicates"]))
        ttk.Label(
            win, text=f"累计：运行 {s['runs']} 次，整理 {s['files']} 个文件，共 {format_size(s['bytes'])}。"
        ).pack(padx=8, pady=(0, 8))

    # ---------- 重复文件窗口 ----------
    def _dup_window(self) -> None:
        if not self.directories:
            messagebox.showinfo("提示", "请先添加至少一个目录。")
            return
        win = tk.Toplevel(self)
        win.title("重复文件扫描（按内容 MD5 比对）")
        win.geometry("760x420")
        label = ttk.Label(win, text="扫描中，请稍候…")
        label.pack(padx=8, pady=8)
        tree = ttk.Treeview(win, columns=("path", "size"), show="headings")
        tree.heading("path", text="文件路径（每组第一份为保留项）")
        tree.heading("size", text="单份大小")
        tree.column("path", width=600)
        tree.column("size", width=110)
        tree.pack(fill=tk.BOTH, expand=True, padx=8)

        groups_holder: dict[str, Any] = {}

        def do_scan() -> None:
            from .duplicates import find_duplicates

            groups = find_duplicates(self.directories, recursive=True)
            groups_holder["groups"] = groups

            def render() -> None:
                total = sum(g["reclaimable"] for g in groups)
                label.config(
                    text=f"共 {len(groups)} 组重复文件，可回收约 {format_size(total)}。"
                    "点下方按钮将删除每组除第一份外的副本（不可恢复，请确认）。"
                )
                for gi, g in enumerate(groups):
                    parent = tree.insert(
                        "", tk.END, values=(f"第 {gi + 1} 组 · 共 {len(g['paths'])} 份", format_size(g["size"]))
                    )
                    for p in g["paths"]:
                        tree.insert(parent, tk.END, values=(p, ""))

            win.after(0, render)

        threading.Thread(target=do_scan, daemon=True).start()

        def do_delete() -> None:
            groups = groups_holder.get("groups") or []
            if not groups:
                return
            if not messagebox.askyesno(
                "危险操作确认",
                "将永久删除每组重复文件中除第一份外的所有副本，不可恢复。确定继续吗？",
                parent=win,
            ):
                return
            from .duplicates import delete_duplicates

            removed = 0
            for g in groups:
                removed += len(delete_duplicates(g, keep_index=0, dry_run=False))
            messagebox.showinfo("完成", f"已删除 {removed} 个重复副本。", parent=win)
            win.destroy()

        ttk.Button(win, text="删除多余副本（每组保留第一份）", command=do_delete).pack(pady=8)


def main() -> None:
    app = SorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
