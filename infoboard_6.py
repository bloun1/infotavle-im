import tkinter as tk
import requests
import datetime
import json
import os
import re
import threading
from datetime import timezone, timedelta
from collections import defaultdict
from PIL import Image, ImageDraw, ImageTk

# === Timezone setup ===
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Oslo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=1))

# === Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# === Constants ===
GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
GRAPHQL_HEADERS = {
    'ET-Client-Name': 'Charlottenlund vgs IM',
    'Content-Type': 'application/json',
}
STOP_PLACE_ID = "NSR:StopPlace:43916"  # R13: parent stop (both directions)
GRAPHQL_QUERY = """
{
  stopPlace(id: "NSR:StopPlace:43916") {
    name
    estimatedCalls(numberOfDepartures: 20, timeRange: 10800) {
      realtime
      expectedDepartureTime
      aimedDepartureTime
      destinationDisplay { frontText }
      serviceJourney { line { publicCode } }
    }
  }
}
"""
MAX_PER_DEST = 3  # R2: cap per destination
REFRESH_API_SEC = 60
REFRESH_ORDEN_MIN = 5

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
BIRTHDAY_TODAY = '#C62828'  # R9: red for today's birthday


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


# === State ===
cached_departures = []
last_update = None
is_online = True
departures_lock = threading.Lock()


def log(msg):
    now = datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(SCRIPT_DIR, "infoboard.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] {msg}\n")


def fetch_orden():
    with open(os.path.join(SCRIPT_DIR, 'orden.json'), 'r', encoding="UTF-8") as f:
        return json.load(f)


def get_week_birthdays():
    """Load birthdays from bursdager.json. Show next 3-4 upcoming by next-occurrence date."""
    try:
        with open(os.path.join(SCRIPT_DIR, 'bursdager.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []

    now = datetime.datetime.now(LOCAL_TZ)
    today = now.date()

    birthdays = []
    for name, date_str in data.items():
        name = str(name).strip()
        try:
            bday = datetime.datetime.strptime(str(date_str), '%Y-%m-%d')
        except (ValueError, TypeError):
            continue

        # R7: compute next occurrence
        month, day = bday.month, bday.day
        try:
            this_year = datetime.date(today.year, month, day)
        except ValueError:
            continue

        if this_year >= today:
            next_date = this_year
        else:
            try:
                next_date = datetime.date(today.year + 1, month, day)
            except ValueError:
                continue

        days_until = (next_date - today).days

        day_names = ['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag']
        day_name = day_names[next_date.weekday()].capitalize()
        date_str_fmt = next_date.strftime('%d.%m')

        # R9: build countdown suffix
        if days_until == 0:
            countdown = "i dag"
        elif days_until == 1:
            countdown = "i morgen"
        else:
            countdown = f"om {days_until} dager"

        birthdays.append({
            'navn': name,
            'dag': day_name,
            'dato': date_str_fmt,
            'days_until': days_until,
            'countdown': countdown,
            'is_today': days_until == 0,
        })

    # Sort by days until next occurrence
    birthdays.sort(key=lambda b: b['days_until'])
    return birthdays[:4]


# R15: Discord connection status tracking
discord_status = "not_configured"  # "not_configured", "ok", or error string
discord_status_lock = threading.Lock()


def fetch_discord():
    """Fetch Discord messages via bot API using config.json. R15: track status."""
    global discord_status
    try:
        with open(os.path.join(SCRIPT_DIR, 'config.json'), 'r', encoding="UTF-8") as f:
            cfg = json.load(f)
        token = cfg.get('discord_bot_token')
        channel_id = cfg.get('discord_channel_id')
        max_msgs = cfg.get('discord_max_messages', 2)
        if not token or not channel_id:
            with discord_status_lock:
                discord_status = "not_configured"
            return []

        # R15: fetch messages directly, surface errors
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={max_msgs}"
        headers = {"Authorization": f"Bot {token}"}
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code != 200:
            err = f"{resp.status_code}"
            try:
                j = resp.json()
                err = f"{resp.status_code} {j.get('message', '')} ({j.get('code', '')})"
            except Exception:
                pass
            with discord_status_lock:
                discord_status = f"Discord feil — {err}"
            log(f"Discord fetch failed: {err}")
            return []

        messages_raw = resp.json()
        fetched_raw = len(messages_raw)
        result = []
        for msg in messages_raw:
            author = msg.get('author', {}).get('global_name') or msg.get('author', {}).get('username', '')
            content = msg.get('content', '').strip()
            # R15: fallback to embed/attachment if content is empty
            if not content:
                for emb in msg.get('embeds', []):
                    content = (emb.get('title') or '') + ' ' + (emb.get('description') or '')
                    content = content.strip()
                    if content:
                        break
                if not content and msg.get('attachments'):
                    content = msg['attachments'][0].get('filename', 'Vedlegg')
            timestamp = msg.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
                    time_str = dt.strftime('%H:%M')
                except Exception:
                    time_str = ''
            else:
                time_str = ''
            result.append({'author': author, 'content': content, 'time': time_str})

        shown = [m for m in result if m['content']]
        # R15: detect empty-content situation (intent off → most messages have no text)
        if fetched_raw > 0 and len(shown) < fetched_raw // 2:
            with discord_status_lock:
                discord_status = "no_content_intent"
            return shown  # show what we have, but also surface the warning
        with discord_status_lock:
            discord_status = "ok"
        return shown[:max_msgs]
    except Exception as e:
        with discord_status_lock:
            discord_status = f"Frakoblet — {e}"
        log(f"Discord fetch failed ({e})")
        return []


def parse_departures():
    """R13: Fetch departures via Journey Planner GraphQL (single stop, ~4KB)."""
    global cached_departures, last_update, is_online
    try:
        response = requests.post(GRAPHQL_URL, headers=GRAPHQL_HEADERS,
                                  json={"query": GRAPHQL_QUERY}, timeout=8)
        response.raise_for_status()
        data = response.json()

        calls = data["data"]["stopPlace"]["estimatedCalls"]
        departures = []
        for c in calls:
            line = c["serviceJourney"]["line"]["publicCode"]
            dest = (c["destinationDisplay"]["frontText"] or "").strip()
            if dest.lower() == "valøyvegen":
                dest = "Tempe"
            t = c.get("expectedDepartureTime") or c.get("aimedDepartureTime")
            if not t:
                continue
            dep_time = datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
            departures.append({
                "line": line,
                "destination": dest,
                "time": dep_time
            })

        departures.sort(key=lambda d: d["time"])

        # R2: Group first, then cap per destination
        grouped = defaultdict(list)
        for d in departures:
            grouped[d["destination"]].append(d)
        for dest in grouped:
            grouped[dest] = grouped[dest][:MAX_PER_DEST]

        with departures_lock:
            cached_departures = []
            for dest in sorted(grouped, key=lambda d: grouped[d][0]["time"]):
                cached_departures.extend(grouped[dest])
            last_update = datetime.datetime.now(LOCAL_TZ)
            is_online = True
        log(f"Updated from GraphQL ({len(cached_departures)} departures)")
        return True
    except Exception as e:
        is_online = False
        log(f"GraphQL fetch failed ({e})")
        return False


def fetch_loop():
    while True:
        parse_departures()
        threading.Event().wait(REFRESH_API_SEC)


def format_time(dep_time):
    now = datetime.datetime.now(LOCAL_TZ)
    delta = int((dep_time - now).total_seconds() / 60)
    if delta < 0:
        return ""
    if delta == 0:
        return "NÅ"
    elif delta < 15:
        return f"{delta} MIN"
    else:
        return dep_time.strftime("%H:%M")


# === R6: RoundedPanel — uses Pillow-rendered images for true rounded corners ===
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

        # R6: draw rounded panel background as Pillow image
        photo = rounded_image(w, h, r, self.surface.bg)
        self.canvas.create_image(0, 0, anchor='nw', image=photo)

        # Inset content frame by radius so corners stay visible
        pad = r
        self.canvas.create_window(pad, pad, anchor='nw', window=self.inner,
                                  width=w - 2 * pad, height=h - 2 * pad)

    def place(self, **kwargs):
        self.canvas.place(**kwargs)


class DepartureBoard:
    """Bus departure board — sits directly on page background, no panel.
    Uses a single shared grid so all groups align column-for-column (Bugs 1 & 2).
    R2: 3 departures per destination, balanced.
    R6: badges use Pillow rounded images."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.frame = tk.Frame(parent, bg=PAGE_BG)

        # Shared grid for header + all rows
        self.grid = tk.Frame(self.frame, bg=PAGE_BG)
        self.grid.pack(fill='both', expand=True, padx=px(6), pady=px(6))

        # Column config: fixed LINJE, expanding RETNING, fixed AVGANG
        self.grid.grid_columnconfigure(0, minsize=px(72), weight=0)
        self.grid.grid_columnconfigure(1, weight=1, minsize=px(120))
        self.grid.grid_columnconfigure(2, minsize=px(90), weight=0)

        # Header row (row 0)
        tk.Label(self.grid, text="LINJE", font=font(24, 'xBold'),
                 bg=PAGE_BG, fg=HEADING_YELLOW).grid(row=0, column=0, sticky='w', padx=px(6))
        tk.Label(self.grid, text="RETNING", font=font(24, 'xBold'),
                 bg=PAGE_BG, fg=HEADING_YELLOW).grid(row=0, column=1, sticky='w', padx=px(6))
        tk.Label(self.grid, text="AVGANG", font=font(24, 'xBold'),
                 bg=PAGE_BG, fg=HEADING_YELLOW).grid(row=0, column=2, sticky='e', padx=px(6))
        self._grid_row = 1

        self.dest_headers = []
        self.dep_slots = []

        self.no_data_label = tk.Label(self.grid, text="", font=font(18),
                                       bg=PAGE_BG, fg=WHITE)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def place(self, **kwargs):
        self.frame.place(**kwargs)

    def _add_dest_group(self):
        """Add a new destination group (header + MAX_PER_DEST rows) to the grid."""
        row = self._grid_row
        hdr = tk.Label(self.grid, text="", font=font(24, 'xBold'),
                       bg=PAGE_BG, fg=WHITE, anchor='w')
        hdr.grid(row=row, column=0, columnspan=3, sticky='w', padx=px(6), pady=(px(10), px(2)))
        self.dest_headers.append(hdr)
        self._grid_row += 1

        group = []
        for _ in range(MAX_PER_DEST):
            row = self._grid_row

            # R6: Badge as Canvas with Pillow rounded image + create_text
            badge_w, badge_h = px(67), px(33)
            badge_canvas = tk.Canvas(self.grid, width=badge_w, height=badge_h,
                                      bg=PAGE_BG, highlightthickness=0)
            badge_canvas.grid(row=row, column=0, sticky='w', padx=px(6), pady=px(2))

            dest_lbl = tk.Label(self.grid, text="", font=font(18),
                                bg=PAGE_BG, fg=WHITE, anchor='w')
            dest_lbl.grid(row=row, column=1, sticky='w', padx=px(6), pady=px(2))

            time_lbl = tk.Label(self.grid, text="", font=font(18, 'bold'),
                                bg=PAGE_BG, fg=HEADING_YELLOW, anchor='e')
            time_lbl.grid(row=row, column=2, sticky='e', padx=px(6), pady=px(2))

            group.append((badge_canvas, dest_lbl, time_lbl))
            self._grid_row += 1

        self.dep_slots.append(group)

    def update_display(self):
        with departures_lock:
            deps = list(cached_departures)

        grouped = defaultdict(list)
        for d in deps:
            grouped[d["destination"]].append(d)
        sorted_groups = sorted(grouped.items(), key=lambda kv: kv[1][0]["time"])

        while len(self.dep_slots) < len(sorted_groups):
            self._add_dest_group()

        self.no_data_label.grid_forget()

        if not sorted_groups:
            self.no_data_label.config(text="INGEN DATA")
            self.no_data_label.grid(row=1, column=0, columnspan=3, pady=px(20))
            for hdr in self.dest_headers:
                hdr.grid_forget()
            for group in self.dep_slots:
                for badge_canvas, dest_lbl, time_lbl in group:
                    badge_canvas.grid_forget()
                    dest_lbl.grid_forget()
                    time_lbl.grid_forget()
            return

        gi = 0
        for dest, group in sorted_groups:
            if gi >= len(self.dep_slots):
                break

            group.sort(key=lambda x: x["time"])

            row_idx = gi * (MAX_PER_DEST + 1) + 1
            self.dest_headers[gi].config(text=f"→ {dest.upper()}")
            self.dest_headers[gi].grid(row=row_idx, column=0, columnspan=3,
                                        sticky='w', padx=px(6), pady=(px(10), px(2)))

            slots = self.dep_slots[gi]
            for i in range(MAX_PER_DEST):
                badge_canvas, dest_lbl, time_lbl = slots[i]
                row_num = row_idx + 1 + i
                if i < len(group):
                    dep = group[i]
                    time_text = format_time(dep["time"])
                    if not time_text:
                        badge_canvas.grid_forget()
                        dest_lbl.grid_forget()
                        time_lbl.grid_forget()
                        continue

                    # R6: Draw rounded badge background + text
                    badge_canvas.delete('all')
                    bw = badge_canvas.winfo_width() if badge_canvas.winfo_width() > 1 else px(67)
                    bh = badge_canvas.winfo_height() if badge_canvas.winfo_height() > 1 else px(33)
                    badge_photo = rounded_image(bw, bh, px(6), TEAL)
                    badge_canvas.create_image(0, 0, anchor='nw', image=badge_photo)
                    badge_canvas.create_text(bw // 2, bh // 2, text=dep['line'],
                                             fill=WHITE, font=font(18, 'bold'))

                    dest_lbl.config(text=dep['destination'])
                    time_lbl.config(text=time_text)

                    badge_canvas.grid(row=row_num, column=0, sticky='w', padx=px(6), pady=px(2))
                    dest_lbl.grid(row=row_num, column=1, sticky='w', padx=px(6), pady=px(2))
                    time_lbl.grid(row=row_num, column=2, sticky='e', padx=px(6), pady=px(2))
                else:
                    badge_canvas.grid_forget()
                    dest_lbl.grid_forget()
                    time_lbl.grid_forget()

            gi += 1

        for idx in range(gi, len(self.dep_slots)):
            self.dest_headers[idx].grid_forget()
            for badge_canvas, dest_lbl, time_lbl in self.dep_slots[idx]:
                badge_canvas.grid_forget()
                dest_lbl.grid_forget()
                time_lbl.grid_forget()


class DiscordPanel:
    """Discord messages panel — yellow surface with Pillow rounded corners (R1+R6)."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        # Title
        tk.Label(self.rf.inner, text="📢❗1IM-FELLESINFO", font=font(24, 'xBold'),
                 bg=surface.bg, fg=surface.heading).pack(pady=(px(6), px(4)))

        # Messages container
        self.msg_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.msg_frame.pack(fill='both', expand=True, padx=px(6), pady=px(4))

        self.msg_widgets = []
        for _ in range(2):
            # R6: rounded card via Pillow image on Canvas, auto-sizes to content
            card = tk.Canvas(self.msg_frame, bg=surface.bg, highlightthickness=0)
            card_inner = tk.Frame(card, bg=DISCORD_CARD)
            author_lbl = tk.Label(card_inner, text="", font=font(14, 'bold'),
                                  bg=DISCORD_CARD, fg=DISCORD_AUTHOR, anchor='w')
            author_lbl.pack(fill='x', padx=px(10), pady=(px(8), 0))
            content_lbl = tk.Label(card_inner, text="", font=font(13),
                                   bg=DISCORD_CARD, fg=DISCORD_TEXT, anchor='w',
                                   wraplength=px(260), justify='left')
            content_lbl.pack(fill='x', padx=px(10), pady=(px(2), 0))
            time_lbl = tk.Label(card_inner, text="", font=font(11),
                                bg=DISCORD_CARD, fg=DISCORD_TIME, anchor='e')
            time_lbl.pack(fill='x', padx=px(10), pady=(px(2), px(8)))
            card._inner = card_inner  # prevent GC
            card._photo = None  # will be set on Configure
            card.bind('<Configure>', lambda e, c=card, ci=card_inner: self._configure_card(c, ci))
            self.msg_widgets.append((card, author_lbl, content_lbl, time_lbl))

        self.no_data_label = tk.Label(self.msg_frame, text="Ingen meldinger",
                                       font=font(14), bg=surface.bg, fg=surface.heading)

    def _configure_card(self, card, card_inner):
        """R6: draw rounded background on card canvas, auto-size to content."""
        w = card.winfo_width()
        if w < 4:
            return
        # Measure content height, then set canvas to fit
        card_inner.update_idletasks()
        ih = card_inner.winfo_reqheight()
        pad = max(1, min(px(8), w // 2))
        h = ih + 2 * pad
        r = max(1, min(px(8), w // 2, h // 2))
        card.config(height=h)
        card.delete('all')
        photo = rounded_image(w, h, r, DISCORD_CARD)
        card._photo = photo  # prevent GC
        card.create_image(0, 0, anchor='nw', image=photo)
        card.create_window(pad, pad, anchor='nw', window=card_inner,
                           width=w - 2 * pad, height=ih)

    def place(self, **kwargs):
        self.rf.place(**kwargs)

    def update_display(self, messages=None):
        if messages is None:
            messages = []

        with discord_status_lock:
            status = discord_status

        # R15: show actionable status instead of generic "Ingen meldinger"
        if status == "not_configured":
            self.no_data_label.config(text="Sett opp Discord i config.json",
                                       fg='#EA560D')
            self.no_data_label.pack(pady=px(10))
            for card, _, _, _ in self.msg_widgets:
                card.pack_forget()
            return
        elif status == "no_content_intent":
            self.no_data_label.config(text="Discord tilkoblet, men ingen meldingstekst\n— skru på Message Content Intent",
                                       fg='#EA560D')
            self.no_data_label.pack(pady=px(10))
            for card, _, _, _ in self.msg_widgets:
                card.pack_forget()
            return
        elif status.startswith("Discord feil") or status.startswith("Frakoblet"):
            self.no_data_label.config(text=f"Discord frakoblet — {status}",
                                       fg='#EA560D')
            self.no_data_label.pack(pady=px(10))
            for card, _, _, _ in self.msg_widgets:
                card.pack_forget()
            return

        if not messages:
            self.no_data_label.config(text="Ingen meldinger", fg=self.surface.heading)
            self.no_data_label.pack(pady=px(10))
            for card, _, _, _ in self.msg_widgets:
                card.pack_forget()
            return

        self.no_data_label.pack_forget()
        for i, (card, author_lbl, content_lbl, time_lbl) in enumerate(self.msg_widgets):
            if i < len(messages):
                msg = messages[i]
                author_lbl.config(text=msg.get('author', msg.get('username', '')))
                content_lbl.config(text=msg.get('content', msg.get('message', '')))
                time_lbl.config(text=msg.get('time', ''))
                card.pack(fill='x', pady=px(3))
            else:
                card.pack_forget()


class BirthdayPanel:
    """Birthday panel — yellow surface with Pillow rounded corners (R1+R6).
    R4: reads from Bursdag.xlsx. R7: shows next upcoming. R8: centered. R9: countdown + red today."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        # Title — centered
        tk.Label(self.rf.inner, text="UKENS BURSDAGSBARN", font=font(14, 'xBold'),
                 bg=surface.bg, fg=surface.heading).pack(pady=(px(6), px(4)))

        self.row_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.row_frame.pack(fill='both', expand=True, padx=px(6))

        self.row_labels = []
        for _ in range(4):
            lbl = tk.Label(self.row_frame, text="", font=font(14, 'bold'),
                           bg=surface.bg, fg=WHITE, anchor='center')  # R8: centered
            lbl.pack(fill='x', pady=px(1))
            self.row_labels.append(lbl)

        self.no_data_label = tk.Label(self.row_frame, text="Ingen bursdager denne uken",
                                       font=font(14), bg=surface.bg, fg=surface.heading)

    def place(self, **kwargs):
        self.rf.place(**kwargs)

    def update_display(self):
        bursdager = get_week_birthdays()

        if not bursdager:
            self.no_data_label.pack(pady=px(6))
            for lbl in self.row_labels:
                lbl.config(text="")
            return

        self.no_data_label.pack_forget()
        for i, lbl in enumerate(self.row_labels):
            if i < len(bursdager):
                b = bursdager[i]
                text = f"{b['navn']} – {b['dag']} – {b['dato']} ({b['countdown']})"
                # R9: today's birthday in red
                color = BIRTHDAY_TODAY if b['is_today'] else WHITE
                lbl.config(text=text, fg=color)
            else:
                lbl.config(text="")


class OrdenTable:
    """Orden table — purple surface with Pillow rounded corners (R1+R6).
    R3: Centered. Bug 4: Hides past weeks."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        # Title — centered
        tk.Label(self.rf.inner, text="ORDENSELEV", font=font(24, 'xBold'),
                 bg=surface.bg, fg=surface.heading).pack(pady=(px(6), px(4)))

        # Centering frame for the table
        self.center_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.center_frame.pack(fill='both', expand=True, padx=px(6))

        # Grid container — R3: centered within center_frame
        self.grid_frame = tk.Frame(self.center_frame, bg=surface.bg)
        self.grid_frame.pack(anchor='center')

        headers = ['UKE', 'DATO', '1IM1', '1IM2', 'VASK']
        for col, header in enumerate(headers):
            tk.Label(self.grid_frame, text=header, font=font(14, 'xBold'),
                     bg=surface.bg, fg=WHITE).grid(row=0, column=col, padx=px(4), pady=px(4), sticky='w')

        self.cells = []
        for row in range(1, 27):
            row_cells = []
            for col in range(5):
                lbl = tk.Label(self.grid_frame, text="", font=font(11),
                               bg=surface.bg, fg=WHITE)
                lbl.grid(row=row, column=col, padx=px(4), pady=px(2), sticky='w')
                row_cells.append(lbl)
            self.cells.append(row_cells)

    def place(self, **kwargs):
        self.rf.place(**kwargs)

    def update_display(self):
        orden_data = fetch_orden()
        current_week = datetime.datetime.now(LOCAL_TZ).isocalendar()[1]

        row_idx = 0
        for uke, info in orden_data.items():
            if row_idx >= len(self.cells):
                break
            week_num = int(re.sub(r'\D', '', uke))
            if week_num < current_week:
                continue

            if week_num == current_week:
                color = GOLD_HILITE
                font_style = font(12, 'bold')
            else:
                color = WHITE
                font_style = font(11)

            data = [uke, info['dato'], info['1IM1'], info['1IM2'], info['vasking']]
            for col, val in enumerate(data):
                self.cells[row_idx][col].config(text=val, fg=color, font=font_style)
            row_idx += 1

        for r in range(row_idx, len(self.cells)):
            for col in range(5):
                self.cells[r][col].config(text="")


# === GUI Setup ===
root = tk.Tk()
root.attributes('-fullscreen', True)
root.configure(bg=PAGE_BG)

# Compute scale factor
screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()
S = screen_w / 1280.0

# R10: Background pattern — load and display as lowest-z layer
bg_pattern_photo = None  # keep reference to prevent GC


def load_bg_pattern():
    """R10/R14: Load bg_pattern, use cached resize if available, else resize and cache."""
    global bg_pattern_photo
    cache_path = os.path.join(SCRIPT_DIR, f'bg_pattern_{screen_w}x{screen_h}.png')
    try:
        if os.path.exists(cache_path):
            img = Image.open(cache_path)
            img.load()  # ensure fully read before converting
        else:
            img = Image.open(os.path.join(SCRIPT_DIR, 'bg_pattern_real.png'))
            img = img.resize((screen_w, screen_h), Image.LANCZOS)
            try:
                img.save(cache_path, 'PNG', optimize=True)
                log(f"Cached bg_pattern to {cache_path}")
            except Exception:
                pass  # non-fatal — cache write failure just means next run resizes again
        bg_pattern_photo = ImageTk.PhotoImage(img)
        return bg_pattern_photo
    except Exception:
        return None


bg_img = load_bg_pattern()
if bg_img:
    bg_label = tk.Label(root, image=bg_img, bg=PAGE_BG)
    bg_label.place(x=0, y=0, relwidth=1.0, relheight=1.0)


def load_logo():
    """R11/R12: Load IM logo image for overlay on gold badge."""
    try:
        img = Image.open(os.path.join(SCRIPT_DIR, 'im-logo-blo.png'))
        return img  # return raw PIL image, we resize after padding calc
    except Exception:
        return None


# === Header ===
header_frame = tk.Frame(root, bg=PAGE_BG)

# R12: IM badge — gold rounded box sized to title text height (36·S) with 5·S padding around logo
IM_BADGE_PAD = 5  # padding in S units around the logo inside the gold box
im_badge_h = px(36)  # match title text height
im_badge_w = im_badge_h  # square-ish
logo_inner_h = im_badge_h - 2 * px(IM_BADGE_PAD)
logo_inner_w = im_badge_w - 2 * px(IM_BADGE_PAD)

im_badge_canvas = tk.Canvas(header_frame, width=im_badge_w, height=im_badge_h,
                             bg=PAGE_BG, highlightthickness=0)
im_badge_photo = rounded_image(im_badge_w, im_badge_h, px(8), '#FCC745')
im_badge_canvas.create_image(0, 0, anchor='nw', image=im_badge_photo)

raw_logo = load_logo()
if raw_logo:
    # R12: scale logo to fit inside the gold box with padding, preserve aspect ratio
    from PIL import Image as _PILImage
    logo_w, logo_h = raw_logo.size
    scale = min(logo_inner_w / logo_w, logo_inner_h / logo_h)
    resized = raw_logo.resize((max(1, int(logo_w * scale)), max(1, int(logo_h * scale))),
                               _PILImage.LANCZOS)
    im_logo_photo = ImageTk.PhotoImage(resized)
    im_badge_canvas.create_image(im_badge_w // 2, im_badge_h // 2, anchor='center', image=im_logo_photo)
else:
    im_badge_canvas.create_text(im_badge_w // 2, im_badge_h // 2, text="IM",
                                 fill='#37B6AE', font=font(20, 'xBold'))

im_badge_canvas.pack(side='left', padx=(px(28), px(10)))

# R5: Title split into XBold + Light
tk.Label(header_frame, text="BUSSAVGANGER - ", font=font(36, 'xBold'),
         bg=PAGE_BG, fg=HEADING_YELLOW).pack(side='left')
tk.Label(header_frame, text="CHARLOTTENLUND VGS", font=font(36, 'normal'),
         bg=PAGE_BG, fg=HEADING_YELLOW).pack(side='left')

# Clock
time_label = tk.Label(header_frame, text='', font=font(36, 'xBold'),
                      bg=PAGE_BG, fg=HEADING_YELLOW)
time_label.pack(side='right', padx=px(50))

# Status (small, unobtrusive)
status_label = tk.Label(header_frame, text='', font=font(11),
                        bg=PAGE_BG, fg='#949BA4')
status_label.pack(side='right', padx=px(10))

# Place header at PSD bbox
header_frame.place(relx=0.022, rely=0.026, relwidth=0.909, relheight=0.065)

# === Main panels ===

# Bus board (no panel, sits on page bg)
board = DepartureBoard(root, PAGE_SURFACE)
board.place(relx=0.018, rely=0.139, relwidth=0.296, relheight=0.565)

# Birthday panel (yellow, R6 rounded corners)
bursdag = BirthdayPanel(root, YELLOW_SURFACE)
bursdag.place(relx=0.027, rely=0.720, relwidth=0.299, relheight=0.182)

# Discord panel (yellow, R6 rounded corners)
discord = DiscordPanel(root, YELLOW_SURFACE)
discord.place(relx=0.348, rely=0.124, relwidth=0.299, relheight=0.779)

# Orden table (purple, R6 rounded corners)
orden = OrdenTable(root, ORDEN_SURFACE)
orden.place(relx=0.671, rely=0.124, relwidth=0.299, relheight=0.779)

root.bind('<Escape>', lambda e: root.destroy())


def update_time():
    time_label.config(text=datetime.datetime.now(LOCAL_TZ).strftime('%H:%M:%S'))
    root.after(1000, update_time)


def update_departures():
    board.update_display()
    if not is_online:
        status_label.config(text="⚠ OFFLINE", fg='#EA560D')
    elif last_update:
        ago = int((datetime.datetime.now(LOCAL_TZ) - last_update).total_seconds())
        status_label.config(text=f"Oppdatert {ago}s siden")
    root.after(10000, update_departures)


def update_orden():
    orden.update_display()
    root.after(REFRESH_ORDEN_MIN * 60 * 1000, update_orden)


def update_bursdager():
    bursdag.update_display()
    root.after(REFRESH_ORDEN_MIN * 60 * 1000, update_bursdager)


def update_discord():
    messages = fetch_discord()
    discord.update_display(messages)
    root.after(REFRESH_API_SEC * 1000, update_discord)


fetch_thread = threading.Thread(target=fetch_loop, daemon=True)
fetch_thread.start()

update_time()
update_departures()
update_orden()
update_bursdager()
update_discord()

root.mainloop()
