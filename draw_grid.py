#!/usr/bin/env python3
"""Draw a 4-column × 4-row drawing grid over image.png and save as image_grid.png."""

import sys
from pathlib import Path
from PIL import Image, ImageDraw

COLUMNS = 4
ROWS = 4
LINE_COLOR = (255, 0, 0)   # red
LINE_WIDTH = 2
LINE_OPACITY = 180          # 0-255; used when image has alpha channel


def draw_grid(input_path: Path, output_path: Path) -> None:
    img = Image.open(input_path).convert("RGBA")
    width, height = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Vertical lines (create COLUMNS sections → COLUMNS-1 interior lines)
    col_step = width / COLUMNS
    for i in range(1, COLUMNS):
        x = round(col_step * i)
        draw.line([(x, 0), (x, height - 1)], fill=(*LINE_COLOR, LINE_OPACITY), width=LINE_WIDTH)

    # Horizontal lines (create ROWS sections → ROWS-1 interior lines)
    row_step = height / ROWS
    for i in range(1, ROWS):
        y = round(row_step * i)
        draw.line([(0, y), (width - 1, y)], fill=(*LINE_COLOR, LINE_OPACITY), width=LINE_WIDTH)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path)
    print(f"Saved: {output_path}  ({width}×{height}px, {COLUMNS} cols × {ROWS} rows)")


if __name__ == "__main__":
    base = Path(__file__).parent
    input_file = Path(sys.argv[1]) if len(sys.argv) > 1 else base / "image.png"
    output_file = input_file.with_stem(input_file.stem + "_grid")

    if not input_file.exists():
        print(f"Error: '{input_file}' not found.")
        print("Usage: python3 draw_grid.py [image.png]")
        sys.exit(1)

    draw_grid(input_file, output_file)
