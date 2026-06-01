"""Shared constants, palette, helpers, and base widgets for infotavle-im."""

import os
import datetime
import threading
import tkinter as tk
from datetime import timezone, timedelta
from PIL import Image, ImageDraw, ImageTk

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
    """Per-surface palette: background, heading, body, subtext, accent."""
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