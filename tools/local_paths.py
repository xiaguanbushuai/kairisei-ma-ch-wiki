# -*- coding: utf-8 -*-
"""统一的本地路径解析（仓库内不含任何机器专属路径）。

解析顺序：环境变量 > tools/local_config.json > 中性默认值。

  · 环境变量：KAIRI_SRC（资源集根目录）、KAIRI_IMAGE_ROOT（卡面原图根目录）
  · 本地配置：把 tools/local_config.example.json 复制成 tools/local_config.json
    并填入自己机器上的实际路径。该文件已被 .gitignore 忽略，不会提交。
  · 中性默认：与工程平级的 kairisei-ma-cn602-server/resource-set
"""
from __future__ import annotations

import json
import os
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT = TOOLS_DIR.parent
CONFIG_FILE = TOOLS_DIR / "local_config.json"

# 中性默认：与工程平级的资源集目录（解压 kairisei-ma-ch 发行包后的常见位置）
DEFAULT_RESOURCE_SET = PROJECT.parent / "kairisei-ma-cn602-server" / "resource-set"


def _load_local_config() -> dict:
    if not CONFIG_FILE.is_file():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


_LOCAL = _load_local_config()


def _pick(env_name: str, config_key: str, default: Path) -> tuple[Path, str]:
    """按「环境变量 → 本地配置 → 默认值」顺序取一个路径，并返回其来源说明。"""
    value = os.environ.get(env_name)
    if value:
        return Path(value), f"环境变量 {env_name}"
    value = _LOCAL.get(config_key)
    if value:
        return Path(value), f"{CONFIG_FILE.name}"
    return default, "默认值"


def resource_set_dir() -> Path:
    """游戏服务端资源集根目录（其下为 _local/ 与 resources/）。"""
    return _pick("KAIRI_SRC", "resourceSetDir", DEFAULT_RESOURCE_SET)[0]


def image_root() -> Path:
    """卡面原图根目录（其下为 chr51/）。未单独配置时由资源集目录推导。"""
    default = resource_set_dir() / "resources" / "image"
    return _pick("KAIRI_IMAGE_ROOT", "imageRoot", default)[0]


def describe() -> str:
    """人类可读的路径与来源说明，供脚本启动时打印。"""
    src, src_from = _pick("KAIRI_SRC", "resourceSetDir", DEFAULT_RESOURCE_SET)
    img, img_from = _pick("KAIRI_IMAGE_ROOT", "imageRoot", src / "resources" / "image")
    return f"资源集目录 {src}（来源：{src_from}）\n  卡面原图   {img}（来源：{img_from}）"


def hint() -> str:
    """路径不通时的排查提示。"""
    return (
        "请任选一种方式指定游戏资源集路径：\n"
        "  1) 设置环境变量 KAIRI_SRC=<资源集根目录>\n"
        f"  2) 复制 tools/local_config.example.json 为 {CONFIG_FILE.name} 并填写实际路径\n"
        f"  3) 把资源集放到默认位置：{DEFAULT_RESOURCE_SET}"
    )
