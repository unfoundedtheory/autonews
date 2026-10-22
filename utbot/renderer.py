"""Unfounded Theory editorial cover: image first, balanced typography, deterministic layout.

Use a genuine, reviewed source image. Do not treat generated artwork as science photography.
Refer to docs/DESIGN_SKILL.md before changing the template.
"""
from __future__ import annotations

from pathlib import Path
import re
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .accent import accent_for_hook, cover_accent_phrases

WIDTH, HEIGHT = 1080, 1350
GREEN = "#8FFF00"
WHITE = "#FFFFFF"
SIDE_MARGIN = 56
BOTTOM_MARGIN = 56
MARGIN = SIDE_MARGIN              # backward-compatible horizontal safe area
LAYOUT_STYLE = "fixed_reference_logo_balanced_edge_coverage_v12"
# Owner's 1080×1350 reference: logo is locked at (402,900)-(678,948).
# Headline ALWAYS begins beneath it, at y=981. Only font size and
# inter-line pitch may adapt to the available space. Safe edge gap: 56px.
BADGE_BOX = (402, 900, 678, 948)
HEADLINE_TOP = 981
HEADLINE_BOTTOM = HEIGHT-BOTTOM_MARGIN
TRACKING_EM = -0.047             # League Spartan letter spacing -47
MIN_EDITORIAL_FONT_PX = 70       # Shorten editorial copy, never silently publish tiny lettering.
LINE_SPACING = 1.08              # optically relaxed compared with prior 1.05
WORD_GAP_EM = 0.20               # distinct visual spaces remain between whole words
DEFAULT_BADGE = Path(__file__).resolve().parent / "assets" / "reference_badge.png"
# Genuine Google Fonts League Spartan variable face: use the Bold 700 axis.
# A bundled font is essential: Vercel's minimal runtime has no dependable OS fonts.
DEFAULT_HEADLINE_FONT = Path(__file__).resolve().parent / "assets" / "LeagueSpartan-Variable.ttf"


@lru_cache(maxsize=100)
def _font(size: int, font_path: str | None = None):
    # An old BRAND_FONT_PATH must not silently override the approved brand.
    # Both local and Vercel render with the exact bundled League Spartan Bold.
    candidates = [DEFAULT_HEADLINE_FONT]
    if font_path and Path(font_path).is_file():
        custom = ImageFont.truetype(font_path,size)
        if 'league spartan' in custom.getname()[0].casefold():
            candidates.insert(0,Path(font_path))
    for candidate in candidates:
        if candidate.is_file():
            face=ImageFont.truetype(candidate,size)
            try:
                face.set_variation_by_axes([700])
            except OSError:
                # A static Bold League Spartan file also meets the brand rule.
                if 'bold' not in face.getname()[1].casefold():
                    continue
            return face
    # Never silently switch to Pillow's rounded Aileron default. The operator
    # would approve a different cover from the reference brand.
    raise RuntimeError('Font League Spartan tidak ditemukan dalam paket.')


def font_readability_status(font_path: str | None = None):
    """Report actual glyph size so deploy/readiness can catch tiny serverless fonts."""
    font = _font(80, font_path)
    cap_height = _ink_height(font)
    family=font.getname()[0]
    return {'requested_px':80, 'actual_font_px':font.size,
            'font_family':family,
            'cap_height_px':cap_height, 'readable':cap_height>=46}


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
    # Use kerning-aware full-word measurement so our manual tracking matches
    # League Spartan's real glyph widths, not isolated-letter approximations.
    return (font.getlength(word)
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


def _balanced_wrap(draw, words, font, max_width, max_lines=5, exact_lines=None, min_lines=3):
    """Dynamic programming for coherent lines with measured kerning and tracking."""
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
                  if end == n and min_lines <= count <= max_lines
                  and (exact_lines is None or count == exact_lines)]
    if not candidates:
        return []
    return [' '.join(line) for line in min(candidates, key=lambda x:x[0])[1]]


def _ink_height(font):
    # Stable uppercase cap-height independent of punctuation in a particular line.
    bbox = font.getbbox('HM', anchor='la')
    return bbox[3]-bbox[1]


def _reference_line_pitch(font):
    """Scale leading with the actual League Spartan cap height.

    Keep 1.08 proportional for headlines with different dynamic font sizes,
    rather than setting a fixed inter-line pixel distance.
    """
    return round((_ink_height(font)+9)*LINE_SPACING)


def _headline_layout(draw, highlight, font_path=None, max_width=WIDTH-2*MARGIN):
    """Prioritize safe 56px margins, then maximum font, then line count.

    All counts 2–5 compete at EACH candidate font size. The first feasible
    size wins; four lines never justify a smaller font. The logo position,
    headline start, and full safe area remain unchanged.
    """
    words=_headline_tokens(highlight)
    if not words:
        raise ValueError('Headline kosong.')
    # PRIORITY 1: all rendered glyphs must remain within the 56px safe area.
    # PRIORITY 2: the LARGEST feasible font wins, irrespective of line count.
    # PRIORITY 3: only among equal-size fits should line balance, edge usage,
    # and the optional four-line preference decide the winner.
    # Checking all candidates at each size also prevents space-coverage
    # weights from selecting an unnecessarily small font.
    for size in range(144,47,-2):
        font=_font(size,font_path)
        pitch=_reference_line_pitch(font)
        cap=_ink_height(font)
        feasible=[]
        for count in range(2,6):
            if len(words)<count:
                continue
            height=(count-1)*pitch+cap
            if HEADLINE_TOP+height>HEADLINE_BOTTOM:
                continue
            lines=_balanced_wrap(draw,words,font,max_width,
                                 max_lines=count,exact_lines=count,
                                 min_lines=2)
            if len(lines)!=count:
                continue
            widths=[_line_width(draw,line,font) for line in lines]
            if any(width>max_width for width in widths):
                continue
            if len(words)>3 and len(lines[-1].split())==1:
                continue
            # All options at this font size satisfy the non-negotiable margins.
            # Prefer consistent edge coverage across all lines. A single
            # extra-wide line must not conceal weak, narrow neighboring lines.
            ratios=[w/max_width for w in widths]
            mean=sum(ratios)/count
            weak=min(ratios)
            balance=-sum((ratio-mean)**2 for ratio in ratios)/count
            edge=max(ratios)
            feasible.append(((mean, weak, balance, edge, -abs(count-4)),
                             lines))
        if feasible:
            _,lines=max(feasible,key=lambda pair:pair[0])
            return font,lines,pitch
    raise ValueError('Headline tidak muat dengan margin aman 56px; persingkat melalui Telegram.')


def headline_font_size(highlight: str, font_path: str | None = None):
    """Actual pixel font size after flexible line-count width/height fitting.

    A headline can technically fit yet look tiny if the copy is verbose.
    The newsroom should suggest a shorter evidence-checked hook in that case.
    """
    canvas=ImageDraw.Draw(Image.new('RGB', (1, 1)))
    font, _, _=_headline_layout(canvas, highlight, font_path)
    return font.size


@lru_cache(maxsize=256)
def require_cover_fit(highlight: str, font_path: str | None = None):
    """Use identical flexible cover geometry as render, without downloading photos."""
    if not highlight or len(highlight.strip()) > 245:
        raise ValueError("Highlight kosong atau terlalu panjang")
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    _, lines, _ = _headline_layout(draw, highlight, font_path)
    return tuple(lines)


def cover_fits(highlight: str, font_path: str | None = None):
    try:
        require_cover_fit(highlight, font_path)
        return True
    except ValueError:
        return False


def _accent_check(word: str, accent: set[str]):
    normalized = re.sub(r"[^\w-]", "", word.upper(), flags=re.UNICODE)
    return normalized in accent


def _draw_word_tracked(draw, word, x, y, font, color):
    """Draw at one fixed baseline. Glyph kerning applies only between characters."""
    cursor = x
    style=font.getname()[1].lower()
    # When a serverless host lacks condensed bold fonts, Pillow uses its
    # bundled scalable regular family; moderate stroke restores headline
    # hierarchy without raster stretching. True bold fonts need no stroke.
    # League Spartan Black requires no extra stroke over its real geometry.
    # Strokes would soften and round the otherwise square letter terminals.
    family=font.getname()[0].lower()
    stroke=0 if ('league spartan' in family or 'bold' in style or 'black' in style
                 or 'heavy' in style) else min(3,max(1,round(font.size*0.035)))
    for index,ch in enumerate(word):
        draw.text((round(cursor),round(y)), ch, font=font, fill=color,
                  stroke_width=stroke, stroke_fill=color, anchor='la')
        # Difference of full-prefix lengths includes kerning between glyphs.
        cursor += (font.getlength(word[:index+1])
                   - font.getlength(word[:index]) + _letter_tracking(font))
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


def _headline_vertical_shift(font, pitch):
    """Legacy compatibility: the owner reference forbids any vertical shift."""
    return 0


def _title_draw_y(font, line_index, pitch):
    """Keep the first ink row anchored below the fixed logo."""
    return HEADLINE_TOP - font.getbbox('HM', anchor='la')[1] + line_index*pitch


def _draw_badge(img, logo_path=None, *, vertical_shift=0):
    """Logo stays at the owner's reference coordinates for every headline."""
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
        draw.text(((left+right)//2,(top+bottom)//2),'unfounded theory',
                  font=_font(26),fill=WHITE,anchor='mm')


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
    if min(img.size) < 600:
        raise ValueError("Foto terlalu kecil (sisi < 600px); pilih resolusi lebih tinggi atau tinjauan editor")
    if not highlight or len(highlight.strip()) > 245:
        raise ValueError("Highlight kosong atau terlalu panjang")
    img = _place_photo(img, photo_focus)
    black, gradient = _fade_gradient()
    img.paste(black, (0, 0), gradient)
    draw = ImageDraw.Draw(img)

    # Lock the logo at reference y=900–948 and start text at y=981.
    # Let 2–5 lines compete by space coverage; keep 56px safety margins.
    font, lines, pitch = _headline_layout(draw, highlight, font_path)
    if _ink_height(font) + HEADLINE_TOP + (len(lines)-1)*pitch > HEADLINE_BOTTOM:
        raise ValueError('Headline overflow: requires editorial revision')
    _draw_badge(img, logo_path)
    accent = set()
    # Re-evaluate even existing legacy accents: the old bot could persist
    # only "LINGKARAN" and lose the key phrase "CAHAYA AURORAL UTUH".
    for phrase in cover_accent_phrases(highlight,accent_words):
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


def render_carousel_cover(input_image, highlight, outpath, logo_path=None, font_path=None):
    """Distinct carousel cover: small logo top-left, headline above bottom menu-safe area.

    Existing single-photo fixed logo and typography remain unchanged.
    """
    image = Image.open(input_image)
    if min(image.size) < 600:
        raise ValueError("Foto carousel di bawah 600 piksel")
    if not highlight or len(highlight.strip()) > 245:
        raise ValueError("Highlight carousel tidak valid")
    image = _place_photo(image, (0.5, 0.43))
    # Only the lower third is shaded; preserve the subject and sky above.
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    from PIL import Image as PILImage
    shade = PILImage.new("L", (1, HEIGHT))
    for y in range(HEIGHT):
        alpha = max(0, min(205, int(205 * (y - 680) / 450)))
        shade.putpixel((0, y), alpha)
    shade = shade.resize((WIDTH, HEIGHT))
    overlay.paste(PILImage.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255)), (0, 0), shade)
    image = PILImage.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    logo = Path(logo_path) if logo_path else DEFAULT_BADGE
    if logo.is_file():
        badge = Image.open(logo).convert("RGBA")
        badge.thumbnail((260, 90), Image.Resampling.LANCZOS)
        image.paste(badge, (SIDE_MARGIN, SIDE_MARGIN), badge)
    draw = ImageDraw.Draw(image)
    words = highlight.strip().split()
    fitted = None
    # "Above menu": headline occupies lower-middle; no headline under Instagram controls.
    for size in range(102, 39, -2):
        face = _font(size, font_path)
        max_width = WIDTH - SIDE_MARGIN * 2
        lines = []
        line = ""
        for word in words:
            proposal = (line + " " + word).strip()
            if draw.textbbox((0, 0), proposal, font=face)[2] <= max_width:
                line = proposal
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        pitch = int(size * 1.08)
        if len(lines) <= 6 and len(lines) * pitch <= 380:
            fitted = (face, lines, pitch)
            break
    if fitted is None:
        raise ValueError("Highlight carousel terlalu panjang untuk margin aman")
    face, lines, pitch = fitted
    top = 1050 - pitch * len(lines)
    for index, line in enumerate(lines):
        draw.text((SIDE_MARGIN, top + index * pitch), line,
                  font=face, fill=WHITE, stroke_width=1)
    target = Path(outpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "JPEG", quality=94, optimize=True)
    return str(target)
