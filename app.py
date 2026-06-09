import io
import os
from pathlib import Path
from PIL import Image, ImageDraw
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


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


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

    result = Image.alpha_composite(img, overlay).convert("RGB")
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
