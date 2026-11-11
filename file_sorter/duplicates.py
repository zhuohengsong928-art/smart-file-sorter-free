"""重复文件扫描与清理。

毕设升级模块（v2.4.0 新增）：
- 两阶段比对：先按文件大小粗筛（大小不同绝不重复），
  再对同大小文件计算 MD5 确认内容完全一致，避免全量哈希的浪费；
- 输出每组重复文件的可回收空间，帮助用户决定是否清理；
- 删除操作默认 dry_run（只报告不动手），且每组至少保留一份。
- 图片相似检测（v2.4.0 续）：MD5 只认字节，同一张图的 JPG/PNG 版本
  字节完全不同、抓不到；对图片另用感知哈希（aHash）按"长相"分组——
  先缩放灰度化为 8×8，再与均值比较生成 64 位指纹，汉明距离小于
  阈值即判为相似。相似不等于相同，所以只报告、永不自动删除。
  该功能需要可选依赖 Pillow，未安装时自动跳过、不影响主功能。
"""

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable

from .logger import get_logger

_CHUNK = 1024 * 1024  # 1 MiB 分块读，避免大文件一次进内存


def file_md5(path: str | Path) -> str:
    """计算文件 MD5（分块读取）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _iter_files(directories: Iterable[str | Path], recursive: bool) -> Iterable[Path]:
    for d in directories:
        root = Path(d)
        if not root.exists():
            continue
        it = root.rglob("*") if recursive else root.glob("*")
        for p in it:
            if p.is_file():
                yield p


def find_duplicates(
    directories: Iterable[str | Path],
    recursive: bool = True,
    min_size: int = 1,
) -> list[dict[str, Any]]:
    """扫描目录，返回内容重复的文件组。

    Returns:
        每组一个字典：{md5, size, paths, reclaimable}
        reclaimable = size * (份数 - 1)，按可回收空间从大到小排序。
    """
    log = get_logger()
    # 第一阶段：按大小分组
    by_size: dict[int, list[Path]] = {}
    for p in _iter_files(directories, recursive):
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < min_size:
            continue
        by_size.setdefault(size, []).append(p)

    # 第二阶段：同大小组内按 MD5 分组
    groups: list[dict[str, Any]] = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for p in paths:
            try:
                digest = file_md5(p)
            except OSError as e:
                log.warning("读取失败跳过: %s (%s)", p, e)
                continue
            by_hash.setdefault(digest, []).append(str(p))
        for digest, same in by_hash.items():
            if len(same) >= 2:
                groups.append(
                    {
                        "md5": digest,
                        "size": size,
                        "paths": sorted(same),
                        "reclaimable": size * (len(same) - 1),
                    }
                )
    groups.sort(key=lambda g: g["reclaimable"], reverse=True)
    total = sum(g["reclaimable"] for g in groups)
    log.info("重复扫描完成: %d 组，可回收约 %d 字节", len(groups), total)
    return groups


def delete_duplicates(
    group: dict[str, Any],
    keep_index: int = 0,
    dry_run: bool = True,
) -> list[str]:
    """删除一组重复文件中的多余副本（保留 paths[keep_index]）。

    默认 dry_run=True 只返回将删除的路径、不实际删除。
    Returns:
        （将）删除的路径列表。
    """
    log = get_logger()
    paths = list(group["paths"])
    if not 0 <= keep_index < len(paths):
        raise ValueError("keep_index 越界")
    targets = [p for i, p in enumerate(paths) if i != keep_index]
    for p in targets:
        if dry_run:
            log.info("[dry-run] 将删除重复副本: %s", p)
        else:
            os.remove(p)
            log.info("已删除重复副本: %s", p)
    return targets


# ================= 图片相似检测（感知哈希 aHash） =================

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
_HASH_SIZE = 8  # 8×8 = 64 位指纹


def pillow_available() -> bool:
    """感知哈希依赖 Pillow（可选依赖）；没有它主功能不受影响。"""
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


def image_ahash(path: str | Path) -> int:
    """计算图片的平均哈希（aHash）指纹：

    灰度化 → 缩放为 8×8 → 每像素与均值比较，亮记 1、暗记 0，
    拼成 64 位整数。同一张图换格式/改尺寸/轻微压缩，指纹基本不变。
    """
    from PIL import Image

    with Image.open(path) as im:
        gray = im.convert("L").resize((_HASH_SIZE, _HASH_SIZE), Image.LANCZOS)
        pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    value = 0
    for px in pixels:
        value = (value << 1) | (1 if px > avg else 0)
    return value


def _hamming(a: int, b: int) -> int:
    """两个指纹的汉明距离（不同的位数）。"""
    return bin(a ^ b).count("1")


def find_similar_images(
    directories: Iterable[str | Path],
    recursive: bool = True,
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """找出内容相似的图片组（同图不同格式/尺寸也能认出）。

    两两比较指纹汉明距离，≤ threshold 判相似，用并查集聚组。
    相似不等于字节相同，因此结果仅供报告参考，不提供删除。

    Returns:
        [{paths: [路径...]}]，按组内数量从多到少排序；
        Pillow 未安装时返回空列表。
    """
    log = get_logger()
    if not pillow_available():
        log.warning("未安装 Pillow，图片相似检测不可用（pip install Pillow 启用）")
        return []

    hashed: list[tuple[str, int]] = []
    for p in _iter_files(directories, recursive):
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        try:
            hashed.append((str(p), image_ahash(p)))
        except Exception as e:  # 损坏图片等：跳过不崩
            log.warning("图片指纹计算失败跳过: %s (%s)", p, e)

    # 并查集聚类
    parent = list(range(len(hashed)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(hashed)):
        for j in range(i + 1, len(hashed)):
            if _hamming(hashed[i][1], hashed[j][1]) <= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    clusters: dict[int, list[str]] = {}
    for i, (path, _) in enumerate(hashed):
        clusters.setdefault(find(i), []).append(path)
    groups = [
        {"paths": sorted(paths)} for paths in clusters.values() if len(paths) >= 2
    ]
    groups.sort(key=lambda g: len(g["paths"]), reverse=True)
    log.info("图片相似扫描完成: %d 张图片，%d 组相似", len(hashed), len(groups))
    return groups
