"""Unfounded Theory editorial cover: image first, balanced typography, deterministic layout.

Use a genuine, reviewed source image. Do not treat generated artwork as science photography.
Refer to docs/DESIGN_SKILL.md before changing the template.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 1080, 1350
GREEN = "#95F21E"
WHITE = "#FFFFFF"
MARGIN = 56  # Content safe margin; actual reference ink sometimes stops near x=75.
LAYOUT_STYLE = "fixed_editorial_grid_v06"
# Measured directly from SIX supplied 1080×1350 reference posts.
BADGE_BOX = (402, 900, 678, 948)   # exact same badge region on every original cover
HEADLINE_TOP = 981                 # first ink row 977–982 in references
HEADLINE_BOTTOM = 1307            # strict fixed text region; do not push badge up
TRACKING_EM = -0.025              # tighter GLYPHS, never collapse the word gap
WORD_GAP_EM = 0.20               # distinct visual spaces remain between whole words
DEFAULT_BADGE = Path(__file__).resolve().parent / "assets" / "reference_badge.png"


@lru_cache(maxsize=100)
def _font(size: int, font_path: str | None = None):
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [
        font_path,
        windows_fonts / "arialbd.ttf",
        windows_fonts / "bahnschrift.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _letter_tracking(font):
    """Negative *inter-character* tracking. Never applied across words."""
    return font.size * TRACKING_EM


def _word_gap(draw, font):
    """Tighter editorial spacing, still independently visible between words."""
    return max(12.0, font.size * WORD_GAP_EM)


@lru_cache(maxsize=16384)
def _cached_word_width(word, font):
    # Fonts are cached above; individual word metrics are reused across
    # every possible wrap candidate and font size.
    return (sum(font.getlength(ch) for ch in word)
            + max(0, len(word) - 1) * _letter_tracking(font))

def _word_width(draw, word, font):
    return _cached_word_width(word, font)


def line_tokens(words):
    return words.split() if isinstance(words, str) else list(words)


def _line_width(draw, words, font, gap=None):
    tokens = line_tokens(words)
    if not tokens:
        return 0.0
    gap = _word_gap(draw, font) if gap is None else gap
    return sum(_word_width(draw, word, font) for word in tokens) + (len(tokens) - 1) * gap


def _headline_tokens(highlight):
    """Do not wrap inside quoted editorial concepts."""
    return re.findall(r"""['\"“‘][^'\"”’]+['\"”’][,;.!?]?|\S+""", highlight.upper())


def _balanced_wrap(draw, words, font, max_width, max_lines=5):
    """Dynamic programming for 3–5 coherent lines, measured with actual tracking."""
    words = line_tokens(words)
    n = len(words)
    if not n:
        return []
    widths = {(a, b): _line_width(draw, words[a:b], font)
              for a in range(n) for b in range(a + 1, n + 1)}
    widths = {key: w for key, w in widths.items() if w <= max_width}
    states = {(0, 0): (0.0, [])}
    for count in range(1, max_lines + 1):
        for end in range(1, n + 1):
            choices = []
            for start in range(end):
                if (start, count-1) not in states or (start, end) not in widths:
                    continue
                w = widths[(start, end)]
                vacancy = (max_width-w)/max_width
                penalty = vacancy**2
                # Discourage a last line with only one word, or an ultra-short line.
                if end == n and len(words[start:end]) == 1 and n > 3:
                    penalty += 5.0
                elif w < max_width * 0.43:
                    penalty += 0.30
                prev, path = states[(start, count-1)]
                choices.append((prev+penalty, path + [words[start:end]]))
            if choices:
                states[(end, count)] = min(choices, key=lambda v:v[0])
    candidates = [(score+count*.10, path) for (end,count),(score,path) in states.items()
                  if end == n and 3 <= count <= max_lines]
    if not candidates:
        return []
    return [' '.join(line) for line in min(candidates, key=lambda x:x[0])[1]]


def _ink_height(font):
    # Stable uppercase cap-height independent of punctuation in a particular line.
    bbox = font.getbbox('HM', anchor='la')
    return bbox[3]-bbox[1]


def _headline_layout(draw, highlight, font_path=None, max_width=WIDTH-2*MARGIN):
    """Use the owner-approved four-line grid; never squeeze to five lines."""
    words = _headline_tokens(highlight)
    for size in range(104, 57, -2):
        font = _font(size, font_path)
        lines = _balanced_wrap(draw, words, font, max_width, max_lines=4)
        pitch = round(size * .985)
        if (len(lines) == 4 and
            HEADLINE_TOP + (len(lines)-1)*pitch + _ink_height(font) <= HEADLINE_BOTTOM
            and all(_line_width(draw, line, font) <= max_width for line in lines)
            and (len(lines[-1].split())>1 or len(words)<4)):
            return font, lines, pitch
    raise ValueError('Highlight tidak muat dalam tepat empat baris; minta revisi melalui Telegram')


def _accent_check(word: str, accent: set[str]):
    normalized = re.sub(r"[^\w-]", "", word.upper(), flags=re.UNICODE)
    return normalized in accent


def _draw_word_tracked(draw, word, x, y, font, color):
    """Draw at one fixed baseline. Glyph kerning applies only between characters."""
    cursor = x
    for ch in word:
        draw.text((round(cursor),round(y)), ch, font=font, fill=color,
                  stroke_width=0, anchor='la')
        cursor += draw.textlength(ch, font=font) + _letter_tracking(font)
    return _word_width(draw, word, font)


def _draw_title_line(draw, line, y, font, accent):
    """Draw with identical geometry to wrap calculation, no fake outline/glow."""
    tokens = line_tokens(line)
    gap = _word_gap(draw, font)
    width = _line_width(draw, tokens, font, gap)
    if width > WIDTH-2*MARGIN+.01:
        raise ValueError('Headline melewati margin aman')
    x = (WIDTH-width)/2
    for i, word in enumerate(tokens):
        color = GREEN if _accent_check(word,accent) else WHITE
        x += _draw_word_tracked(draw,word,x,y,font,color)
        if i < len(tokens)-1:
            x += gap
    return (WIDTH-width)/2, (WIDTH+width)/2


def _title_draw_y(font, line_index, pitch):
    # PIL's ascender origin differs from actual visible ink top. Anchor *ink* at
    # HEADLINE_TOP regardless of number of lines or font size.
    return HEADLINE_TOP - font.getbbox('HM', anchor='la')[1] + line_index*pitch


def _draw_badge(img, logo_path=None):
    """No text-driven movement: center remains x=540, y=924 on ALL posts."""
    left, top, right, bottom = BADGE_BOX
    logo_file = Path(logo_path) if logo_path else DEFAULT_BADGE
    if logo_file.is_file():
        badge = Image.open(logo_file).convert('RGBA')
        badge.thumbnail((right-left,bottom-top), Image.Resampling.LANCZOS)
        loc = ((left+right-badge.width)//2,(top+bottom-badge.height)//2)
        img.paste(badge, loc, badge)
    else:
        # Fall back to a fixed-size vector badge only if extracted logo unavailable.
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((left,top,right,bottom),radius=24,
                               outline=WHITE,width=3)
        draw.text((540,924),'unfounded theory',font=_font(26),
                  fill=WHITE,anchor='mm')


def _place_photo(source: Image.Image, focus: tuple[float, float]):
    focus_x, focus_y = focus
    if not (0 <= focus_x <= 1 and 0 <= focus_y <= 1):
        raise ValueError("photo_focus must be a normalized (x, y) pair")
    # Crop only where needed to keep important object in frame; no distortion.
    return ImageOps.fit(source.convert("RGB"), (WIDTH, HEIGHT),
                        method=Image.Resampling.LANCZOS,
                        centering=(focus_x, focus_y))


def _fade_gradient():
    """Transparent top, smoothly deepening black at the text, never a flat overlay."""
    stops = [(0, 0), (450, 0), (690, 12), (800, 38),
             (910, 116), (1010, 197), (1150, 250), (1350, 255)]
    ramp = Image.new("L", (1, HEIGHT))
    for (a, v1), (b, v2) in zip(stops, stops[1:]):
        for y in range(a, b):
            t = (y - a) / (b - a)
            smooth = t * t * (3 - 2 * t)
            ramp.putpixel((0, y), round(v1 + (v2 - v1) * smooth))
    ramp.putpixel((0, HEIGHT - 1), 255)
    mask = ramp.resize((WIDTH, HEIGHT))
    return Image.new("RGB", (WIDTH, HEIGHT), "#000000"), mask


def render(input_image, highlight, outpath, accent_words=None, logo_path=None,
           font_path=None, photo_focus=(0.5, 0.43), source_type="documentary"):
    """Render an approved cover, without changing the underlying scientific photo.

    ``source_type='illustration'`` adds an explicit disclosure label.
    Source rights / scientific image identity are validated elsewhere by editor.
    """
    if source_type not in ("documentary", "illustration"):
        raise ValueError("source_type must be documentary or illustration")
    img = Image.open(input_image)
    if min(img.size) < 800:
        raise ValueError("Foto terlalu kecil untuk cover 1080 × 1350; pilih resolusi tinggi")
    if not highlight or len(highlight.strip()) > 245:
        raise ValueError("Highlight kosong atau terlalu panjang")
    img = _place_photo(img, photo_focus)
    black, gradient = _fade_gradient()
    img.paste(black, (0, 0), gradient)
    draw = ImageDraw.Draw(img)

    # Reference geometry fixed: badge y900–948 and first title ink y981.
    # All approved headlines use FOUR lines in the exact same fixed region.
    font, lines, pitch = _headline_layout(draw, highlight, font_path)
    if _ink_height(font) + HEADLINE_TOP + (len(lines)-1)*pitch > HEADLINE_BOTTOM:
        raise ValueError('Headline overflow: requires editorial revision')
    _draw_badge(img, logo_path)
    accent = set()
    for phrase in accent_words or []:
        accent.update(re.sub(r"[^\w\s-]", "", phrase.upper()).split())
    for i, line in enumerate(lines):
        _draw_title_line(draw, line, _title_draw_y(font,i,pitch), font, accent)

    if source_type == "illustration":
        note_font = _font(18)
        draw.text((MARGIN, 38), "ILUSTRASI • BUKAN FOTO OBSERVASI",
                  font=note_font, fill=WHITE)

    outpath = Path(outpath)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    img.save(outpath, "JPEG", quality=95, optimize=True, subsampling=0)
    return str(outpath)
