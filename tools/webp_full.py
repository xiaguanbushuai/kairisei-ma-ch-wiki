# -*- coding: utf-8 -*-
"""
卡面原图 PNG → WebP q85 批量转码（用于 GitHub 备份仓库）。

用法：
    python tools/webp_full.py                  # 全量转码（跳过已存在的）
    python tools/webp_full.py --quality 80     # 指定质量
    python tools/webp_full.py --workers 8      # 并行进程数

说明：
    原图 4385 张 PNG 共 5.4GB；WebP q85 全尺寸转码后约 1.1GB，
    动漫立绘视觉几乎无差别，能塞进 GitHub 免费仓库（硬限 5GB）。
    转码可随时中断重跑：输出文件已存在且非 0 字节时自动跳过。
"""
from __future__ import annotations

import argparse
import sys
import time
from multiprocessing import Pool
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_paths  # noqa: E402  （tools/local_paths.py：统一的路径解析）

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = local_paths.image_root() / "chr51"
DEFAULT_OUT = PROJECT.parent / "kairisei-ma-ch-cards" / "images" / "chr51"


def convert_one(args):
    src_file: Path
    out_file: Path
    quality: int
    src_file, out_file, quality = args
    if out_file.exists() and out_file.stat().st_size > 0:
        return ("skip", out_file.stat().st_size)
    try:
        with Image.open(src_file) as im:
            im.save(out_file, "WEBP", quality=quality, method=4)
        return ("ok", out_file.stat().st_size, src_file.stat().st_size)
    except Exception as exc:  # noqa: BLE001
        return ("error", str(exc), src_file.name)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--quality", type=int, default=85)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    src_dir: Path = args.src
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(src_dir.glob("*.png"))
    if not files:
        raise SystemExit(f"源目录没有 PNG：{src_dir}")

    jobs = [(f, out_dir / (f.stem + ".webp"), args.quality) for f in files]
    total_src = sum(f.stat().st_size for f in files)
    print(f"共 {len(files)} 张 PNG（{human(total_src)}）→ WebP q{args.quality} → {out_dir}")
    print(f"并行 {args.workers} 进程，已转码的会自动跳过……")

    start = time.time()
    ok = skip = err = 0
    out_total = src_done = 0
    last_print = 0.0
    with Pool(args.workers) as pool:
        for i, result in enumerate(pool.imap_unordered(convert_one, jobs, chunksize=16), 1):
            if result[0] == "ok":
                ok += 1
                out_total += result[1]
                src_done += result[2]
            elif result[0] == "skip":
                skip += 1
                out_total += result[1]
            else:
                err += 1
                print(f"  [失败] {result[2]}: {result[1]}")
            if time.time() - last_print > 15 or i == len(jobs):
                last_print = time.time()
                pct = i / len(jobs) * 100
                speed = i / (time.time() - start)
                eta = (len(jobs) - i) / speed if speed > 0 else 0
                print(f"  进度 {i}/{len(jobs)} ({pct:.0f}%)  新转 {ok}  跳过 {skip}  失败 {err}  "
                      f"输出累计 {human(out_total)}  速度 {speed:.1f}张/s  剩余约 {eta:.0f}s")

    print()
    print("-" * 56)
    print(f"  完成：新转 {ok}，跳过 {skip}，失败 {err}，耗时 {time.time() - start:.0f}s")
    print(f"  输出总大小：{human(out_total)}（原 PNG {human(total_src)}，"
          f"压缩到 {out_total / total_src * 100:.0f}%）")
    print(f"  输出目录：{out_dir}")
    print("-" * 56)


if __name__ == "__main__":
    main()
