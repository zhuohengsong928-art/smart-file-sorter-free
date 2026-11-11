"""配置管理：加载和验证 YAML 规则文件。"""

import os
import fnmatch
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

DEFAULT_CONFIG = {
    "categories": {
        "PDF文档": [".pdf", ".epub", ".mobi"],
        "图片": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
        "代码脚本": [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".go", ".json", ".sql"],
        "办公文档": [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv"],
        "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
        "音视频": [".mp4", ".mov", ".avi", ".mkv", ".flv", ".mp3", ".wav", ".flac", ".aac"],
    },
    "skip_extensions": [".lnk", ".url", ".crdownload", ".tmp", ".part"],
    "skip_patterns": ["desktop.ini", "Thumbs.db", ".DS_Store", "~$*"],
    "recursive": False,
    "rename_format": "{date}_{name}",
    "date_format": "%Y%m%d",
    "output_root": "",
}


def load_config(path: str | Path) -> dict[str, Any]:
    """从 YAML 文件加载配置，融合到默认配置中。"""
    path = Path(path)
    config = {**DEFAULT_CONFIG}

    if not path.exists():
        return config

    content = path.read_text(encoding="utf-8")

    if yaml is not None:
        user_config = yaml.safe_load(content) or {}
    else:
        # fallback: 极简 YAML 解析（仅支持嵌套字典+列表）
        user_config = _parse_simple_yaml(content)

    # 深度合并
    _deep_merge(config, user_config)
    return config


def _deep_merge(base: dict, override: dict) -> None:
    """递归合并 override 到 base。"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def should_skip(filename: str, config: dict[str, Any]) -> bool:
    """判断文件是否应跳过（系统文件、快捷方式、临时文件）。"""
    name = os.path.basename(filename)
    ext = os.path.splitext(name)[1].lower()

    # 跳过指定扩展名
    if ext in config.get("skip_extensions", []):
        return True

    # 跳过匹配模式的文件名
    for pattern in config.get("skip_patterns", []):
        if fnmatch.fnmatch(name, pattern):
            return True

    return False


def classify_file(filename: str, config: dict[str, Any]) -> str:
    """根据扩展名返回分类名称，未匹配返回"其他"。"""
    ext = os.path.splitext(filename)[1].lower()
    for category, extensions in config.get("categories", {}).items():
        if ext in extensions:
            return category
    return "其他"


def _parse_simple_yaml(content: str) -> dict:
    """简易 YAML 回退解析器（pyyaml 不可用时）。"""
    import re

    result: dict[str, Any] = {}
    lines = content.split("\n")
    current_section: str | None = None
    current_list: list[str] = []

    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue

        # 顶层键
        m = re.match(r"^(\w[\w_]*)\s*:\s*(.*)", stripped)
        if m and not stripped.startswith("  "):
            key = m.group(1)
            value = m.group(2).strip()
            if value:
                result[key] = _parse_yaml_value(value)
                current_section = None
            else:
                current_section = key
                current_list = []

        # 列表项
        elif stripped.startswith("- ") and current_section:
            item = stripped[2:].strip().strip('"').strip("'")
            current_list.append(item)
            if current_section == "categories":
                # categories 下可能嵌套
                pass

        # 嵌套键
        elif current_section and not stripped.startswith("-"):
            pass

    if current_section:
        result[current_section] = current_list

    return result


def _parse_yaml_value(v: str) -> Any:
    """解析简单 YAML 值。"""
    v = v.strip().strip('"').strip("'")
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.isdigit():
        return int(v)
    return v
