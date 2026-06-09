import io
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, request, send_file, render_template, flash, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "grid-secret")

COLUMNS = 4
ROWS = 4
LINE_COLOR = (255, 0, 0)
LINE_WIDTH = 2
LINE_OPACITY = 180
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED = {"png", "jpg", "jpeg", "bmp", "webp", "gif"}

RULER_WIDTH_CM = 29
RULER_HEIGHT_CM = 19
MARGIN = 40          # px strip added to top and left
TICK_MINOR = 5       # px for every-1cm tick
TICK_MAJOR = 12      # px for every-5cm tick
RULER_COLOR = (30, 30, 30)
RULER_BG = (255, 255, 255)


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


def _font(size: int = 10):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def add_rulers(img: Image.Image) -> Image.Image:
    w, h = img.size
    canvas = Image.new("RGB", (w + MARGIN, h + MARGIN), RULER_BG)
    canvas.paste(img, (MARGIN, MARGIN))
    draw = ImageDraw.Draw(canvas)
    font = _font(10)

    # baseline lines where ruler meets image
    draw.line([(MARGIN, MARGIN - 1), (w + MARGIN - 1, MARGIN - 1)], fill=RULER_COLOR, width=1)
    draw.line([(MARGIN - 1, MARGIN), (MARGIN - 1, h + MARGIN - 1)], fill=RULER_COLOR, width=1)

    # top ruler (0 → 29 cm)
    for i in range(RULER_WIDTH_CM + 1):
        x = MARGIN + round(i * w / RULER_WIDTH_CM)
        x = min(x, w + MARGIN - 1)
        is_major = (i % 5 == 0)
        tick_h = TICK_MAJOR if is_major else TICK_MINOR
        draw.line([(x, MARGIN - tick_h), (x, MARGIN - 1)], fill=RULER_COLOR, width=1)
        if is_major:
            label = str(i)
            tw, th = _text_size(draw, label, font)
            draw.text((x - tw // 2, MARGIN - tick_h - th - 1), label, fill=RULER_COLOR, font=font)

    # left ruler (0 → 19 cm)
    for i in range(RULER_HEIGHT_CM + 1):
        y = MARGIN + round(i * h / RULER_HEIGHT_CM)
        y = min(y, h + MARGIN - 1)
        is_major = (i % 5 == 0)
        tick_w = TICK_MAJOR if is_major else TICK_MINOR
        draw.line([(MARGIN - tick_w, y), (MARGIN - 1, y)], fill=RULER_COLOR, width=1)
        if is_major:
            label = str(i)
            tw, th = _text_size(draw, label, font)
            draw.text((MARGIN - tick_w - tw - 2, y - th // 2), label, fill=RULER_COLOR, font=font)

    return canvas


def apply_grid(file_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(file_bytes)).convert("RGBA")
    width, height = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    col_step = width / COLUMNS
    for i in range(1, COLUMNS):
        x = round(col_step * i)
        draw.line([(x, 0), (x, height - 1)], fill=(*LINE_COLOR, LINE_OPACITY), width=LINE_WIDTH)

    row_step = height / ROWS
    for i in range(1, ROWS):
        y = round(row_step * i)
        draw.line([(0, y), (width - 1, y)], fill=(*LINE_COLOR, LINE_OPACITY), width=LINE_WIDTH)

    gridded = Image.alpha_composite(img, overlay).convert("RGB")
    result = add_rulers(gridded)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    return buf


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    file = request.files.get("image")
    if not file or file.filename == "":
        flash("Please choose an image file.")
        return redirect(url_for("index"))
    if not _allowed(file.filename):
        flash("Unsupported file type. Use PNG, JPG, BMP, WEBP, or GIF.")
        return redirect(url_for("index"))

    data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        flash("File too large (max 20 MB).")
        return redirect(url_for("index"))

    buf = apply_grid(data)
    stem = Path(file.filename).stem
    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"{stem}_grid.png")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
