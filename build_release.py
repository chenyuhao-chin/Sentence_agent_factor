#!/usr/bin/env python3
"""
Agent Factory — 发布打包脚本
=============================
一键生成两种版本的源码包：
  1. 纯净版（opensource）— 不含商业 Prompt，可公开售卖
  2. 商业版（commercial）— 含完整微调 Prompt，内部使用

使用方式：
    python3 build_release.py --type opensource   # 生成纯净版
    python3 build_release.py --type commercial   # 生成商业版
    python3 build_release.py --type both         # 两个都生成
"""

import argparse
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "releases"

# 商业敏感文件（纯净版替换为开源版）
COMMERCIAL_FILES = ["prompts/architect.md"]

# 纯净版替换映射：商业文件 → 开源替代
OPENSOURCE_SWAPS = {
    "prompts/architect.md": "prompts/architect_opensource.md",
}

# 排除的目录/文件（两个版本都不带）
EXCLUDE_PATTERNS = [
    "__pycache__", ".git", ".env", ".env.local", ".env.production",
    "venv", ".venv", "releases", "output_agents",
    ".idea", ".vscode", "*.pyc", ".pytest_cache", "agent_config.json",
]


def should_exclude(path: Path) -> bool:
    parts = path.relative_to(BASE_DIR).parts
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*."):
            if path.name.endswith(pattern[1:]):
                return True
        elif pattern in parts:
            return True
    return False


def build_release(version_type: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version = "v1.0"
    zip_name = f"agent_factory_{version_type}_{version}_{timestamp}.zip"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUTPUT_DIR / zip_name

    print(f"\n{'='*60}")
    print(f"  构建 {version_type.upper()} 版本")
    print(f"  输出: {zip_path}")
    print(f"{'='*60}\n")

    files_added = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BASE_DIR):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if not should_exclude(root_path / d)]

            for fname in files:
                file_path = root_path / fname
                if should_exclude(file_path):
                    continue

                arcname = str(file_path.relative_to(BASE_DIR))

                # 读取文件内容
                try:
                    content = file_path.read_bytes()
                except Exception:
                    continue

                # 纯净版：商业文件替换为开源版
                if version_type == "opensource" and arcname in COMMERCIAL_FILES:
                    swap_src = OPENSOURCE_SWAPS.get(arcname)
                    if swap_src:
                        swap_path = BASE_DIR / swap_src
                        if swap_path.exists():
                            content = swap_path.read_bytes()
                            print(f"  [替换] {arcname} → 开源版 ({swap_src})")
                        else:
                            print(f"  [警告] 开源替代不存在: {swap_src}，跳过")
                            continue

                zf.writestr(arcname, content)
                files_added += 1

    size_kb = zip_path.stat().st_size / 1024
    print(f"\n  ✅ 打包完成: {zip_name}")
    print(f"  📦 文件数: {files_added}")
    print(f"  📐 大小: {size_kb:.1f} KB")

    return str(zip_path)


def main():
    parser = argparse.ArgumentParser(description="Agent Factory 发布打包")
    parser.add_argument(
        "--type",
        choices=["opensource", "commercial", "both"],
        default="both",
        help="版本类型: opensource(纯净版) / commercial(商业版) / both(两个都生成)",
    )
    args = parser.parse_args()

    if args.type in ("opensource", "both"):
        build_release("opensource")

    if args.type in ("commercial", "both"):
        build_release("commercial")

    print(f"\n{'='*60}")
    print(f"  所有版本构建完成，输出目录: releases/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
