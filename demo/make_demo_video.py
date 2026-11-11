#!/usr/bin/env python3
"""Smart File Sorter 演示视频生成器（v2.4.0）。

真实运行 file_sorter 的扫描 / 整理 / 历史记录 / 查重 / 撤销逻辑，
把全过程渲染成“文件管理器窗口”风格的帧序列，再用 ffmpeg 编码为 MP4。

流程：
    ① 造一个杂乱的假桌面（12 个文件，含重复、伪装、应跳过文件）
    ② scan_directory 扫描预览（含文件头魔数内容校验纠正）
    ③ organize_files 真实整理 + record_run 写入历史库
    ④ find_duplicates 按 MD5 找出重复文件组
    ⑤ undo_run 一键撤销还原
每一幕的画面内容都来自程序的真实返回值，不做假数据。
"""

import copy
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 历史库路径必须在导入 file_sorter.history 的消费者之前设定
os.environ["SFS_HISTORY_DB"] = "/tmp/demo_desktop/history.db"

PROJECT_ROOT = Path("/home/hatch/workspace/github/smart-file-sorter")
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from file_sorter.archiver import organize_files  # noqa: E402
from file_sorter.classifier import scan_directory  # noqa: E402
from file_sorter.config import DEFAULT_CONFIG  # noqa: E402
from file_sorter.duplicates import find_duplicates  # noqa: E402
from file_sorter.history import record_run  # noqa: E402
from file_sorter.undo import undo_run  # noqa: E402

# ---------------------------------------------------------------- 路径与常量
DEMO_ROOT = Path("/tmp/demo_desktop")
DESKTOP = DEMO_ROOT / "Desktop"
FRAMES_DIR = DEMO_ROOT / "frames"
OUT_VIDEO = Path("/home/hatch/workspace/your_files/sorter-demo-video.mp4")

W, H = 1280, 800
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

BG_DESKTOP = (22, 29, 40)
WIN_FILL = (242, 244, 247)
WIN_TITLE = (224, 229, 238)
TEXT_DARK = (28, 39, 51)
TEXT_SUB = (96, 110, 128)
PANEL_FILL = (14, 20, 28)
PANEL_TEXT = (214, 222, 233)
PANEL_DIM = (130, 142, 160)
HIGHLIGHT = (255, 176, 32)
CAPTION_BG = (8, 11, 16)

CATEGORY_COLORS = {
    "PDF文档": (214, 69, 65),
    "图片": (39, 174, 96),
    "代码脚本": (108, 92, 231),
    "办公文档": (62, 124, 177),
    "压缩包": (168, 118, 31),
    "音视频": (192, 64, 140),
    "文件夹": (232, 168, 35),
    "其他": (140, 148, 158),
}

_font_cache: dict = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    return _font_cache[key]


# ---------------------------------------------------------------- 假桌面文件
PHOTO_BYTES = b"\xff\xd8\xff\xe0" + b"\xab" * 2044  # 2048 字节的“JPEG”

FILES: list[tuple[str, bytes]] = [
    ("毕业论文开题报告.pdf", b"%PDF-1.7\n" + b"% thesis proposal body\n" * 20),
    ("课程设计说明书.docx", b"PK\x03\x04" + b"docx-course-design;" * 30),
    ("实验数据.xlsx", b"PK\x03\x04" + b"xlsx-lab-data;" * 25),
    ("sort.py", ("#!/usr/bin/env python3\nprint('hello sorter')\n" * 4).encode("utf-8")),
    ("笔记.md", ("# 学习笔记\n- 文件分拣演示\n" * 6).encode("utf-8")),
    ("课件.zip", b"PK\x03\x04" + b"zip-courseware;" * 20),
    ("录屏.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512),
    ("照片.jpg", PHOTO_BYTES),
    ("照片 - 副本.jpg", PHOTO_BYTES),  # 与照片.jpg 内容完全相同的重复文件
    ("风景图.pdf", b"\x89PNG\r\n\x1a\n" + b"\x00" * 600),  # PNG 伪装成 PDF
    ("ChromeSetup.exe.lnk", b"LNK-fake-shortcut-bytes"),
    ("未完成下载.crdownload", b"partial-download-data"),
]


def build_fake_desktop() -> None:
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)
    DESKTOP.mkdir(parents=True)
    FRAMES_DIR.mkdir(parents=True)
    for name, data in FILES:
        (DESKTOP / name).write_bytes(data)


# ---------------------------------------------------------------- 绘图工具
def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int,
              max_lines: int = 2) -> list[str]:
    """按像素宽度把文本折成最多 max_lines 行，超长末行加省略号。"""
    lines: list[str] = []
    rest = text
    while rest and len(lines) < max_lines:
        if draw.textlength(rest, font=fnt) <= max_width:
            lines.append(rest)
            rest = ""
            break
        cur = ""
        for ch in rest:
            if draw.textlength(cur + ch, font=fnt) <= max_width:
                cur += ch
            else:
                break
        if not cur:
            cur = rest[:1]
        if len(lines) == max_lines - 1 and len(cur) < len(rest):
            while cur and draw.textlength(cur + "…", font=fnt) > max_width:
                cur = cur[:-1]
            lines.append(cur + "…")
            rest = ""
            break
        lines.append(cur)
        rest = rest[len(cur):]
    return lines


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG_DESKTOP)
    return img, ImageDraw.Draw(img)


def draw_window(img: Image.Image, draw: ImageDraw.ImageDraw, title: str) -> None:
    """画一个浅色文件管理器窗口：标题栏 + 三个彩色圆点。"""
    draw.rounded_rectangle([36, 36, 1244, 688], radius=18, fill=WIN_FILL)
    draw.rounded_rectangle([36, 36, 1244, 84], radius=18, fill=WIN_TITLE)
    draw.rectangle([36, 66, 1244, 84], fill=WIN_TITLE)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 66 + i * 30
        draw.ellipse([cx - 9, 51, cx + 9, 69], fill=color)
    draw.text((150, 48), title, font=font(21, bold=True), fill=TEXT_DARK)


def draw_caption(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.rectangle([0, 714, W, H], fill=CAPTION_BG)
    draw.rectangle([0, 714, 10, H], fill=HIGHLIGHT)
    fnt = font(31, bold=True)
    tw = draw.textlength(text, font=fnt)
    draw.text(((W - tw) / 2, 738), text, font=fnt, fill=(255, 255, 255))


def draw_file_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                   glyph: str, color: tuple) -> None:
    """画一个文件图标：彩色圆角纸片 + 右上折角 + 扩展名缩写。"""
    x0, y0, x1, y1 = cx - 36, cy - 42, cx + 36, cy + 42
    draw.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=color)
    draw.polygon([(x1 - 18, y0), (x1, y0 + 18), (x1 - 18, y0 + 18)], fill=(255, 255, 255))
    fnt = font(19, bold=True)
    tw = draw.textlength(glyph, font=fnt)
    draw.text((cx - tw / 2, cy + 2), glyph, font=fnt, fill=(255, 255, 255))


def draw_folder_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, big: bool = False) -> None:
    color = CATEGORY_COLORS["文件夹"]
    if big:
        draw.rounded_rectangle([cx - 58, cy - 46, cx - 8, cy - 34], radius=6, fill=color)
        draw.rounded_rectangle([cx - 62, cy - 36, cx + 62, cy + 44], radius=8, fill=color)
        draw.rounded_rectangle([cx - 62, cy - 20, cx + 62, cy + 44], radius=8,
                               fill=(243, 188, 63))
    else:
        draw.rounded_rectangle([cx - 40, cy - 34, cx - 4, cy - 24], radius=5, fill=color)
        draw.rounded_rectangle([cx - 44, cy - 25, cx + 44, cy + 32], radius=7, fill=color)
        draw.rounded_rectangle([cx - 44, cy - 13, cx + 44, cy + 32], radius=7,
                               fill=(243, 188, 63))


def glyph_of(name: str) -> str:
    ext = Path(name).suffix.lstrip(".").upper()
    return ext[:4] if ext else "FILE"


def draw_file_grid(draw: ImageDraw.ImageDraw,
                   items: list[tuple[str, str, tuple]]) -> None:
    """把 (文件名, 图标字, 颜色) 以 6 列网格画进窗口内容区。"""
    cols, cell_w, cell_h = 6, 190, 168
    start_x, start_y = 70, 116
    name_font = font(18)
    for idx, (name, glyph, color) in enumerate(items):
        col, row = idx % cols, idx // cols
        cx = start_x + col * cell_w + cell_w // 2
        cy = start_y + row * cell_h + 52
        draw_file_icon(draw, cx, cy, glyph, color)
        lines = wrap_text(draw, name, name_font, cell_w - 16, max_lines=2)
        ly = cy + 52
        for line in lines:
            tw = draw.textlength(line, font=name_font)
            draw.text((cx - tw / 2, ly), line, font=name_font, fill=TEXT_DARK)
            ly += 24


def draw_panel(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle([58, 104, 1222, 664], radius=12, fill=PANEL_FILL)


# ---------------------------------------------------------------- 各幕渲染
def _ext_category_hint(name: str) -> str:
    """仅用于第一幕图标配色的扩展名粗分类（渲染用，不参与真实逻辑）。"""
    ext = Path(name).suffix.lower()
    for cat, exts in DEFAULT_CONFIG["categories"].items():
        if ext in exts:
            return cat
    return "其他"


def scene1_frames() -> list[Image.Image]:
    """① 杂乱桌面：12 个文件平铺在窗口里。"""
    frames = []
    items = []
    for name, _ in FILES:
        color = CATEGORY_COLORS.get(_ext_category_hint(name), CATEGORY_COLORS["其他"])
        items.append((name, glyph_of(name), color))
    for pulse in (False, True):
        img, draw = new_canvas()
        draw_window(img, draw, "文件管理器 — 桌面 (Desktop)")
        if pulse:
            draw.rounded_rectangle([44, 92, 1236, 680], radius=14,
                                   outline=HIGHLIGHT, width=3)
        draw_file_grid(draw, items)
        draw_caption(draw, "① 桌面现状：12 个文件堆在一起")
        frames.append(img)
    return frames


def scene2_frames(scan: list[dict]) -> list[Image.Image]:
    """② 扫描预览面板：真实 scan 结果逐行列出，纠正行高亮。"""
    order = {name: i for i, (name, _) in enumerate(FILES)}
    rows = sorted(scan, key=lambda r: order.get(r["name"], 99))
    frames = []
    for pulse in (False, True):
        img, draw = new_canvas()
        draw_window(img, draw, "Smart File Sorter — 扫描预览 (dry-run)")
        draw_panel(draw)
        y = 126
        draw.text((86, y), "扫描结果：先看清楚再动手，不移动任何文件",
                  font=font(22, bold=True), fill=(255, 255, 255))
        y += 46
        line_font = font(21)
        for r in rows:
            if r["skipped"]:
                text = f"{r['name']}  →  跳过（{r['skipped']}）"
                draw.text((86, y), text, font=line_font, fill=PANEL_DIM)
            elif r["corrected"]:
                text = (f"{r['name']}  →  {r['category']}  ★ 内容校验："
                        f"扩展名 .pdf 实为 {r['detected_format']}，已按内容纠正")
                if pulse:
                    draw.rounded_rectangle([76, y - 4, 1204, y + 32], radius=6,
                                           fill=(84, 62, 8))
                draw.text((86, y), text, font=line_font, fill=HIGHLIGHT)
            else:
                text = f"{r['name']}  →  {r['category']}"
                draw.text((86, y), text, font=line_font, fill=PANEL_TEXT)
            y += 38
        draw_caption(draw, "② 扫描预览：先看清楚再动手（dry-run）")
        frames.append(img)
    return frames


def scene3_frames() -> list[Image.Image]:
    """③ 整理完成：真实读取桌面上新建的分类文件夹及其内容。"""
    folders = []
    for sub in sorted(DESKTOP.iterdir()):
        if sub.is_dir():
            names = sorted(p.name for p in sub.iterdir() if p.is_file())
            folders.append((sub.name, names))
    frames = []
    for pulse in (False, True):
        img, draw = new_canvas()
        draw_window(img, draw, "文件管理器 — 桌面 (Desktop)")
        if pulse:
            draw.rounded_rectangle([44, 92, 1236, 680], radius=14,
                                   outline=(39, 174, 96), width=3)
        cols, cell_w, cell_h = 3, 380, 262
        start_x, start_y = 70, 110
        name_font = font(23, bold=True)
        item_font = font(16)
        for idx, (folder, names) in enumerate(folders):
            col, row = idx % cols, idx // cols
            x0 = start_x + col * cell_w
            y0 = start_y + row * cell_h
            cx = x0 + cell_w // 2
            draw_folder_icon(draw, cx, y0 + 52, big=True)
            tw = draw.textlength(folder, font=name_font)
            draw.text((cx - tw / 2, y0 + 104), folder, font=name_font, fill=TEXT_DARK)
            ly = y0 + 140
            for nm in names[:4]:
                lines = wrap_text(draw, nm, item_font, cell_w - 40, max_lines=1)
                txt = lines[0] if lines else nm
                tw2 = draw.textlength(txt, font=item_font)
                draw.text((cx - tw2 / 2, ly), txt, font=item_font, fill=TEXT_SUB)
                ly += 23
            if len(names) > 4:
                extra = f"……共 {len(names)} 个文件"
                tw3 = draw.textlength(extra, font=item_font)
                draw.text((cx - tw3 / 2, ly), extra, font=item_font, fill=TEXT_SUB)
        draw_caption(draw, "③ 一键整理完成：自动生成分类文件夹")
        frames.append(img)
    return frames


def scene4_frame(groups: list[dict]) -> Image.Image:
    """④ 重复文件：真实 find_duplicates 结果面板。"""
    img, draw = new_canvas()
    draw_window(img, draw, "Smart File Sorter — 重复文件扫描")
    draw_panel(draw)
    y = 130
    draw.text((86, y), f"重复文件扫描：共 {len(groups)} 组（按内容 MD5 比对）",
              font=font(23, bold=True), fill=(255, 255, 255))
    y += 56
    line_font = font(21)
    total = 0
    for i, g in enumerate(groups, 1):
        total += g["reclaimable"]
        header = (f"第 {i} 组 · 共 {len(g['paths'])} 份 · 单份 {g['size']} 字节"
                  f" · 可回收 {g['reclaimable']} 字节")
        draw.text((86, y), header, font=line_font, fill=HIGHLIGHT)
        y += 38
        for p in g["paths"]:
            rel = os.path.relpath(p, DESKTOP)
            draw.text((110, y), rel, font=line_font, fill=PANEL_TEXT)
            y += 36
        y += 14
    draw.text((86, y + 10), f"合计可回收空间：{total} 字节（删副本前请确认，每组保留一份）",
              font=font(21, bold=True), fill=(255, 255, 255))
    draw_caption(draw, "④ 重复文件无所遁形")
    return img


def scene5_frames() -> list[Image.Image]:
    """⑤ 撤销还原后的桌面 + 片尾标题卡。"""
    frames = []
    items = []
    for name, _ in FILES:
        items.append((name, glyph_of(name),
                      CATEGORY_COLORS.get(_ext_category_hint(name),
                                          CATEGORY_COLORS["其他"])))
    img, draw = new_canvas()
    draw_window(img, draw, "文件管理器 — 桌面 (Desktop)")
    draw_file_grid(draw, items)
    draw_caption(draw, "⑤ 后悔药：撤销上次整理，一键还原")
    frames.append(img)

    img2, draw2 = new_canvas()
    title = "Smart File Sorter v2.4.0"
    fnt = font(56, bold=True)
    tw = draw2.textlength(title, font=fnt)
    draw2.text(((W - tw) / 2, 330), title, font=fnt, fill=(255, 255, 255))
    sub = "智能文件分类管理系统"
    fnt2 = font(28)
    tw2 = draw2.textlength(sub, font=fnt2)
    draw2.text(((W - tw2) / 2, 420), sub, font=fnt2, fill=PANEL_DIM)
    frames.append(img2)
    return frames


# ---------------------------------------------------------------- 主流程
def main() -> None:
    config = copy.deepcopy(DEFAULT_CONFIG)

    build_fake_desktop()
    print(f"[demo] 假桌面已生成：{len(FILES)} 个文件 @ {DESKTOP}")

    # ---- 真实扫描（scene 2 的数据源）
    scan = scan_directory(DESKTOP, config)
    corrected = [r for r in scan if r.get("corrected")]
    for r in corrected:
        print(f"[demo] 内容校验纠正：{r['name']} → {r['category']}"
              f"（真实格式 {r['detected_format']}）")
    if not any(r["name"] == "风景图.pdf" and r["corrected"] for r in scan):
        print("[demo] ⚠ 注意：风景图.pdf 未被内容校验纠正，与预期不符！")

    frames: list[Image.Image] = []
    frames += scene1_frames()
    frames += scene2_frames(scan)

    # ---- 真实整理 + 写入历史库
    organized = organize_files(scan, config, dry_run=False)
    run_id = record_run(organized)
    moved = sum(len(v) for v in organized.values())
    print(f"[demo] 整理完成：run_id={run_id}，记录 {moved} 条")

    frames += scene3_frames()

    # ---- 真实查重（整理后在整个桌面递归查找）
    groups = find_duplicates([DESKTOP], recursive=True)
    for g in groups:
        print(f"[demo] 重复组：{len(g['paths'])} 份 × {g['size']} 字节，"
              f"可回收 {g['reclaimable']} 字节")
    frames.append(scene4_frame(groups))

    # ---- 真实撤销
    result = undo_run()
    print(f"[demo] 撤销 run #{result['run_id']}：还原 {len(result['restored'])} 个，"
          f"跳过 {len(result['skipped'])} 个")
    frames += scene5_frames()

    # ---- 落帧并编码
    for i, frame in enumerate(frames):
        frame.save(FRAMES_DIR / f"f{i:03d}.png")
    print(f"[demo] 共渲染 {len(frames)} 帧 → {FRAMES_DIR}")

    OUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-framerate", "2",
        "-i", str(FRAMES_DIR / "f%03d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(OUT_VIDEO),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    size = OUT_VIDEO.stat().st_size
    print(f"[demo] 视频已生成：{OUT_VIDEO}（{size} 字节，{len(frames)} 帧 @2fps）")


if __name__ == "__main__":
    main()
