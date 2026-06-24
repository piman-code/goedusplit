from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    Image = ImageDraw = ImageFont = ImageFilter = None


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "app_icon"
ICONSET_DIR = ASSET_DIR / "goedusplit.iconset"
SIZE = 1024
SCALE = 3


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            if candidate:
                return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(size):
            px[x, y] = (*color, 255)
    return img


def _rounded_background(draw_img: Image.Image, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> ImageDraw.ImageDraw:
    size = draw_img.size[0]
    radius = round(size * 0.23)
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    margin = round(size * 0.055)
    sd.rounded_rectangle(
        [margin, margin + round(size * 0.02), size - margin, size - margin + round(size * 0.02)],
        radius=radius,
        fill=(0, 0, 0, 70),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(round(size * 0.025)))
    draw_img.alpha_composite(shadow)

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([margin, margin, size - margin, size - margin], radius=radius, fill=255)
    grad = _gradient(size, top, bottom)
    draw_img.alpha_composite(Image.composite(grad, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))
    return ImageDraw.Draw(draw_img)


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: tuple[int, int, int, int], width: int) -> None:
    draw.line(points, fill=fill, width=width, joint="curve")
    r = width // 2
    for x, y in points:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def split_grid_icon() -> Image.Image:
    s = SIZE * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = _rounded_background(img, (18, 83, 78), (50, 145, 132))

    panel = [round(s * 0.17), round(s * 0.21), round(s * 0.83), round(s * 0.79)]
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([panel[0], panel[1] + round(s * 0.018), panel[2], panel[3] + round(s * 0.018)], radius=round(s * 0.055), fill=(0, 0, 0, 70))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(round(s * 0.018))))
    draw.rounded_rectangle(panel, radius=round(s * 0.055), fill=(248, 253, 251, 255))

    x0, y0, x1, y1 = panel
    header_h = round(s * 0.09)
    draw.rounded_rectangle([x0, y0, x1, y0 + header_h], radius=round(s * 0.055), fill=(236, 248, 245, 255))
    draw.rectangle([x0, y0 + header_h - round(s * 0.03), x1, y0 + header_h], fill=(236, 248, 245, 255))

    labels = ["A", "B", "C", "D", "E"]
    colors = [(48, 127, 106), (81, 157, 135), (114, 177, 158), (168, 197, 185), (215, 224, 221)]
    font = _font(round(s * 0.052), True)
    for i, label in enumerate(labels):
        cx = x0 + round(s * 0.12) + i * round(s * 0.105)
        cy = y0 + round(header_h * 0.52)
        draw.ellipse([cx - round(s * 0.026), cy - round(s * 0.026), cx + round(s * 0.026), cy + round(s * 0.026)], fill=colors[i])
        bbox = draw.textbbox((0, 0), label, font=font)
        draw.text((cx - (bbox[2] - bbox[0]) / 2, cy - (bbox[3] - bbox[1]) / 2 - round(s * 0.003)), label, font=font, fill=(255, 255, 255, 255))

    left = x0 + round(s * 0.08)
    right = x1 - round(s * 0.08)
    top = y0 + header_h + round(s * 0.065)
    row_h = round(s * 0.075)
    for i in range(5):
        y = top + i * row_h
        fill = (245, 250, 249, 255) if i % 2 == 0 else (232, 244, 241, 255)
        draw.rounded_rectangle([left, y, right, y + round(s * 0.048)], radius=round(s * 0.022), fill=fill)
        bar_w = round((right - left) * (0.88 - i * 0.12))
        draw.rounded_rectangle([left, y, left + bar_w, y + round(s * 0.048)], radius=round(s * 0.022), fill=colors[i])

    split_x = x0 + round((x1 - x0) * 0.67)
    draw.line([split_x, top - round(s * 0.035), split_x, y1 - round(s * 0.08)], fill=(231, 170, 61, 255), width=round(s * 0.018))
    draw.polygon(
        [
            (split_x - round(s * 0.045), top - round(s * 0.035)),
            (split_x + round(s * 0.045), top - round(s * 0.035)),
            (split_x, top + round(s * 0.035)),
        ],
        fill=(231, 170, 61, 255),
    )

    _line(
        draw,
        [
            (x0 + round(s * 0.16), y1 - round(s * 0.14)),
            (x0 + round(s * 0.31), y1 - round(s * 0.18)),
            (x0 + round(s * 0.45), y1 - round(s * 0.125)),
            (x0 + round(s * 0.59), y1 - round(s * 0.20)),
        ],
        (42, 119, 112, 255),
        round(s * 0.025),
    )

    return img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def ox_icon() -> Image.Image:
    s = SIZE * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = _rounded_background(img, (23, 48, 60), (41, 119, 112))
    card = [round(s * 0.18), round(s * 0.2), round(s * 0.82), round(s * 0.8)]
    draw.rounded_rectangle(card, radius=round(s * 0.06), fill=(250, 253, 252, 255))

    x0, y0, x1, y1 = card
    levels = ["A", "B", "C", "D", "E"]
    font = _font(round(s * 0.062), True)
    for i, level in enumerate(levels):
        y = y0 + round(s * 0.11) + i * round(s * 0.095)
        draw.text((x0 + round(s * 0.07), y - round(s * 0.035)), level, font=font, fill=(37, 112, 104, 255))
        for j in range(4):
            cx = x0 + round(s * 0.2) + j * round(s * 0.115)
            r = round(s * 0.027)
            on = j < 4 - max(i - 1, 0)
            if on:
                draw.ellipse([cx - r, y - r, cx + r, y + r], outline=(47, 135, 116, 255), width=round(s * 0.013))
            else:
                draw.line([cx - r, y - r, cx + r, y + r], fill=(198, 76, 71, 255), width=round(s * 0.014))
                draw.line([cx - r, y + r, cx + r, y - r], fill=(198, 76, 71, 255), width=round(s * 0.014))

    _line(
        draw,
        [
            (x0 + round(s * 0.14), y1 - round(s * 0.12)),
            (x0 + round(s * 0.34), y1 - round(s * 0.18)),
            (x0 + round(s * 0.5), y1 - round(s * 0.12)),
            (x0 + round(s * 0.62), y1 - round(s * 0.22)),
        ],
        (226, 166, 54, 255),
        round(s * 0.024),
    )
    return img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def analysis_icon() -> Image.Image:
    s = SIZE * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = _rounded_background(img, (28, 68, 83), (42, 119, 112))

    base = [round(s * 0.2), round(s * 0.22), round(s * 0.8), round(s * 0.78)]
    draw.rounded_rectangle(base, radius=round(s * 0.065), fill=(245, 251, 250, 255))
    x0, y0, x1, y1 = base
    chart = [x0 + round(s * 0.095), y0 + round(s * 0.1), x1 - round(s * 0.095), y1 - round(s * 0.105)]
    for i in range(4):
        y = chart[1] + i * round((chart[3] - chart[1]) / 3)
        draw.line([chart[0], y, chart[2], y], fill=(213, 228, 225, 255), width=round(s * 0.006))
    bars = [0.82, 0.7, 0.58, 0.45, 0.32]
    colors = [(40, 120, 111), (61, 149, 128), (118, 181, 161), (226, 166, 54), (196, 76, 71)]
    bar_w = round(s * 0.055)
    gap = round(s * 0.05)
    bx = chart[0] + round(s * 0.04)
    for i, h in enumerate(bars):
        bh = round((chart[3] - chart[1]) * h)
        draw.rounded_rectangle([bx, chart[3] - bh, bx + bar_w, chart[3]], radius=round(s * 0.018), fill=colors[i])
        bx += bar_w + gap

    draw.arc([x0 + round(s * 0.25), y0 + round(s * 0.12), x1 - round(s * 0.07), y1 - round(s * 0.08)], start=205, end=320, fill=(226, 166, 54, 255), width=round(s * 0.018))
    return img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def _write_iconset(base: Image.Image) -> None:
    if ICONSET_DIR.exists():
        shutil.rmtree(ICONSET_DIR)
    ICONSET_DIR.mkdir(parents=True)
    specs = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    for name, px in specs:
        base.resize((px, px), Image.Resampling.LANCZOS).save(ICONSET_DIR / name)


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    existing_icon = ASSET_DIR / "goedusplit.ico"
    existing_png = ASSET_DIR / "goedusplit.png"
    if Image is None:
        if existing_icon.exists() and existing_png.exists():
            print("Pillow is not installed; keeping existing Windows icon assets.")
            return 0
        print("Pillow is required to generate app icons. Install requirements.txt first.", file=sys.stderr)
        return 1

    variants = [
        ("01-split-grid", split_grid_icon()),
        ("02-ox-judgement", ox_icon()),
        ("03-analysis-bars", analysis_icon()),
    ]
    for name, image in variants:
        image.save(ASSET_DIR / f"{name}.png")

    selected = variants[0][1]
    selected.save(ASSET_DIR / "goedusplit.png")
    selected.save(
        ASSET_DIR / "goedusplit.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    preview = Image.new("RGBA", (SIZE * 3, SIZE + 160), (246, 250, 249, 255))
    draw = ImageDraw.Draw(preview)
    label_font = _font(54, True)
    labels = ["01 Split Grid", "02 O/X", "03 Analysis"]
    for i, (label, image) in enumerate(zip(labels, [v[1] for v in variants], strict=True)):
        x = i * SIZE
        preview.alpha_composite(image.resize((820, 820), Image.Resampling.LANCZOS), (x + 102, 70))
        bbox = draw.textbbox((0, 0), label, font=label_font)
        draw.text((x + (SIZE - (bbox[2] - bbox[0])) / 2, 930), label, font=label_font, fill=(31, 48, 53, 255))
    preview.convert("RGB").save(ASSET_DIR / "preview-sheet.png", quality=95)

    if sys.platform == "darwin":
        _write_iconset(selected)
        icns_path = ASSET_DIR / "goedusplit.icns"
        try:
            subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(icns_path)], check=True)
        except subprocess.CalledProcessError:
            if icns_path.exists():
                print(f"warning: iconutil failed; keeping existing {icns_path}")
            else:
                print("warning: iconutil failed and no .icns file exists; app will build without a fresh macOS icon")

    print(f"wrote {ASSET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
