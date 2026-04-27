import asyncio
from concurrent.futures import ProcessPoolExecutor

_executor = ProcessPoolExecutor(max_workers=2)

# Thumbnail output dimensions
THUMB_W = 1280
THUMB_H = 720


def _add_text_overlay_sync(image_path: str, text: str, output_path: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGB")
    # Always output at standard thumbnail resolution
    img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    # Large Impact font — 1/10th of height, min 60px
    font_size = max(60, THUMB_H // 10)
    font = None
    for font_name in ["Impact", "impact", "/usr/share/fonts/TTF/Impact.ttf",
                       "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf"]:
        try:
            font = ImageFont.truetype(font_name, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=font_size)

    text = text.upper()

    # Wrap text to fit width (leaving 80px margin each side)
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > THUMB_W - 160:
            if current:
                lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    line_height = font_size + 12
    total_text_h = len(lines) * line_height
    bar_padding = 24
    bar_h = total_text_h + bar_padding * 2

    # Dark semi-transparent bar at bottom third
    bar_y = THUMB_H - bar_h - 40
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(overlay)
    bar_draw.rectangle([(0, bar_y), (THUMB_W, bar_y + bar_h)], fill=(0, 0, 0, 180))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Draw text centred on bar
    y_start = bar_y + bar_padding
    for i, line in enumerate(lines):
        y = y_start + i * line_height
        # Thick black outline (8 directions)
        for dx in [-3, -2, -1, 0, 1, 2, 3]:
            for dy in [-3, -2, -1, 0, 1, 2, 3]:
                if dx == 0 and dy == 0:
                    continue
                draw.text((THUMB_W // 2 + dx, y + dy), line,
                          font=font, fill=(0, 0, 0), anchor="mt")
        # Yellow glow pass
        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            draw.text((THUMB_W // 2 + dx, y + dy), line,
                      font=font, fill=(255, 220, 0), anchor="mt")
        # White main text
        draw.text((THUMB_W // 2, y), line, font=font, fill=(255, 255, 255), anchor="mt")

    img.save(output_path, "JPEG", quality=92)


async def add_text_overlay(image_path: str, text: str, output_path: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor,
        _add_text_overlay_sync,
        image_path,
        text,
        output_path,
    )
