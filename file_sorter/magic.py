"""内容识别：读取文件头魔数（magic number）校验真实格式。

毕设升级模块（v2.4.0 新增）：
扩展名可以被随意改名欺骗，但文件开头的固定字节（魔数）改不了。
本模块在扩展名分类之外再读文件头做一次验证：
- 签名明确且与扩展名类别冲突 → 以真实类型为准，纠正分类；
- 纯文本类格式（txt/py/md 等）没有固定文件头 → 不强判，沿用扩展名。

只读每个文件最前面 16 字节，开销可忽略。
"""

from pathlib import Path
from typing import Optional

# 签名 → (格式名, 所属类别)。类别名与 config 的 categories 保持一致。
# 长的签名放前面，避免短签名先命中（如 OLE2 与其子格式）。
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "JPEG", "图片"),
    (b"\x89PNG\r\n\x1a\n", "PNG", "图片"),
    (b"GIF87a", "GIF", "图片"),
    (b"GIF89a", "GIF", "图片"),
    (b"BM", "BMP", "图片"),
    (b"%PDF-", "PDF", "PDF文档"),
    (b"PK\x03\x04", "ZIP容器", "压缩包"),  # zip 本体；docx/xlsx/pptx/epub 会被细化
    (b"Rar!\x1a\x07", "RAR", "压缩包"),
    (b"7z\xbc\xaf\x27\x1c", "7Z", "压缩包"),
    (b"\x1f\x8b", "GZIP", "压缩包"),
    (b"\xfd7zXZ\x00", "XZ", "压缩包"),
    (b"ID3", "MP3", "音视频"),
    (b"\xff\xfb", "MP3", "音视频"),
    (b"RIFF", "RIFF容器", "音视频"),  # wav / avi，需看子类型
    (b"\x1a\x45\xdf\xa3", "MKV/WEBM", "音视频"),
]

# ZIP 容器细化：扩展名 → 真实格式名（同属办公文档/PDF文档大类）
_ZIP_SUBTYPE_BY_EXT = {
    ".docx": "DOCX",
    ".xlsx": "XLSX",
    ".pptx": "PPTX",
    ".epub": "EPUB",
    ".jar": "JAR",
}

_CATEGORY_BY_EXT_FAMILY = {
    ".docx": "办公文档",
    ".xlsx": "办公文档",
    ".pptx": "办公文档",
    ".epub": "PDF文档",
    ".jar": "压缩包",
}

_READ_BYTES = 16


def sniff_format(path: str | Path) -> Optional[tuple[str, str]]:
    """读取文件头，返回 (格式名, 类别)；无法识别时返回 None。

    无法识别的常见情况：纯文本格式、空文件、签名不在表内——
    此时调用方应沿用扩展名分类，而不是强行判定。
    """
    p = Path(path)
    try:
        with open(p, "rb") as f:
            head = f.read(_READ_BYTES)
    except OSError:
        return None
    if len(head) < 2:
        return None

    ext = p.suffix.lower()
    for sig, fmt, category in _SIGNATURES:
        if not head.startswith(sig):
            continue
        if fmt == "ZIP容器":
            # docx/xlsx/pptx/epub 本质都是 ZIP 容器，按扩展名细化
            sub = _ZIP_SUBTYPE_BY_EXT.get(ext)
            if sub:
                return sub, _CATEGORY_BY_EXT_FAMILY[ext]
            return "ZIP", "压缩包"
        if fmt == "RIFF容器":
            subtype = head[8:12]
            if subtype == b"WAVE":
                return "WAV", "音视频"
            if subtype == b"AVI ":
                return "AVI", "音视频"
            if subtype == b"WEBP":
                return "WEBP", "图片"
            return None
        return fmt, category

    # ISO BMFF 家族（mp4/mov）：第 5~8 字节为 'ftyp'
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "MP4/MOV", "音视频"
    return None


def verify_category(
    path: str | Path,
    ext_category: str,
) -> tuple[str, Optional[str], bool]:
    """把扩展名分类与文件头校验结合，返回最终分类。

    Returns:
        (最终分类, 检测到的真实格式名或 None, 是否发生纠正)
        - 文件头无法识别 → (扩展名分类, None, False)
        - 文件头类别与扩展名一致 → (扩展名分类, 格式名, False)
        - 冲突 → (文件头类别, 格式名, True)，即以内容为准纠正
    """
    sniffed = sniff_format(path)
    if sniffed is None:
        return ext_category, None, False
    fmt, real_category = sniffed
    if real_category == ext_category:
        return ext_category, fmt, False
    return real_category, fmt, True
