import base64
import io
import json
import math
import os
import zipfile
from pathlib import Path
import anthropic
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, request, send_file, render_template, flash, redirect, url_for, make_response

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "grid-secret")

COLUMNS = 4
ROWS = 4
LINE_COLOR = (255, 0, 0)
LINE_WIDTH = 2
LINE_OPACITY = 180
MAX_BYTES = 20 * 1024 * 1024
ALLOWED = {"png", "jpg", "jpeg", "bmp", "webp", "gif"}

RULER_WIDTH_CM = 29
RULER_HEIGHT_CM = 19
MARGIN = 40
TICK_MINOR = 5
TICK_MAJOR = 12
RULER_COLOR = (30, 30, 30)
RULER_BG = (255, 255, 255)
ROW_LABELS = "ABCD"


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


def _font(size=10):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fmt(val):
    return f"{round(val, 2):g}"


def add_rulers(img, x_start=0, x_end=RULER_WIDTH_CM, y_start=0, y_end=RULER_HEIGHT_CM):
    w, h = img.size
    canvas = Image.new("RGB", (w + MARGIN, h + MARGIN), RULER_BG)
    canvas.paste(img, (MARGIN, MARGIN))
    draw = ImageDraw.Draw(canvas)
    font = _font(10)
    x_range = x_end - x_start
    y_range = y_end - y_start

    draw.line([(MARGIN, MARGIN - 1), (w + MARGIN - 1, MARGIN - 1)], fill=RULER_COLOR, width=1)
    draw.line([(MARGIN - 1, MARGIN), (MARGIN - 1, h + MARGIN - 1)], fill=RULER_COLOR, width=1)

    # top ruler — whole-cm ticks + boundary ticks at start/end
    top_ticks = set(range(math.ceil(x_start), math.floor(x_end) + 1))
    top_ticks.update([x_start, x_end])
    for val in sorted(top_ticks):
        x = MARGIN + round((val - x_start) * w / x_range)
        x = max(MARGIN, min(x, w + MARGIN - 1))
        is_major = (round(val, 6) % 5 == 0)
        is_boundary = (val == x_start or val == x_end)
        tick_h = TICK_MAJOR if is_major else TICK_MINOR
        draw.line([(x, MARGIN - tick_h), (x, MARGIN - 1)], fill=RULER_COLOR, width=1)
        if is_major or is_boundary:
            label = _fmt(val)
            tw, th = _text_size(draw, label, font)
            draw.text((x - tw // 2, MARGIN - tick_h - th - 1), label, fill=RULER_COLOR, font=font)

    # left ruler — same logic
    left_ticks = set(range(math.ceil(y_start), math.floor(y_end) + 1))
    left_ticks.update([y_start, y_end])
    for val in sorted(left_ticks):
        y = MARGIN + round((val - y_start) * h / y_range)
        y = max(MARGIN, min(y, h + MARGIN - 1))
        is_major = (round(val, 6) % 5 == 0)
        is_boundary = (val == y_start or val == y_end)
        tick_w = TICK_MAJOR if is_major else TICK_MINOR
        draw.line([(MARGIN - tick_w, y), (MARGIN - 1, y)], fill=RULER_COLOR, width=1)
        if is_major or is_boundary:
            label = _fmt(val)
            tw, th = _text_size(draw, label, font)
            draw.text((MARGIN - tick_w - tw - 2, y - th // 2), label, fill=RULER_COLOR, font=font)

    return canvas


def stamp_label(img, label, x0=None, y0=None):
    draw = ImageDraw.Draw(img)
    font = _font(14)
    tw, th = _text_size(draw, label, font)
    pad = 4
    if x0 is None:
        x0 = MARGIN + 6
    if y0 is None:
        y0 = MARGIN + 6
    draw.rectangle([x0, y0, x0 + tw + pad * 2, y0 + th + pad * 2], fill=(255, 255, 255))
    draw.text((x0 + pad, y0 + pad), label, fill=(30, 30, 30), font=font)
    return img


def apply_grid(file_bytes):
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

    for row in range(ROWS):
        for col in range(COLUMNS):
            label = f"{ROW_LABELS[row]}{col + 1}"
            lx = MARGIN + round(col * width / COLUMNS) + 6
            ly = MARGIN + round(row * height / ROWS) + 6
            stamp_label(result, label, lx, ly)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    return buf


def split_image(file_bytes):
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    width, height = img.size
    sw = width // COLUMNS
    sh = height // ROWS

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in range(ROWS):
            for col in range(COLUMNS):
                square = img.crop((col * sw, row * sh, col * sw + sw, row * sh + sh))

                x_start = col * RULER_WIDTH_CM / COLUMNS
                x_end = (col + 1) * RULER_WIDTH_CM / COLUMNS
                y_start = row * RULER_HEIGHT_CM / ROWS
                y_end = (row + 1) * RULER_HEIGHT_CM / ROWS

                square = add_rulers(square, x_start, x_end, y_start, y_end)
                label = f"{ROW_LABELS[row]}{col + 1}"
                stamp_label(square, label)

                sq_buf = io.BytesIO()
                square.save(sq_buf, format="PNG")
                sq_buf.seek(0)
                zf.writestr(f"{label}.png", sq_buf.read())

    zip_buf.seek(0)
    return zip_buf


def simplify_to_shapes(file_bytes):
    arr = np.frombuffer(file_bytes, np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    h, w = img_bgr.shape[:2]

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Bilateral filter kills texture while keeping hard edges
    bilateral = cv2.bilateralFilter(gray, 15, 75, 75)

    # Heavy Gaussian on top to further suppress fine detail
    blurred = cv2.GaussianBlur(bilateral, (11, 11), 0)

    # Fixed thresholds — adaptive was too sensitive on bright/white images
    edges = cv2.Canny(blurred, 40, 120)

    # Close small gaps so nearby edge fragments merge into solid outlines
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    min_area = max(500, (w * h) * 0.001)  # ignore anything smaller than 0.1% of image

    for cnt in contours:
        if cv2.contourArea(cnt) < min_area:
            continue
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) < 3:
            continue
        cv2.drawContours(canvas, [approx], -1, (40, 40, 40), 2)

    result = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    result = add_rulers(result)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    return buf


CLAUDE_PROMPT = (
    "You are helping an artist learn gesture and construction drawing. "
    "Analyze this image and break the main subject(s) into simple geometric shapes — "
    "ellipses, rectangles, triangles, or lines — the way an art teacher constructs a figure.\n\n"
    "Return ONLY a JSON array, no markdown, no explanation. Each item:\n"
    '{"type":"ellipse"|"rectangle"|"triangle"|"line",'
    '"x1":<0-100>,"y1":<0-100>,"x2":<0-100>,"y2":<0-100>,'
    '"label":"<short name>"}\n\n'
    "x1,y1=top-left, x2,y2=bottom-right as % of image size. "
    "Return 6-15 shapes for the main subject only. Ignore background."
)

SHAPE_COLORS = {
    "ellipse":   (30,  120, 220),
    "rectangle": (20,  160,  60),
    "triangle":  (220, 110,   0),
    "line":      (160,  30, 200),
}


def claude_simplify(file_bytes, api_key):
    # Resize to max 1024px before sending — saves cost and latency
    orig = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    ow, oh = orig.size
    scale = min(1.0, 1024 / max(ow, oh))
    send_img = orig.resize((int(ow * scale), int(oh * scale)), Image.LANCZOS) if scale < 1 else orig
    send_buf = io.BytesIO()
    send_img.save(send_buf, format="JPEG", quality=85)
    b64 = base64.standard_b64encode(send_buf.getvalue()).decode()

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": CLAUDE_PROMPT},
        ]}],
    )
    raw = msg.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    shapes = json.loads(raw)

    # Draw colored shape overlays on the original photo
    canvas = orig.convert("RGBA")
    overlay = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(11)

    for shape in shapes:
        t = shape.get("type", "rectangle")
        x1, y1 = shape["x1"] / 100 * ow, shape["y1"] / 100 * oh
        x2, y2 = shape["x2"] / 100 * ow, shape["y2"] / 100 * oh
        r, g, b = SHAPE_COLORS.get(t, (220, 0, 0))
        color = (r, g, b, 210)
        label = shape.get("label", "")

        if t == "ellipse":
            draw.ellipse([(x1, y1), (x2, y2)], outline=color, width=3)
        elif t == "triangle":
            cx = (x1 + x2) / 2
            draw.polygon([(cx, y1), (x1, y2), (x2, y2)], outline=color, width=3)
        elif t == "line":
            draw.line([(x1, y1), (x2, y2)], fill=color, width=3)
        else:
            draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=3)

        if label:
            draw.text((x1 + 4, y1 + 2), label, fill=color, font=font)

    result = Image.alpha_composite(canvas, overlay).convert("RGB")
    result = add_rulers(result)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _set_download_cookie(resp, token):
    if token:
        resp.set_cookie(f"dl_{token}", "1", max_age=60, samesite="Lax")


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
    resp = make_response(send_file(buf, mimetype="image/png", as_attachment=True,
                                   download_name=f"{stem}_grid.png"))
    _set_download_cookie(resp, request.form.get("download_token", ""))
    return resp


@app.route("/split", methods=["POST"])
def split():
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
    buf = split_image(data)
    stem = Path(file.filename).stem
    resp = make_response(send_file(buf, mimetype="application/zip", as_attachment=True,
                                   download_name=f"{stem}_squares.zip"))
    _set_download_cookie(resp, request.form.get("download_token", ""))
    return resp


@app.route("/simplify", methods=["POST"])
def simplify():
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
    buf = simplify_to_shapes(data)
    stem = Path(file.filename).stem
    resp = make_response(send_file(buf, mimetype="image/png", as_attachment=True,
                                   download_name=f"{stem}_shapes.png"))
    _set_download_cookie(resp, request.form.get("download_token", ""))
    return resp


@app.route("/claude", methods=["POST"])
def claude_route():
    file = request.files.get("image")
    api_key = request.form.get("api_key", "").strip()
    if not file or file.filename == "":
        flash("Please choose an image file.")
        return redirect(url_for("index"))
    if not api_key:
        flash("Paste your Anthropic API key to use Claude analysis.")
        return redirect(url_for("index"))
    if not _allowed(file.filename):
        flash("Unsupported file type. Use PNG, JPG, BMP, WEBP, or GIF.")
        return redirect(url_for("index"))
    data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        flash("File too large (max 20 MB).")
        return redirect(url_for("index"))
    try:
        buf = claude_simplify(data, api_key)
    except Exception as e:
        flash(f"Claude error: {e}")
        return redirect(url_for("index"))
    stem = Path(file.filename).stem
    resp = make_response(send_file(buf, mimetype="image/png", as_attachment=True,
                                   download_name=f"{stem}_claude.png"))
    _set_download_cookie(resp, request.form.get("download_token", ""))
    return resp


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
