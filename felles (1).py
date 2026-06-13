"""Shared constants, palette, helpers, and base widgets for infotavle-im."""

import os
import re
import threading
import datetime
from io import BytesIO
from datetime import timezone, timedelta
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

# === Timezone setup ===
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Oslo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=1))

# === Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# === Palette (PSD-extracted) ===
PAGE_BG       = '#3D1053'
PANEL_YELLOW  = '#E9B647'
PANEL_PURPLE  = '#4A1366'
HEADING_YELLOW= '#FCC745'
TITLE_YELLOW  = '#E9B647'
INK_PURPLE    = '#3D1053'
WHITE         = '#FFFFFF'
GOLD_HILITE   = '#FFD349'
TEAL          = '#00816D'
DISCORD_CARD  = '#2B2D31'
DISCORD_AUTHOR= '#FCC745'
DISCORD_TEXT  = '#DBDEE1'
DISCORD_TIME  = '#949BA4'
BIRTHDAY_TODAY = '#C62828'


class Surface:
    """Per-surface palette: background, heading, accent, radius."""
    def __init__(self, bg, heading, body, subtext, accent, rounded=True, radius_px=12):
        self.bg = bg
        self.heading = heading
        self.body = body
        self.subtext = subtext
        self.accent = accent
        self.rounded = rounded
        self.radius_px = radius_px


PAGE_SURFACE  = Surface(PAGE_BG, HEADING_YELLOW, WHITE, WHITE, TEAL, rounded=False)
YELLOW_SURFACE = Surface(PANEL_YELLOW, INK_PURPLE, INK_PURPLE, INK_PURPLE, TEAL)
ORDEN_SURFACE  = Surface(PANEL_PURPLE, TITLE_YELLOW, WHITE, WHITE, GOLD_HILITE)

# === Scaling ===
screen_w = None
S = 1.0  # set after root created

# === R6: Pillow-rendered rounded image cache ===
_img_cache = {}


def rounded_image(w, h, radius, fill_hex):
    """Render a rounded rectangle as a Pillow RGBA image with transparent corners."""
    key = (w, h, radius, fill_hex)
    if key in _img_cache:
        return _img_cache[key]
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill_hex)
    photo = ImageTk.PhotoImage(img)
    _img_cache[key] = photo
    return photo


def px(ref_px):
    """Scale a PSD-reference pixel value by S."""
    return max(1, round(ref_px * S))


def font(ref_px, weight='normal', family=None):
    """Return a Tkinter font tuple scaled by S. Negative size = device pixels."""
    if family is None:
        family = resolve_font_family(weight)
    tk_weight = 'bold' if weight in ('bold', 'xBold') else 'normal'
    return (family, -px(ref_px), tk_weight)


def resolve_font_family(weight='normal'):
    """Try Widescreen fonts, fall back to Arial."""
    candidates = {
        'xBold': ['Widescreen XBold', 'Widescreen Bold', 'Arial'],
        'bold':  ['Widescreen Bold', 'Arial'],
        'normal': ['Widescreen Light', 'Widescreen', 'Arial'],
    }
    for name in candidates.get(weight, ['Arial']):
        return name
    return 'Arial'


def log(msg):
    """Append timestamped message to infoboard.log."""
    now = datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(SCRIPT_DIR, "infoboard.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] {msg}\n")


# ===========================================================================
# Emoji / symbol rendering
#
# Tkinter cannot render colour emoji at all (no COLR/CBDT support), and a
# bare Raspberry Pi is missing many symbol glyphs, so any emoji written as
# plain widget text shows up as a "tofu" box (□). To guarantee that ANY
# character used anywhere on the board renders, we:
#   * route emoji through Twemoji PNGs (full Unicode emoji coverage), and
#   * draw all other text with a wide-coverage TTF (DejaVu) via Pillow,
# then hand the result back as a single image. Genuinely missing glyphs fall
# back to the TTF glyph instead of a blank box.
#
# render_text_image()  -> wrapped multi-line text + inline emoji as one photo
#                         (drop-in for a tk.Label image; keeps reqheight sane)
# emoji_photo()         -> a single emoji as a photo (for icon-sized use)
# ===========================================================================

# Set these to your Widescreen .ttf files for visual consistency; otherwise
# DejaVu is used (covers Latin + Norwegian + most symbols).
WIDESCREEN_TTF = None
WIDESCREEN_BOLD_TTF = None

# Optional local mirror of the Twemoji 72x72 PNG set. If present, used before
# the CDN so the board still renders emoji with no internet (kiosk-safe).
TWEMOJI_LOCAL_DIR = os.path.join(SCRIPT_DIR, "assets", "twemoji")
_TWEMOJI_CDN = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{}.png"

# Emoji code-point ranges. Plain arrows (U+2190-21FF) are intentionally left
# OUT so "→" keeps rendering as crisp text.
_EMOJI_RANGES = (
    "\U0001F000-\U0001FAFF"   # pictographic planes (most emoji)
    "\U00002600-\U000026FF"   # misc symbols: weather, ballot boxes
    "\U00002700-\U000027BF"   # dingbats
    "\U00002B00-\U00002BFF"   # misc symbols & arrows, stars
    "\U00002300-\U000023FF"   # technical: alarm clock, hourglass
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
)
_EMOJI_BASE = f"[{_EMOJI_RANGES}]"
_EMOJI_MOD = "[\U0001F3FB-\U0001F3FF\U0000FE0E\U0000FE0F\U000020E3]"
_EMOJI_CLUSTER = re.compile(
    f"(?:{_EMOJI_BASE}{_EMOJI_MOD}*(?:\u200D{_EMOJI_BASE}{_EMOJI_MOD}*)*"
    f"|[0-9#*]\uFE0F?\u20E3)"
)

_remote_img_lock = threading.Lock()
_remote_img_cache = {}     # url -> PIL.Image (RGBA) | None
_emoji_raw_cache = {}      # emoji -> PIL.Image (RGBA) | None
_pil_font_cache = {}       # (size, bold) -> ImageFont
_text_photo_cache = {}     # cache key -> ImageTk.PhotoImage (keep a ref!)


def split_emoji(s):
    """Yield ('text', str) / ('emoji', str) segments of s, in order."""
    i = 0
    for m in _EMOJI_CLUSTER.finditer(s):
        if m.start() > i:
            yield ('text', s[i:m.start()])
        yield ('emoji', m.group())
        i = m.end()
    if i < len(s):
        yield ('text', s[i:])


def twemoji_url(emoji):
    """Map a unicode emoji to its Twemoji PNG URL (or None)."""
    if not emoji:
        return None
    pts = [ord(c) for c in emoji]
    if 0x200D not in pts:                 # no ZWJ -> drop FE0F variation selector
        pts = [p for p in pts if p != 0xFE0F]
    if not pts:
        return None
    return _TWEMOJI_CDN.format("-".join(f"{p:x}" for p in pts))


def get_remote_image(url):
    """Return a cached PIL.Image (RGBA) for url, downloading once. None on fail.
    Thread-safe so a background fetch thread can warm the cache."""
    if not url:
        return None
    with _remote_img_lock:
        if url in _remote_img_cache:
            return _remote_img_cache[url]
    im = None
    try:
        import requests
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            im = Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        log(f"image fetch failed ({e})")
        im = None
    with _remote_img_lock:
        _remote_img_cache[url] = im
    return im


def _emoji_raw(emoji):
    """Full-size (72px) RGBA emoji image: local mirror first, then CDN."""
    if emoji in _emoji_raw_cache:
        return _emoji_raw_cache[emoji]
    im = None
    url = twemoji_url(emoji)
    if url:
        code = url.rsplit("/", 1)[-1]
        local = os.path.join(TWEMOJI_LOCAL_DIR, code)
        if os.path.isfile(local):
            try:
                im = Image.open(local).convert("RGBA")
            except Exception:
                im = None
        if im is None:
            im = get_remote_image(url)
    _emoji_raw_cache[emoji] = im
    return im


def warm_emoji_cache(text):
    """Pre-download every emoji in text (call from a background thread)."""
    for kind, seg in split_emoji(text or ""):
        if kind == 'emoji':
            _emoji_raw(seg)


def _pil_font(size, bold=False):
    size = max(6, int(size))
    key = (size, bool(bold))
    if key in _pil_font_cache:
        return _pil_font_cache[key]
    candidates = []
    if bold and WIDESCREEN_BOLD_TTF:
        candidates.append(WIDESCREEN_BOLD_TTF)
    if not bold and WIDESCREEN_TTF:
        candidates.append(WIDESCREEN_TTF)
    if bold:
        candidates += [
            r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
    else:
        candidates += [
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        ]
    fnt = None
    for path in candidates:
        try:
            fnt = ImageFont.truetype(path, size)
            break
        except Exception:
            continue
    if fnt is None:
        fnt = ImageFont.load_default()
    _pil_font_cache[key] = fnt
    return fnt


def compose_text_image(text, max_w, size, fg, bg=None, bold=False,
                       align='left', line_gap=None):
    """Render text (with \\n + inline emoji) to a wrapped PIL RGBA image.

    max_w  : wrap width in device pixels
    size   : text height in device pixels
    fg/bg  : hex colours; bg=None -> transparent background
    Returns a PIL.Image. (No Tk needed -> unit-testable.)"""
    fnt = _pil_font(size, bold)
    epx = max(8, int(size * 1.15))
    asc, desc = fnt.getmetrics()
    text_h = asc + desc
    if line_gap is None:
        line_gap = max(2, size // 5)
    line_h = max(text_h, epx) + line_gap

    def measure(t):
        try:
            return fnt.getlength(t)
        except Exception:
            return fnt.getbbox(t)[2]

    lines = []
    for raw_line in (text or "").split("\n"):
        atoms = []                       # (kind, payload, width)
        for kind, seg in split_emoji(raw_line):
            if kind == 'emoji':
                atoms.append(('emoji', seg, epx))
            else:
                for tok in re.split(r'(\s+)', seg):
                    if tok:
                        atoms.append(('text', tok, measure(tok)))
        cur, cw = [], 0
        for kind, payload, w in atoms:
            if kind == 'text' and payload.isspace():
                if cur:
                    cur.append((kind, payload, w)); cw += w
                continue
            if cw + w > max_w and cur:
                while cur and cur[-1][0] == 'text' and cur[-1][1].isspace():
                    cw -= cur[-1][2]; cur.pop()
                lines.append((cur, cw)); cur, cw = [], 0
            cur.append((kind, payload, w)); cw += w
        lines.append((cur, cw))
    if not lines:
        lines = [([], 0)]

    W = int(max_w)
    H = int(line_h * len(lines))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0) if bg is None else bg)
    d = ImageDraw.Draw(img)
    ty = (line_h - text_h) // 2
    ey = (line_h - epx) // 2
    y = 0
    for line, cw in lines:
        x = (W - cw) // 2 if align == 'center' else 0
        for kind, payload, w in line:
            if kind == 'emoji':
                em = _emoji_raw(payload)
                if em is not None:
                    em = em.resize((epx, epx), Image.LANCZOS)
                    img.paste(em, (int(x), int(y + ey)), em)
                else:                    # never blank: draw the glyph as text
                    d.text((x, y + ty), payload, font=fnt, fill=fg)
            else:
                d.text((x, y + ty), payload, font=fnt, fill=fg)
            x += w
        y += line_h
    return img


def render_text_image(text, max_w, size, fg, bg=None, bold=False,
                      align='left', cache_key=None):
    """Like compose_text_image but returns an ImageTk.PhotoImage (needs a
    Tk root to exist). The result is cached so it isn't garbage-collected;
    pass a stable cache_key when the same string is re-rendered every cycle."""
    key = cache_key or (text, max_w, size, fg, bg, bold, align)
    if key in _text_photo_cache:
        return _text_photo_cache[key]
    photo = ImageTk.PhotoImage(
        compose_text_image(text, max_w, size, fg, bg, bold, align))
    _text_photo_cache[key] = photo
    return photo


def emoji_photo(emoji, size, bg=None):
    """A single emoji as an ImageTk.PhotoImage at size x size. Falls back to a
    blank transparent image if the emoji can't be fetched."""
    key = ("__one__", emoji, size, bg)
    if key in _text_photo_cache:
        return _text_photo_cache[key]
    im = _emoji_raw(emoji)
    if im is not None:
        im = im.resize((size, size), Image.LANCZOS)
        if bg is not None:
            base = Image.new("RGBA", (size, size), bg)
            base.paste(im, (0, 0), im)
            im = base
    else:
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    photo = ImageTk.PhotoImage(im)
    _text_photo_cache[key] = photo
    return photo


def has_emoji(s):
    """True if s contains at least one emoji cluster."""
    return bool(s) and _EMOJI_CLUSTER.search(s) is not None


class RoundedPanel:
    """Panel with rounded corners rendered via Pillow RGBA image on a Canvas.
    The inner content frame is inset so it never covers the corners."""
    def __init__(self, parent, surface, **kwargs):
        self.surface = surface
        self.radius_px = surface.radius_px

        self.canvas = tk.Canvas(parent, bg=PAGE_BG, highlightthickness=0)
        self.inner = tk.Frame(self.canvas, bg=surface.bg)

        self.canvas.bind('<Configure>', self._on_configure)

    def _on_configure(self, event=None):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 4 or h < 4:
            return
        r = max(1, min(px(self.radius_px), w // 2, h // 2))

        self.canvas.delete('all')

        photo = rounded_image(w, h, r, self.surface.bg)
        self.canvas.create_image(0, 0, anchor='nw', image=photo)

        pad = r
        self.canvas.create_window(pad, pad, anchor='nw', window=self.inner,
                                  width=w - 2 * pad, height=h - 2 * pad)

    def place(self, **kwargs):
        self.canvas.place(**kwargs)