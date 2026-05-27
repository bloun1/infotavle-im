import tkinter as tk
import requests
import xmltodict
import datetime
import json
import threading
import os
import re
from PIL import Image, ImageTk, ImageDraw
from datetime import timezone, timedelta
from collections import defaultdict

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Oslo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=2))  # CEST fallback (summer)

# === Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# === Config ===
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')


def load_config():
    defaults = {
        "discord_bot_token": "",
        "discord_channel_id": "",
        "discord_max_messages": 8,
        "discord_refresh_sec": 60,
    }
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        defaults.update(cfg)
    except FileNotFoundError:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(defaults, f, indent=2, ensure_ascii=False)
    return defaults


CONFIG = load_config()

# === API ===
API_URL = "https://api.entur.io/realtime/v1/rest/et?datasetId=ATB"
HEADERS = {'ET-Client-Name': 'Charlottenlund vgs IM'}
STOP_PLACE = "NSR:Quay:75404"
MAX_DEPARTURES = 12
MAX_PER_DEST = 5
REFRESH_API_SEC = 60
REFRESH_ORDEN_MIN = 5
API_TIMEOUT = 10

# === Charlottenlund vgs Visual Profile ===
BG_COLOR = '#3C1053'
BG_SECONDARY = '#4A1366'
HEADING_COLOR = '#FFD244'
ACCENT_COLOR = '#00816D'
ACCENT_DARK = '#006C5B'
TEXT_COLOR = '#FFFFFF'
SUBTEXT_COLOR = '#B89CC8'
ALERT_COLOR = '#EA560D'
IM_TEAL = '#38aba3'
DISCORD_BG = '#5865F2'  # Discord blurple for icons

# === Fonts ===
# Primary: Widescreen XBold (headings/bold) / Light (body)
# Fallback: Arial (installed everywhere)
# To install Widescreen: place .ttf files in script dir or system fonts folder,
# then restart the app.

FONTS_BOLD = ['Widescreen XBold', 'Widescreen-XBold', 'Widescreen']
FONTS_LIGHT = ['Widescreen Light', 'Widescreen-Light', 'Widescreen']

_font_cache = {}


def resolve_font(size, weight='normal'):
    """Resolve font tuple with Widescreen → Arial fallback. Call after tk.Tk()."""
    key = (size, weight)
    if key in _font_cache:
        return _font_cache[key]
    families = FONTS_BOLD if weight in ('bold', 'xbold') else FONTS_LIGHT
    tk_weight = 'bold' if weight in ('bold', 'xbold') else 'normal'
    available = set(tk.font.families())
    for family in families:
        if family in available:
            result = (family, size, tk_weight)
            _font_cache[key] = result
            return result
    result = ('Arial', size, tk_weight)
    _font_cache[key] = result
    return result


# Font constants — set after root = tk.Tk() in init_fonts()
FONT_TITLE = None
FONT_SUBHEADING = None
FONT_BODY = None
FONT_BODY_BOLD = None
FONT_BODY_SMALL = None
FONT_TABLE_HEADER = None
FONT_CLOCK = None
FONT_LINE_BADGE = None
FONT_TIME = None
FONT_STATUS = None
FONT_IM_BADGE = None
FONT_DISCORD_MSG = None
FONT_DISCORD_AUTHOR = None
FONT_DISCORD_TIME = None


def init_fonts():
    """Initialize all font constants. Must be called after tk.Tk()."""
    global FONT_TITLE, FONT_SUBHEADING, FONT_BODY, FONT_BODY_BOLD
    global FONT_BODY_SMALL, FONT_TABLE_HEADER, FONT_CLOCK
    global FONT_LINE_BADGE, FONT_TIME, FONT_STATUS, FONT_IM_BADGE
    global FONT_DISCORD_MSG, FONT_DISCORD_AUTHOR, FONT_DISCORD_TIME
    FONT_TITLE = resolve_font(40, 'xbold')         # h1
    FONT_SUBHEADING = resolve_font(28, 'xbold')     # h2
    FONT_BODY = resolve_font(17, 'normal')           # body
    FONT_BODY_BOLD = resolve_font(17, 'xbold')       # body bold
    FONT_BODY_SMALL = resolve_font(14, 'normal')      # small (orden cells)
    FONT_TABLE_HEADER = resolve_font(14, 'xbold')     # table headers
    FONT_CLOCK = resolve_font(36, 'normal')           # clock
    FONT_LINE_BADGE = resolve_font(17, 'xbold')       # line badge
    FONT_TIME = resolve_font(17, 'xbold')             # departure time
    FONT_STATUS = resolve_font(14, 'normal')           # status
    FONT_IM_BADGE = resolve_font(40, 'xbold')         # IM badge
    FONT_DISCORD_MSG = resolve_font(14, 'normal')     # Discord content
    FONT_DISCORD_AUTHOR = resolve_font(14, 'xbold')   # Discord author
    FONT_DISCORD_TIME = resolve_font(12, 'normal')     # Discord time

# === Border Radius ===
CORNER_RADIUS = 8


def rounded_rect(canvas, x1, y1, x2, y2, r=CORNER_RADIUS, **kwargs):
    """Draw a rounded rectangle on a Tkinter Canvas."""
    points = [
        x1 + r, y1, x1 + r, y1,
        x2 - r, y1, x2 - r, y1,
        x2, y1, x2, y1 + r,
        x2, y1 + r, x2, y2 - r,
        x2, y2 - r, x2, y2,
        x2 - r, y2, x2 - r, y2,
        x1 + r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r,
        x1, y2 - r, x1, y1 + r,
        x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedFrame(tk.Frame):
    """Frame with rounded corners rendered via Canvas background."""
    def __init__(self, parent, bg=BG_SECONDARY, radius=CORNER_RADIUS, **kwargs):
        super().__init__(parent, bg=bg, highlightthickness=0, **kwargs)
        self._radius = radius
        self._bg = bg
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, height=0)
        self.canvas.pack(fill='both', expand=True)
        self.bind('<Configure>', self._on_resize)

    def _on_resize(self, event):
        self.canvas.delete('rounded_bg')
        w, h = event.width, event.height
        r = self._radius
        self.canvas.create_rectangle(
            r, 0, w - r, h,
            fill=self._bg, outline='', tags='rounded_bg'
        )
        self.canvas.create_rectangle(
            0, r, w, h - r,
            fill=self._bg, outline='', tags='rounded_bg'
        )
        for (cx, cy) in [(r, r), (w - r, r), (r, h - r), (w - r, h - r)]:
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=self._bg, outline='', tags='rounded_bg'
            )
        self.canvas.tag_lower('rounded_bg')


# === State ===
cached_departures = []
last_update = None
is_online = False
departures_lock = threading.Lock()
discord_messages = []
discord_lock = threading.Lock()


def log(msg):
    now = datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(SCRIPT_DIR, "infoboard.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] {msg}\n")


def fetch_orden():
    path = os.path.join(SCRIPT_DIR, 'orden.json')
    try:
        with open(path, 'r', encoding="UTF-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log(f"Orden load failed ({e})")
        return {}


def fetch_discord_messages():
    """Fetch recent messages from Discord channel via REST API."""
    global discord_messages
    token = CONFIG.get("discord_bot_token", "")
    channel_id = CONFIG.get("discord_channel_id", "")
    if not token or not channel_id:
        return
    try:
        resp = requests.get(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {token}"},
            params={"limit": CONFIG.get("discord_max_messages", 8)},
            timeout=10
        )
        resp.raise_for_status()
        msgs = []
        for m in resp.json():
            author = m.get("author", {}).get("global_name") or m.get("author", {}).get("username", "?")
            content = m.get("content", "").strip()
            timestamp = m.get("timestamp", "")
            # Skip empty messages (embeds/attachments only)
            if not content:
                continue
            # Strip Discord markdown: bold, italic, code
            content = re.sub(r'\*\*(.+?)\*\*', r'\1', content)
            content = re.sub(r'\*(.+?)\*', r'\1', content)
            content = re.sub(r'`(.+?)`', r'\1', content)
            # Truncate long messages
            if len(content) > 120:
                content = content[:117] + "..."
            # Parse timestamp
            try:
                dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
                time_str = dt.strftime("%H:%M")
            except Exception:
                time_str = ""
            msgs.append({"author": author, "content": content, "time": time_str})
        with discord_lock:
            discord_messages = msgs
        log(f"Discord: fetched {len(msgs)} messages")
    except Exception as e:
        log(f"Discord fetch failed ({e})")


def parse_departures():
    global cached_departures, last_update, is_online
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=API_TIMEOUT)
        response.raise_for_status()
        doc = xmltodict.parse(response.text)

        etd = doc["Siri"]["ServiceDelivery"]["EstimatedTimetableDelivery"]
        journeys = etd["EstimatedJourneyVersionFrame"]["EstimatedVehicleJourney"]
        if isinstance(journeys, dict):
            journeys = [journeys]

        departures = []
        for j in journeys:
            calls = j.get("EstimatedCalls", {}).get("EstimatedCall")
            if not calls:
                continue
            if isinstance(calls, dict):
                calls = [calls]
            for stop in calls:
                if stop.get("StopPointRef") == STOP_PLACE:
                    t = stop.get("ExpectedArrivalTime") or stop.get("ExpectedDepartureTime")
                    if t:
                        dep_time = datetime.datetime.fromisoformat(
                            t.replace("Z", "+00:00")
                        ).astimezone(LOCAL_TZ)
                        dest = j.get("DestinationName", "").strip()
                        if dest.lower() == "valøyvegen":
                            dest = "Tempe"
                        departures.append({
                            "line": j.get("PublishedLineName", ""),
                            "destination": dest,
                            "time": dep_time
                        })
                    break

        departures.sort(key=lambda d: d["time"])
        with departures_lock:
            cached_departures = departures[:MAX_DEPARTURES]
            last_update = datetime.datetime.now(LOCAL_TZ)
            is_online = True
        log(f"Updated from API ({len(cached_departures)} departures)")
        return True
    except Exception as e:
        is_online = False
        log(f"API fetch failed ({e})")
        return False


def fetch_loop():
    while True:
        parse_departures()
        fetch_discord_messages()
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


def create_pattern_bg(width, height):
    pattern_path = os.path.join(SCRIPT_DIR, 'bg_pattern_real.png')
    if os.path.exists(pattern_path):
        try:
            bg = Image.open(pattern_path).convert('RGB')
            if bg.size != (width, height):
                bg = bg.resize((width, height), Image.LANCZOS)
            return bg
        except Exception as e:
            log(f"Pattern load failed ({e}), generating fallback")

    # Fallback: procedural diamond pattern
    bg = Image.new('RGBA', (width, height), BG_COLOR)
    draw = ImageDraw.Draw(bg, 'RGBA')
    spacing = 120
    for y in range(-80, height + 80, spacing):
        for x in range(-80, width + 80, spacing):
            x_offset = spacing // 2 if (y // spacing) % 2 else 0
            cx, cy = x + x_offset, y
            draw.polygon([(cx, cy-27), (cx+27, cy), (cx, cy+27), (cx-27, cy)],
                         fill=(0x38, 0xab, 0xa3, 25))
            draw.polygon([(cx, cy-13), (cx+13, cy), (cx, cy+13), (cx-13, cy)],
                         fill=(0x00, 0x81, 0x6d, 25))
    return bg.convert('RGB')


class DepartureBoard:
    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_COLOR)

        hdr = tk.Frame(self.frame, bg=BG_SECONDARY, padx=16, pady=10)
        hdr.pack(fill='x')
        tk.Label(hdr, text="LINJE", font=FONT_TABLE_HEADER,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).pack(side='left', padx=(0, 15))
        tk.Label(hdr, text="RETNING", font=FONT_TABLE_HEADER,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).pack(side='left')
        tk.Label(hdr, text="AVGANG", font=FONT_TABLE_HEADER,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).pack(side='right')

        self.rows_frame = tk.Frame(self.frame, bg=BG_COLOR)
        self.rows_frame.pack(fill='both', expand=True, pady=(10, 0))

        self.dest_headers = []
        self.dep_rows = []

        for _ in range(8):
            hdr_lbl = tk.Label(self.rows_frame, text="", font=FONT_SUBHEADING,
                               bg=BG_COLOR, fg=ACCENT_COLOR, anchor='w')
            self.dest_headers.append(hdr_lbl)
            group = []
            for _ in range(MAX_PER_DEST):
                row_frame = tk.Frame(self.rows_frame, bg=BG_COLOR)
                line_lbl = tk.Label(row_frame, text="", font=FONT_LINE_BADGE,
                                    bg=ACCENT_COLOR, fg='#FFFFFF', width=4, anchor='center')
                dest_lbl = tk.Label(row_frame, text="", font=FONT_BODY,
                                    bg=BG_COLOR, fg=TEXT_COLOR, anchor='w')
                time_lbl = tk.Label(row_frame, text="", font=FONT_TIME,
                                    bg=BG_COLOR, fg=HEADING_COLOR, anchor='e')
                line_lbl.pack(side='left', padx=(16, 8), ipady=2)
                dest_lbl.pack(side='left', padx=(8, 0), fill='x', expand=True)
                time_lbl.pack(side='right', padx=16)
                group.append((row_frame, line_lbl, dest_lbl, time_lbl))
            self.dep_rows.append(group)

        self.no_data_label = tk.Label(self.rows_frame, text="", font=FONT_BODY,
                                       bg=BG_COLOR, fg=SUBTEXT_COLOR)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def update_display(self):
        with departures_lock:
            deps = list(cached_departures)

        grouped = defaultdict(list)
        for d in deps:
            grouped[d["destination"]].append(d)
        sorted_groups = sorted(grouped.items(), key=lambda kv: kv[1][0]["time"])

        if not sorted_groups:
            self.no_data_label.config(text="INGEN DATA")
            self.no_data_label.pack(pady=20)
            for dh in self.dest_headers:
                dh.pack_forget()
            for group in self.dep_rows:
                for row_frame, _, _, _ in group:
                    row_frame.pack_forget()
            return

        self.no_data_label.pack_forget()

        row_idx = 0
        for dest, group in sorted_groups:
            if row_idx >= len(self.dest_headers):
                break

            group.sort(key=lambda x: x["time"])
            self.dest_headers[row_idx].config(text=f"→ {dest.upper()}")
            self.dest_headers[row_idx].pack(fill='x', pady=(12, 4))

            for i, dep in enumerate(group[:MAX_PER_DEST]):
                if i >= len(self.dep_rows[row_idx]):
                    break
                time_text = format_time(dep["time"])
                if not time_text:
                    continue
                row_frame, line_lbl, dest_lbl, time_lbl = self.dep_rows[row_idx][i]
                line_lbl.config(text=dep['line'])
                dest_lbl.config(text=dep['destination'])
                time_lbl.config(text=time_text)
                row_frame.pack(fill='x', pady=3)

            for i in range(min(len(group), MAX_PER_DEST), MAX_PER_DEST):
                self.dep_rows[row_idx][i][0].pack_forget()

            row_idx += 1

        for idx in range(row_idx, len(self.dest_headers)):
            self.dest_headers[idx].pack_forget()
            for row_frame, _, _, _ in self.dep_rows[idx]:
                row_frame.pack_forget()


class DiscordPanel:
    """Panel showing recent messages from 1IM-Fellesinfo Discord channel."""

    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_SECONDARY, padx=20, pady=16)

        # Header with emoji
        header_frame = tk.Frame(self.frame, bg=BG_SECONDARY)
        header_frame.pack(fill='x', pady=(0, 12))
        tk.Label(header_frame, text="📢 1IM-FELLESINFO", font=FONT_SUBHEADING,
                 bg=BG_SECONDARY, fg=HEADING_COLOR, anchor='w').pack(side='left')

        self.msg_container = tk.Frame(self.frame, bg=BG_SECONDARY)
        self.msg_container.pack(fill='both', expand=True)

        self.msg_labels = []
        for _ in range(CONFIG.get("discord_max_messages", 8)):
            msg_frame = tk.Frame(self.msg_container, bg=BG_SECONDARY)
            author_lbl = tk.Label(msg_frame, font=FONT_DISCORD_AUTHOR,
                                  bg=BG_SECONDARY, fg=IM_TEAL, anchor='w')
            content_lbl = tk.Label(msg_frame, font=FONT_DISCORD_MSG,
                                  bg=BG_SECONDARY, fg=TEXT_COLOR, anchor='w',
                                  wraplength=320, justify='left')
            time_lbl = tk.Label(msg_frame, font=FONT_DISCORD_TIME,
                                bg=BG_SECONDARY, fg=SUBTEXT_COLOR, anchor='e')

            author_lbl.pack(side='left', padx=(0, 6))
            time_lbl.pack(side='right', padx=(6, 0))
            content_lbl.pack(side='left', fill='x', expand=True)

            self.msg_labels.append((msg_frame, author_lbl, content_lbl, time_lbl))

        self.no_data_label = tk.Label(self.msg_container, text="Ingen meldinger",
                                       font=FONT_BODY, bg=BG_SECONDARY, fg=SUBTEXT_COLOR)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def update_display(self):
        with discord_lock:
            msgs = list(discord_messages)

        if not msgs:
            self.no_data_label.pack(pady=20)
            for msg_frame, _, _, _ in self.msg_labels:
                msg_frame.pack_forget()
            # Also show setup hint if no Discord config
            if not CONFIG.get("discord_bot_token") or not CONFIG.get("discord_channel_id"):
                self.no_data_label.config(
                    text="Sett opp Discord i config.json\n(Se README for instruksjoner)")
            return

        self.no_data_label.pack_forget()

        for i, (msg_frame, author_lbl, content_lbl, time_lbl) in enumerate(self.msg_labels):
            if i < len(msgs):
                msg = msgs[i]
                author_lbl.config(text=msg["author"])
                content_lbl.config(text=msg["content"])
                time_lbl.config(text=msg["time"])
                msg_frame.pack(fill='x', pady=2)
            else:
                msg_frame.pack_forget()


class OrdenTable:
    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_SECONDARY, padx=20, pady=16)

        tk.Label(self.frame, text="ORDENSVAKT", font=FONT_SUBHEADING,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).grid(
                     row=0, column=0, columnspan=6, sticky='w', pady=(0, 12))

        headers = ['UKE', 'DATO', '1IM1', '1IM2', 'STOL', 'VASK']
        for col, header in enumerate(headers):
            tk.Label(self.frame, text=header, font=FONT_TABLE_HEADER,
                     bg=BG_SECONDARY, fg=HEADING_COLOR).grid(
                         row=1, column=col, padx=8, pady=(0, 6), sticky='w')

        self.cells = []
        for row in range(2, 28):
            row_cells = []
            for col in range(6):
                lbl = tk.Label(self.frame, text="", font=FONT_BODY_SMALL,
                               bg=BG_SECONDARY, fg=TEXT_COLOR)
                lbl.grid(row=row, column=col, padx=8, pady=2, sticky='w')
                row_cells.append(lbl)
            self.cells.append(row_cells)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def update_display(self):
        orden_data = fetch_orden()
        current_week = datetime.datetime.now(LOCAL_TZ).isocalendar()[1]

        row_idx = 0
        for uke, info in orden_data.items():
            if row_idx >= len(self.cells):
                break
            week_num = int(uke[3:])
            if week_num == current_week:
                color = HEADING_COLOR
                font_style = FONT_BODY_BOLD
            elif week_num < current_week:
                color = SUBTEXT_COLOR
                font_style = ('Arial', 14, 'overstrike')
            else:
                color = TEXT_COLOR
                font_style = FONT_BODY_SMALL

            data = [uke, info['dato'], info['1IM1'], info['1IM2'],
                    info['stoler'], info['vasking']]
            for col, val in enumerate(data):
                self.cells[row_idx][col].config(text=val, fg=color, font=font_style)
            row_idx += 1


# === GUI Setup ===
root = tk.Tk()
root.attributes('-fullscreen', True)
root.configure(bg=BG_COLOR)
init_fonts()

# === Pattern background ===
screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()
try:
    bg_image_pil = create_pattern_bg(screen_w, screen_h)
    bg_photo = ImageTk.PhotoImage(bg_image_pil)
    bg_label = tk.Label(root, image=bg_photo, bg=BG_COLOR)
    bg_label.place(x=0, y=0, relwidth=1, relheight=1)
    bg_label.image = bg_photo
except Exception as e:
    log(f"Background pattern failed ({e}), using solid color")

# === Header ===
title_frame = tk.Frame(root, bg=BG_COLOR)
title_frame.pack(fill='x', pady=(20, 10), padx=40)

im_badge = tk.Frame(title_frame, bg=IM_TEAL, padx=14, pady=4)
im_badge.pack(side='left', padx=(0, 16))
tk.Label(im_badge, text="IM", font=FONT_IM_BADGE,
         bg=IM_TEAL, fg='#FFFFFF').pack()

tk.Label(title_frame, text="BUSSAVGANGER — CHARLOTTENLUND VGS",
         font=FONT_TITLE, bg=BG_COLOR, fg=HEADING_COLOR).pack(side='left')

time_label = tk.Label(title_frame, text='', font=FONT_CLOCK,
                      bg=BG_COLOR, fg=TEXT_COLOR)
time_label.pack(side='right', padx=40)

status_label = tk.Label(title_frame, text='', font=FONT_STATUS,
                        bg=BG_COLOR, fg=TEXT_COLOR)
status_label.pack(side='right', padx=(0, 20))

# === Separator ===
sep = tk.Frame(root, bg=ACCENT_COLOR, height=2)
sep.pack(fill='x', padx=40, pady=(0, 10))

# === Main content — 3 columns: Buss | Discord | Orden ===
main_container = tk.Frame(root, bg=BG_COLOR)
main_container.pack(expand=True, fill='both', padx=40, pady=(0, 20))

# Column 1: Bussavganger (left, expanding)
board = DepartureBoard(main_container)
board.pack(side='left', fill='both', expand=True, padx=(0, 12))

# Column 2: Discord (center, fixed-ish width)
discord = DiscordPanel(main_container)
discord.pack(side='left', fill='both', expand=False, padx=(0, 12))

# Column 3: Ordensvakt (right, fixed width)
orden = OrdenTable(main_container)
orden.pack(side='right', fill='both', expand=False)

root.bind('<Escape>', lambda e: root.destroy())


def update_time():
    time_label.config(text=datetime.datetime.now(LOCAL_TZ).strftime('%H:%M:%S'))
    root.after(1000, update_time)


def update_departures():
    board.update_display()
    if not is_online:
        status_label.config(text="⚠ OFFLINE", fg=ALERT_COLOR)
    elif last_update:
        ago = int((datetime.datetime.now(LOCAL_TZ) - last_update).total_seconds())
        if ago > 120:
            status_label.config(text=f"Oppdatert {ago // 60}min siden", fg=ALERT_COLOR)
        else:
            status_label.config(text="", fg=TEXT_COLOR)
    root.after(10000, update_departures)


def update_orden():
    orden.update_display()
    root.after(REFRESH_ORDEN_MIN * 60 * 1000, update_orden)


def update_discord():
    discord.update_display()
    root.after(CONFIG.get("discord_refresh_sec", 60) * 1000, update_discord)


fetch_thread = threading.Thread(target=fetch_loop, daemon=True)
fetch_thread.start()

update_time()
update_departures()
update_orden()
update_discord()
root.mainloop()