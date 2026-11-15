"""Generate the macOS app icon without checking binary assets into the repo."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def render(size: int) -> Image.Image:
    scale = size / 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(220 * scale)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=radius,
        fill=(15, 23, 42, 255),
    )
    center = (size // 2, size // 2)
    for ring, alpha in ((360, 70), (250, 95), (140, 130)):
        r = int(ring * scale)
        draw.ellipse(
            (center[0] - r, center[1] - r, center[0] + r, center[1] + r),
            outline=(45, 212, 191, alpha),
            width=max(2, int(10 * scale)),
        )
    sweep = int(330 * scale)
    draw.line(
        (center[0], center[1], center[0] + sweep, center[1] - int(120 * scale)),
        fill=(250, 204, 21, 235),
        width=max(3, int(16 * scale)),
    )
    dot_r = int(34 * scale)
    dot_center = (center[0] + int(150 * scale), center[1] - int(55 * scale))
    draw.ellipse(
        (
            dot_center[0] - dot_r,
            dot_center[1] - dot_r,
            dot_center[0] + dot_r,
            dot_center[1] + dot_r,
        ),
        fill=(250, 204, 21, 255),
    )
    return image


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: make_icon.py OUT.icns")
        return 2
    output = Path(sys.argv[1]).resolve()
    iconset = output.with_suffix(".iconset")
    iconset.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for size in sizes:
        image = render(size)
        image.save(iconset / f"icon_{size}x{size}.png")
        if size <= 512:
            image2x = render(size * 2)
            image2x.save(iconset / f"icon_{size}x{size}@2x.png")
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(output)],
        check=True,
    )
    print(f"icon: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
