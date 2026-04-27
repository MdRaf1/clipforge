import asyncio
from concurrent.futures import ProcessPoolExecutor

_executor = ProcessPoolExecutor(max_workers=2)


def _add_text_overlay_sync(image_path: str, text: str, output_path: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size

    font_size = max(36, width // 18)
    try:
        font = ImageFont.truetype("Impact", font_size)
    except OSError:
        font = ImageFont.load_default()

    # Wrap text to fit width
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > width - 40:
            if current:
                lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    line_height = font_size + 8
    total_height = len(lines) * line_height
    y_start = height - total_height - 30

    for i, line in enumerate(lines):
        y = y_start + i * line_height
        # Black shadow/outline
        for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            draw.text((width // 2 + dx, y + dy), line, font=font, fill="black", anchor="mt")
        draw.text((width // 2, y), line, font=font, fill="white", anchor="mt")

    img.save(output_path, "JPEG", quality=90)


async def add_text_overlay(image_path: str, text: str, output_path: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor,
        _add_text_overlay_sync,
        image_path,
        text,
        output_path,
    )
