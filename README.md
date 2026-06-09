# Grid Drawing Tool

Draws a 4-column × 4-row grid overlay on an image to help with drawing reference.

## Setup (first time only)

```bash
cd "/Users/amel/Documents/Documents - Amel's MacBook Air/GitStuff/Grid"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

1. Place your image as `image.png` in this folder
2. Activate the environment:
   ```bash
   source venv/bin/activate
   ```
3. Run the script:
   ```bash
   python3 draw_grid.py
   ```
4. Output is saved as `image_grid.png` in the same folder

You can also pass a custom image path:
```bash
python3 draw_grid.py /path/to/your/image.png
```

## Adding new packages

```bash
source venv/bin/activate
pip install <package-name>
pip freeze > requirements.txt
```

## Files

| File | Description |
|---|---|
| `draw_grid.py` | Main script |
| `image.png` | Input image (replace with your own) |
| `image_grid.png` | Output image with grid (auto-generated) |
| `requirements.txt` | Python dependencies |
| `venv/` | Virtual environment (do not commit) |
