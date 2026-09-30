# -*- coding: utf-8 -*-
"""生成卡面缩略图。

原图每张约 1.2MB，列表页直接加载会很慢。这里统一缩到宽 180px，
无透明通道的图做调色板量化，体积可降到约 20KB。

用法:
    python tools/thumbs.py            # 增量生成
    python tools/thumbs.py --force    # 全量重生成
"""
from __future__ import annotations

import os
import sys
import time

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_IMAGE_ROOT = r"D:\新建文件夹 (2)\kairisei-ma-cn602-server\resource-set\resources\image"
IMAGE_ROOT = os.environ.get("KAIRI_IMAGE_ROOT", DEFAULT_IMAGE_ROOT)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMB_ROOT = os.path.join(PROJECT, ".cache", "thumbs")

WIDTH = 180


def main() -> int:
    force = "--force" in sys.argv
    source_dir = os.path.join(IMAGE_ROOT, "chr51")
    target_dir = os.path.join(THUMB_ROOT, "chr51")
    if not os.path.isdir(source_dir):
        print(f"原图目录不存在: {source_dir}")
        return 1
    os.makedirs(target_dir, exist_ok=True)

    names = sorted(name for name in os.listdir(source_dir) if name.endswith(".png"))
    total = len(names)
    done = skipped = failed = 0
    started = time.time()
    original_bytes = thumb_bytes = 0

    for index, name in enumerate(names, start=1):
        source = os.path.join(source_dir, name)
        target = os.path.join(target_dir, name)
        if not force and os.path.exists(target) and os.path.getmtime(target) >= os.path.getmtime(source):
            skipped += 1
            continue
        try:
            with Image.open(source) as image:
                # 统一转 RGBA 处理：卡面原图全部带透明通道。
                # FASTOCTREE 量化是少数支持 RGBA 的方式，透明度会保留在调色板里。
                image = image.convert("RGBA")
                ratio = WIDTH / image.width
                size = (WIDTH, max(1, round(image.height * ratio)))
                thumb = image.resize(size, Image.LANCZOS)
                thumb.quantize(colors=256, method=Image.FASTOCTREE).save(target, "PNG", optimize=True)
            original_bytes += os.path.getsize(source)
            thumb_bytes += os.path.getsize(target)
            done += 1
        except Exception as error:  # noqa: BLE001
            failed += 1
            if failed <= 5:
                print(f"  ! {name}: {error}")
        if index % 500 == 0:
            print(f"  ... {index}/{total}  新增={done} 跳过={skipped} 失败={failed}", flush=True)

    print(
        f"完成 新增={done} 跳过={skipped} 失败={failed} 用时={time.time() - started:.1f}s "
        f"原图={original_bytes / 1048576:.0f}MB 缩略图={thumb_bytes / 1048576:.0f}MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
