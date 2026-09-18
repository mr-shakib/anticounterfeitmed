#!/usr/bin/env python
"""Generate every sized copy of the project mark from one source file.

Keeping these generated rather than hand-placed means a change to the mark
reaches the app, the portal and the landing page together, instead of leaving
one surface showing an old badge.
"""

from __future__ import annotations

import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "brand" / "mark.webp"

#: Android launcher densities. The launcher icon is the mark on its own; the
#: badge already carries its own circular border.
LAUNCHER_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

OUTPUTS = [
    (ROOT / "landing" / "mark.png", 256),
    (ROOT / "landing" / "favicon.png", 64),
    (ROOT / "staff-web" / "public" / "mark.png", 256),
    (ROOT / "staff-web" / "app" / "icon.png", 64),
    (ROOT / "consumer-app" / "assets" / "brand" / "mark.png", 256),
]


def main() -> int:
    if not SOURCE.exists():
        print(f"missing source mark: {SOURCE}", file=sys.stderr)
        return 1

    mark = Image.open(SOURCE).convert("RGBA")
    print(f"source: {SOURCE.name} {mark.size[0]}x{mark.size[1]}")

    for path, size in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        mark.resize((size, size), Image.LANCZOS).save(path, optimize=True)
        print(f"  {path.relative_to(ROOT)}  {size}x{size}")

    res = ROOT / "consumer-app" / "android" / "app" / "src" / "main" / "res"
    for folder, size in LAUNCHER_SIZES.items():
        target = res / folder
        target.mkdir(parents=True, exist_ok=True)
        resized = mark.resize((size, size), Image.LANCZOS)
        resized.save(target / "ic_launcher.png", optimize=True)
        print(f"  {(target / 'ic_launcher.png').relative_to(ROOT)}  {size}x{size}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
