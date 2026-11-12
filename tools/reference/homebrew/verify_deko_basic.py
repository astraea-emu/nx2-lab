#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent RGB oracle for switch-examples' unmodified deko_basic triangle."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

WIDTH, HEIGHT = 1280, 720
BACKGROUND = (32, 75, 122)


def expected_pixel(x: int, y: int) -> tuple[int, int, int]:
    """Rasterize the public-domain vertex shader at each pixel centre."""
    ndc_x = 2 * ((x + 0.5) / WIDTH) - 1
    v = (y + 0.5) / HEIGHT
    if abs(ndc_x) > v:
        return BACKGROUND
    return (round(255 * (1 - v)),
            round(255 * (v - ndc_x) / 2),
            round(255 * (v + ndc_x) / 2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    captures = sorted(args.directory.glob("*_present_*.png"))
    if not captures:
        parser.error("No present captures found")
    hashes = []
    for capture in captures:
        with Image.open(capture) as image:
            if image.size != (WIDTH, HEIGHT) or image.mode != "RGB":
                raise ValueError("Unexpected present image size or format")
            pixels = image.load()
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    expected = expected_pixel(x, y)
                    if pixels[x, y] != expected:
                        raise ValueError(f"RGB mismatch at ({x}, {y}): "
                                         f"observed {pixels[x, y]}, expected {expected}")
        hashes.append(hashlib.sha256(capture.read_bytes()).hexdigest())
    print(json.dumps({"captured_present_images": len(hashes),
                      "exact_rgb_pixels_per_image": WIDTH * HEIGHT,
                      "all_present_frames_identical": len(set(hashes)) == 1,
                      "sha256": hashes}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
