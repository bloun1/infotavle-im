import tkinter as tk
import requests
import xmltodict
import datetime
import json
import threading
import os
from PIL import Image, ImageTk, ImageDraw
from datetime import timezone, timedelta
from collections import defaultdict

# === Timezone setup ===
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Oslo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=1))

# === Constants ===
API_URL = "https://api.entur.io/realtime/v1/rest/et?datasetId=ATB"
HEADERS = {'ET-Client-Name': 'Charlottenlund vgs'}
STOP_PLACE = "NSR:Quay:75404"
MAX_DEPARTURES = 12
MAX_PER_DEST = 5
REFRESH_API_SEC = 60
REFRESH_ORDEN_MIN = 5
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# === Charlottenlund vgs Visual Profile Colors ===
BG_COLOR = '#3C1053'
BG_SECONDARY = '#4A1366'
HEADING_COLOR = '#FFD244'
ACCENT_COLOR = '#00816D'
ACCENT_DARK = '#006C5B'
TEXT_COLOR = '#FFFFFF'
SUBTEXT_COLOR = '#B89CC8'
ALERT_COLOR = '#EA560D'

# IM line colors (from IM visual identity)
IM_TEAL = '#38aba3'
IM_TEAL_DARK = '#00816d'

# === Fonts ===
FONT_HEADING = ('Arial', 40, 'bold')
FONT_SUBHEADING = ('Arial', 28, 'bold')
FONT_BODY = ('Arial', 24)
FONT_BODY_SMALL = ('Arial', 13)
FONT_TABLE_HEADER = ('Arial', 16, 'bold')
FONT_TITLE = ('Arial', 40, 'bold')
FONT_CLOCK = ('Arial', 36)
FONT_STATUS = ('Arial', 20)
FONT_IM_LABEL = ('Arial', 36, 'bold')

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


def parse_departures():
    global cached_departures, last_update, is_online
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=6)
        response.raise_for_status()
        doc = xmltodict.parse(response.text)

        journeys = doc["Siri"]["ServiceDelivery"]["EstimatedTimetableDelivery"]["EstimatedJourneyVersionFrame"]["EstimatedVehicleJourney"]
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
                        dep_time = datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
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
    """Create the IM pattern background with geometric diamonds on Charlottenlund purple."""
    bg = Image.new('RGBA', (width, height), BG_COLOR)
    draw = ImageDraw.Draw(bg, 'RGBA')

    diamond_size = 80
    spacing = 120
    opacity = 25

    pattern_color = (0x38, 0xab, 0xa3, opacity)
    pattern_color2 = (0x00, 0x81, 0x6d, opacity)

    for y in range(-diamond_size, height + diamond_size, spacing):
        for x in range(-diamond_size, width + diamond_size, spacing):
            x_offset = spacing // 2 if (y // spacing) % 2 else 0
            cx = x + x_offset
            cy = y

            points = [
                (cx, cy - diamond_size // 3),
                (cx + diamond_size // 3, cy),
                (cx, cy + diamond_size // 3),
                (cx - diamond_size // 3, cy),
            ]
            draw.polygon(points, fill=pattern_color)

            inner_size = diamond_size // 6
            inner_points = [
                (cx, cy - inner_size),
                (cx + inner_size, cy),
                (cx, cy + inner_size),
                (cx - inner_size, cy),
            ]
            draw.polygon(inner_points, fill=pattern_color2)

    return bg.convert('RGB')


class DepartureBoard:
    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_COLOR)

        # Header row
        hdr = tk.Frame(self.frame, bg=BG_SECONDARY)
        hdr.pack(fill='x', ipady=8)
        tk.Label(hdr, text="LINJE", font=FONT_SUBHEADING,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).pack(side='left', padx=15)
        tk.Label(hdr, text="RETNING", font=FONT_SUBHEADING,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).pack(side='left', padx=20)
        tk.Label(hdr, text="AVGANG", font=FONT_SUBHEADING,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).pack(side='right', padx=20)

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
                line_lbl = tk.Label(row_frame, text="", font=('Arial', 22, 'bold'),
                                    bg=ACCENT_COLOR, fg='#FFFFFF', width=5, anchor='center')
                dest_lbl = tk.Label(row_frame, text="", font=FONT_BODY,
                                    bg=BG_COLOR, fg=TEXT_COLOR, anchor='w')
                time_lbl = tk.Label(row_frame, text="", font=('Arial', 24, 'bold'),
                                    bg=BG_COLOR, fg=HEADING_COLOR, anchor='e')
                line_lbl.pack(side='left', padx=(10, 5), ipady=2)
                dest_lbl.pack(side='left', padx=20, fill='x', expand=True)
                time_lbl.pack(side='right', padx=20)
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

        row_idx = 0
        visible_rows = 0

        if not sorted_groups:
            self.no_data_label.config(text="INGEN DATA")
            self.no_data_label.grid(row=0, column=0, columnspan=3, pady=20)
            for dh in self.dest_headers:
                dh.pack_forget()
            for group in self.dep_rows:
                for row_frame, _, _, _ in group:
                    row_frame.pack_forget()
            return

        self.no_data_label.pack_forget()

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
                visible_rows += 1

            for i in range(min(len(group), MAX_PER_DEST), MAX_PER_DEST):
                row_frame, line_lbl, dest_lbl, time_lbl = self.dep_rows[row_idx][i]
                row_frame.pack_forget()

            row_idx += 1

        for idx in range(row_idx, len(self.dest_headers)):
            self.dest_headers[idx].pack_forget()
            for row_frame, _, _, _ in self.dep_rows[idx]:
                row_frame.pack_forget()


class OrdenTable:
    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_SECONDARY, padx=15, pady=10)

        tk.Label(self.frame, text="ORDENSVAKT", font=FONT_SUBHEADING,
                 bg=BG_SECONDARY, fg=HEADING_COLOR).grid(row=0, column=0, columnspan=6, sticky='w', pady=(0, 8))

        headers = ['UKE', 'DATO', '1IM1', '1IM2', 'STOL', 'VASK']
        for col, header in enumerate(headers):
            tk.Label(self.frame, text=header, font=FONT_TABLE_HEADER,
                     bg=BG_SECONDARY, fg=HEADING_COLOR).grid(row=1, column=col, padx=7, pady=5, sticky='w')

        self.cells = []
        for row in range(2, 28):
            row_cells = []
            for col in range(6):
                lbl = tk.Label(self.frame, text="", font=FONT_BODY_SMALL,
                               bg=BG_SECONDARY, fg=TEXT_COLOR)
                lbl.grid(row=row, column=col, padx=7, pady=3, sticky='w')
                row_cells.append(lbl)
            self.cells.append(row_cells)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def update_display(self):
        orden_data = fetch_orden()
        current_week = datetime.datetime.now().isocalendar()[1]

        row_idx = 0
        for uke, info in orden_data.items():
            if row_idx >= len(self.cells):
                break
            week_num = int(uke[3:])
            if week_num == current_week:
                color = HEADING_COLOR
                font_style = ('Arial', 13, 'bold')
            elif week_num < current_week:
                color = SUBTEXT_COLOR
                font_style = ('Arial', 13, 'overstrike')
            else:
                color = TEXT_COLOR
                font_style = ('Arial', 13)

            data = [uke, info['dato'], info['1IM1'], info['1IM2'], info['stoler'], info['vasking']]
            for col, val in enumerate(data):
                self.cells[row_idx][col].config(text=val, fg=color, font=font_style)
            row_idx += 1


# === GUI Setup ===
root = tk.Tk()
root.attributes('-fullscreen', True)
root.configure(bg=BG_COLOR)

# === Pattern background ===
screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()
try:
    bg_image_pil = create_pattern_bg(screen_w, screen_h)
    bg_photo = ImageTk.PhotoImage(bg_image_pil)

    bg_label = tk.Label(root, image=bg_photo, bg=BG_COLOR)
    bg_label.place(x=0, y=0, relwidth=1, relheight=1)
    bg_label.image = bg_photo  # prevent GC
except Exception as e:
    log(f"Background pattern failed ({e}), using solid color")

# === IM Logo in header ===
try:
    logo_pil = Image.open(os.path.join(SCRIPT_DIR, 'im_logo_small.png')).convert('RGBA')
    # Make white background transparent
    logo_data = logo_pil.getdata()
    new_logo_data = []
    for item in logo_data:
        r, g, b, a = item
        if r > 240 and g > 240 and b > 240:
            new_logo_data.append((0, 0, 0, 0))
        else:
            new_logo_data.append((r, g, b, a))
    logo_pil.putdata(new_logo_data)

    # Create a version on purple background for tkinter (which doesn't handle alpha well)
    logo_bg = Image.new('RGBA', logo_pil.size, BG_COLOR)
    logo_bg.paste(logo_pil, (0, 0), logo_pil)
    logo_photo = ImageTk.PhotoImage(logo_bg.convert('RGB'))
except Exception as e:
    log(f"Logo load failed ({e})")
    logo_photo = None

# === Header with IM branding ===
title_frame = tk.Frame(root, bg=BG_COLOR)
title_frame.pack(fill='x', pady=20, padx=40)

if logo_photo:
    logo_label = tk.Label(title_frame, image=logo_photo, bg=BG_COLOR)
    logo_label.pack(side='left', padx=(0, 15))
    logo_label.image = logo_photo  # prevent GC

# Title with IM line name
im_label = tk.Label(title_frame, text="IM", font=FONT_IM_LABEL,
                    bg=BG_COLOR, fg=IM_TEAL)
im_label.pack(side='left', padx=(0, 10))

title_label = tk.Label(title_frame, text="— BUSSAVGANGER — CHARLOTTENLUND VGS",
                        font=FONT_TITLE, bg=BG_COLOR, fg=HEADING_COLOR)
title_label.pack(side='left')

time_label = tk.Label(title_frame, text='', font=FONT_CLOCK,
                      bg=BG_COLOR, fg=TEXT_COLOR)
time_label.pack(side='right', padx=50)

status_label = tk.Label(title_frame, text='', font=FONT_STATUS,
                        bg=BG_COLOR, fg=TEXT_COLOR)
status_label.pack(side='right', padx=30)

main_container = tk.Frame(root, bg=BG_COLOR)
main_container.pack(expand=True, fill='both', padx=30, pady=(0, 20))

board = DepartureBoard(main_container)
board.pack(side='left', fill='both', expand=True, padx=(0, 20))

orden = OrdenTable(main_container)
orden.pack(side='right', fill='both', expand=False, padx=(0, 0))

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
        status_label.config(text=f"Oppdatert {ago}s siden", fg=SUBTEXT_COLOR)
    root.after(10000, update_departures)


def update_orden():
    orden.update_display()
    root.after(REFRESH_ORDEN_MIN * 60 * 1000, update_orden)


fetch_thread = threading.Thread(target=fetch_loop, daemon=True)
fetch_thread.start()

update_time()
update_departures()
update_orden()
root.mainloop()