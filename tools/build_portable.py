# -*- coding: utf-8 -*-
"""
把 kairisei-wiki 打包成「傻瓜包」（方案 A：便携 Node 运行时 + 零依赖本地服务）。

用法：
    python tools/build_portable.py                 # 极简版（只带缩略图）
    python tools/build_portable.py --full-images   # 完整版（附带 chr51 原图 5.4GB）
    python tools/build_portable.py --out D:/xxx    # 指定输出目录

打包结果结构：
    kairisei-wiki-portable/
      start.cmd            双击启动
      server.mjs           零依赖本地服务
      README.txt           使用说明
      LICENSE              非商业授权
      runtime/node.exe     便携 Node 运行时
      web/                 dist 构建产物
      images/thumbs/       缩略图
      images/full/         原图（仅 --full-images）
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PORTABLE_SRC = PROJECT / "tools" / "portable"

DEFAULT_OUT = PROJECT.parent / "release" / "kairisei-wiki-portable"
PACKAGE_NAME = "kairisei-wiki-portable"

NODE_CANDIDATES = [
    Path.home() / ".workbuddy/binaries/node/versions/22.12.0/node.exe",
    Path.home() / ".workbuddy/binaries/node/versions/22.22.2-3/node.exe",
    Path("C:/Program Files/nodejs/node.exe"),
]

DEFAULT_IMAGE_ROOT = Path("D:/新建文件夹 (2)/kairisei-ma-cn602-server/resource-set/resources/image")


def human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def find_node() -> Path:
    for candidate in NODE_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "找不到可用的 node.exe。请把便携版 node.exe 放到 runtime/node.exe 后重试。\n"
        "候选路径：\n  " + "\n  ".join(str(c) for c in NODE_CANDIDATES)
    )


def safe_clean(target: Path) -> None:
    """只清理我们自己的打包输出目录，绝不碰其它路径。"""
    if not target.exists():
        return
    if target.name != PACKAGE_NAME:
        raise SystemExit(f"拒绝删除非本工具产出的目录：{target}")
    shutil.rmtree(target)


def copy_tree(src: Path, dst: Path, label: str) -> int:
    if not src.exists():
        raise SystemExit(f"[缺失] {label} 不存在：{src}")
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    size = dir_size(dst)
    count = sum(1 for p in dst.rglob("*") if p.is_file())
    print(f"  [OK] {label:<22} {count:>5} 个文件  {human(size):>10}")
    return size


def main() -> None:
    parser = argparse.ArgumentParser(description="打包 wiki 傻瓜包")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出目录")
    parser.add_argument("--full-images", action="store_true", help="附带 chr51 原图（约 5.4GB）")
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT, help="卡面原图根目录")
    parser.add_argument("--skip-build", action="store_true", help="跳过 dist 存在性检查")
    args = parser.parse_args()

    out: Path = args.out.resolve()
    dist = PROJECT / "dist"

    print("=" * 58)
    print("  乖离性百万亚瑟王国服资料站 · 傻瓜包构建")
    print("=" * 58)
    print(f"  输出目录：{out}")
    print(f"  图片档位：{'完整（含原图）' if args.full_images else '极简（仅缩略图）'}")
    print()

    if not (dist / "index.html").is_file() and not args.skip_build:
        raise SystemExit("dist/index.html 不存在，请先执行：npm run build")

    print("[1/6] 清理旧输出")
    safe_clean(out)
    out.mkdir(parents=True, exist_ok=True)

    start = time.time()
    total = 0

    print("[2/6] 拷贝网站本体")
    total += copy_tree(dist, out / "web", "web/ (dist)")

    print("[3/6] 拷贝卡面图片")
    total += copy_tree(PROJECT / ".cache" / "thumbs", out / "images" / "thumbs", "images/thumbs")
    if args.full_images:
        src_full = args.image_root / "chr51"
        total += copy_tree(src_full, out / "images" / "full" / "chr51", "images/full/chr51")

    print("[4/6] 拷贝运行时")
    node = find_node()
    runtime = out / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copy2(node, runtime / "node.exe")
    node_size = (runtime / "node.exe").stat().st_size
    total += node_size
    print(f"  [OK] runtime/node.exe      1 个文件  {human(node_size):>10}  (来源 {node})")

    print("[5/6] 拷贝启动脚本与文档")
    out.mkdir(parents=True, exist_ok=True)
    for name in ("server.mjs", "start.cmd", "README.txt", "LICENSE"):
        src = PORTABLE_SRC / name
        if src.is_file():
            shutil.copy2(src, out / name)
            total += src.stat().st_size
            print(f"  [OK] {name}")
        elif name == "LICENSE":
            print(f"  [警告] 缺少 LICENSE（应在 {src}）")

    print("[6/6] 生成版本信息")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    (out / "BUILD.txt").write_text(
        "构成：\n"
        f"  构建时间 {stamp}\n"
        f"  图片档位 {'full' if args.full_images else 'thumbs-only'}\n"
        f"  Node     {node}\n"
        f"  包含     web/ + images/ + runtime/node.exe\n",
        encoding="utf-8",
    )

    print()
    print("-" * 58)
    print(f"  完成！总大小约 {human(total)}，耗时 {time.time() - start:.1f}s")
    print(f"  双击运行：{out / 'start.cmd'}")
    print("-" * 58)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
