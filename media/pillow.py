import asyncio
from concurrent.futures import ProcessPoolExecutor

_executor = ProcessPoolExecutor(max_workers=2)

THUMB_W = 1080
THUMB_H = 1920


def _add_text_overlay_sync(image_path: str, text: str, output_path: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGB")
    img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    # MrBeast style: large Impact, all-caps, centered lower-third
    font_size = max(80, THUMB_H // 12)
    font = None
    for font_name in [
        "Impact", "impact",
        "/usr/share/fonts/TTF/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_name, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=font_size)

    text = text.upper()

    # Word-wrap to fit width (80px margin each side)
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

    line_height = font_size + 16
    total_text_h = len(lines) * line_height

    # Semi-transparent dark bar behind text
    bar_pad = 32
    bar_h = total_text_h + bar_pad * 2
    bar_y = THUMB_H - bar_h - 80

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(overlay)
    bar_draw.rectangle([(0, bar_y), (THUMB_W, bar_y + bar_h)], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    y_start = bar_y + bar_pad
    for i, line in enumerate(lines):
        y = y_start + i * line_height
        cx = THUMB_W // 2

        # Thick black outline
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if dx == 0 and dy == 0:
                    continue
                draw.text((cx + dx, y + dy), line, font=font, fill=(0, 0, 0), anchor="mt")

        # Yellow inner glow
        for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            draw.text((cx + dx, y + dy), line, font=font, fill=(255, 220, 0), anchor="mt")

        # White main text
        draw.text((cx, y), line, font=font, fill=(255, 255, 255), anchor="mt")

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
