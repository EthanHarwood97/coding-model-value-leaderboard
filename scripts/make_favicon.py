#!/usr/bin/env python3
"""Generate favicon.ico for the scorecard (regenerate if the palette changes)."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent.parent
SIZE = 1024

BG = "#0d1117"
BORDER = "#30363d"
ACCENT = "#58a6ff"
SUCCESS = "#3fb950"


def draw_icon(size=SIZE):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    radius = int(size * 0.22)
    d.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=radius, fill=BG, outline=BORDER, width=max(1, int(size * 0.035)),
    )

    pad = int(size * 0.24)
    base_y = size - pad
    available = base_y - pad
    bar_w = int(size * 0.15)
    gap = int(size * 0.10)
    total_w = bar_w * 3 + gap * 2
    x = (size - total_w) // 2

    for frac, color in zip((0.42, 0.62, 0.85), (ACCENT, ACCENT, SUCCESS)):
        top = base_y - int(available * frac)
        d.rounded_rectangle(
            [x, top, x + bar_w, base_y],
            radius=int(bar_w * 0.28), fill=color,
        )
        x += bar_w + gap

    return img


def main():
    out = ROOT / "favicon.ico"
    draw_icon().save(
        out, format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
