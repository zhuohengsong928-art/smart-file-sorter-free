# 🦞 Smart File Sorter

[![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.3.0-orange)](https://github.com/zhuohengsong928-art/smart-file-sorter)

> 基于 Python 的智能文件分拣管理工具，支持文件自动分类、批量重命名、内容去重、运行日志追溯，适用于个人办公桌面自动化管理。

---

## ✨ 功能

- 🏷️ **智能分类** — 扩展名自动识别 7 大类，YAML 自由扩展规则
- 🔄 **批量重命名** — `{date}_{name}` 模板引擎，冲突自动递增 `(1)(2)...`
- 🛡️ **内容去重** — MD5 哈希比对，同内容文件零覆盖、省空间
- 📋 **运行日志** — 控制台 + 文件双通道，完整记录每次操作轨迹
- 🔍 **安全预览** — `--dry-run` 先看再动，零风险
- 📊 **统计报告** — 分类数量 / 文件大小 / 跳过明细，支持 JSON 导出
- 🚫 **智能过滤** — 自动跳过系统文件、快捷方式、下载临时文件

## 📦 安装

```bash
git clone https://github.com/zhuohengsong928-art/smart-file-sorter.git
cd smart-file-sorter
pip install -e .
```

> 极简依赖：Python 3.9+ + `pyyaml`

## 🚀 使用

```bash
# 一键启动（双击也可）
启动.bat

# 命令行
python -m file_sorter ~/Desktop --dry-run    # 预览
python -m file_sorter ~/Desktop              # 整理
python -m file_sorter ~/Desktop ~/Downloads  # 多目录
python -m file_sorter ~/Downloads -r         # 递归子目录
python -m file_sorter ~/Desktop --json report.json -v  # 导出报告
```

## 📋 分类规则

| 分类 | 匹配扩展名 |
|------|-----------|
| 📑 PDF文档 | `.pdf` `.epub` `.mobi` |
| 🖼️ 图片 | `.jpg` `.png` `.gif` `.bmp` `.webp` `.svg` |
| 💻 代码脚本 | `.py` `.js` `.html` `.css` `.java` `.go` `.json` `.sql` |
| 📄 办公文档 | `.doc` `.docx` `.xls` `.xlsx` `.ppt` `.pptx` `.txt` `.md` |
| 📦 压缩包 | `.zip` `.rar` `.7z` `.tar` `.gz` |
| 🎬 音视频 | `.mp4` `.mov` `.mp3` `.flv` `.avi` `.mkv` |
| 📁 其他 | 未匹配以上规则的文件（.exe 等） |

## ⚙️ 自定义

编辑 `config/rules.yaml`：

```yaml
categories:
  我的图片:
    - .jpg
    - .png

rename_format: "{date}_{name}"   # 模板
date_format: "%Y%m%d"             # 日期格式
dedup_by_content: true            # MD5 去重开关
recursive: false                  # 是否递归扫描
```

## 🏗️ 结构

```
smart-file-sorter/
├── file_sorter/
│   ├── __main__.py       # CLI 入口
│   ├── config.py         # 配置管理（YAML）
│   ├── classifier.py     # 文件扫描与分类
│   ├── renamer.py        # 批量重命名 + 内容去重
│   ├── archiver.py       # 目录归档
│   ├── logger.py         # 双通道日志系统
│   ├── stats.py          # 统计计算
│   └── reporter.py       # 终端 / JSON 报告
├── config/
│   └── rules.yaml        # 默认规则
├── tests/
│   └── test_sorter.py    # 单元测试
├── 启动.bat              # 一键启动脚本
├── pyproject.toml
└── README.md
```

## 📄 许可

MIT License © 2026

---

*让文件管理像吃龙虾一样优雅 🦞*
