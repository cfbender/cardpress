"""Typeset a card face as a 1-bit image for a thermal printer.

A thermal head prints black dots only, so a photo of the real card comes out as
mud. The card is re-typeset instead: name, cost, type line, and rules as crisp
text, and only the art is dithered.
"""

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .scryfall import Face

ART_ASPECT = 457 / 626  # Scryfall art_crop height / width
# How much of the art's height to keep, tried in order until the rules text fits.
ART_CROPS = (1, 0.8, 0.6, 0.45, 0)
COLOR_NAMES = {"W": "WHITE", "U": "BLUE", "B": "BLACK", "R": "RED", "G": "GREEN"}
# Fonts are bundled so a card prints the same on every machine.
FONT_DIR = Path(__file__).parent / "fonts"


@lru_cache
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Word-wrap to a pixel width, keeping the card's own paragraph breaks."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if line and font.getlength(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def _cost(mana_cost: str) -> str:
    """{2}{G/U}{R} -> 2(G/U)R: bare symbols, with multi-letter ones kept together."""
    symbols = re.findall(r"\{([^}]+)\}", mana_cost)
    return "".join(s if len(s) == 1 or s.isdigit() else f"({s})" for s in symbols)


def _dither(art: Image.Image, width: int, height: int) -> Image.Image:
    art = ImageOps.fit(art.convert("L"), (width, height), Image.Resampling.LANCZOS)
    art = ImageOps.autocontrast(art, cutoff=1)
    # Thermal heads print darker than a screen shows, so lift the midtones first.
    art = art.point(lambda value: round(255 * (value / 255) ** 0.75))
    art = art.filter(ImageFilter.UnsharpMask(radius=2, percent=120))
    return art.convert("1")


def render_card(face: Face, art: Image.Image | None, width: int, height: int) -> Image.Image:
    """Draw the face upright at width x height dots. White is 1, black is 0."""
    image = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(image)
    margin = round(width * 0.035)
    inner = width - 2 * margin
    draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=2)

    type_font = _font(round(width * 0.045), bold=True)
    stats_font = _font(round(width * 0.06), bold=True)
    small_font = _font(round(width * 0.034))
    title_height = round(width * 0.058 * 1.35)
    type_height = round(type_font.size * 1.35)
    footer_height = round(stats_font.size * 1.35)

    # Title: shrink the name until it clears the mana cost.
    cost = _cost(face.mana_cost)
    title_size = round(width * 0.058)
    while True:
        title_font = _font(title_size, bold=True)
        name_room = inner - title_font.getlength(cost) - (margin if cost else 0)
        if title_font.getlength(face.name) <= name_room or title_size <= round(width * 0.034):
            break
        title_size -= 1

    # Rules: shrink the text a little, then crop the art, then shrink further.
    text_room = height - 2 * margin - title_height - type_height - footer_height
    largest, comfortable, smallest = (round(width * scale) for scale in (0.045, 0.036, 0.028))
    attempts = [(crop, size) for crop in ART_CROPS[:-1] for size in range(largest, comfortable - 1, -1)]
    attempts += [(crop, size) for crop in ART_CROPS[-2:] for size in range(comfortable - 1, smallest - 1, -1)]
    for crop, size in attempts:
        rules_font = _font(size)
        lines = _wrap(face.rules, rules_font, inner) if face.rules else []
        art_height = round(inner * ART_ASPECT * crop) if art else 0
        line_height = round(size * 1.25)
        if art_height + len(lines) * line_height <= text_room:
            break
    else:
        lines = lines[: text_room // line_height]  # Longer than the card: cut it off rather than overprint.

    y = margin
    draw.text((margin, y), face.name, font=title_font, fill=0)
    draw.text((width - margin, y), cost, font=title_font, fill=0, anchor="ra")
    y += title_height

    if art_height:
        image.paste(_dither(art, inner, art_height), (margin, y))
        draw.rectangle((margin, y, margin + inner - 1, y + art_height - 1), outline=0)
        y += art_height + round(type_height * 0.15)

    draw.text((margin, y), face.type_line, font=type_font, fill=0)
    y += type_height
    for line in lines:
        draw.text((margin, y), line, font=rules_font, fill=0)
        y += line_height

    # A thermal print has no colour, so spell the colours out.
    baseline = height - margin
    draw.text((width - margin, baseline), face.stats, font=stats_font, fill=0, anchor="rs")
    colors = " ".join(COLOR_NAMES[c] for c in face.colors) or "COLORLESS"
    credit = f"{colors} · Illus. {face.artist}" if face.artist else colors
    footer_room = inner - stats_font.getlength(face.stats) - margin
    footer = credit if small_font.getlength(credit) <= footer_room else colors
    draw.text((margin, baseline), footer, font=small_font, fill=0, anchor="ls")
    return image
