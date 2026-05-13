import tkinter as tk
import requests
import xmltodict
import datetime
import json
import threading
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

# === Colors ===
BG_COLOR = '#0b0f14'
NEON_YELLOW = '#FFC700'
NEON_BLUE = '#00ADEF'
TEXT_COLOR = '#E6F0FF'
SUBTEXT_COLOR = '#A8C0D8'

# === State ===
cached_departures = []
last_update = None
is_online = True
departures_lock = threading.Lock()


def log(msg):
    now = datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    with open("infoboard.log", "a", encoding="utf-8") as f:
        f.write(f"[{now}] {msg}\n")


def fetch_orden():
    with open('orden.json', 'r', encoding="UTF-8") as f:
        return json.load(f)


def parse_departures():
    """Fetch and parse departures from API. Returns list or None on error."""
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
        log(f"✅ Updated from API ({len(cached_departures)} departures)")
        return True
    except Exception as e:
        is_online = False
        log(f"⚠️ API fetch failed ({e})")
        return False


def fetch_loop():
    """Background thread: fetch API periodically."""
    while True:
        parse_departures()
        threading.Event().wait(REFRESH_API_SEC)


def format_time(dep_time):
    now = datetime.datetime.now(LOCAL_TZ)
    delta = int((dep_time - now).total_seconds() / 60)
    if delta < 0:
        return ""
    if delta == 0:
        return "Nå"
    elif delta < 15:
        return f"{delta} min"
    else:
        return dep_time.strftime("%H:%M")


# === Pre-built widget rows ===
class DepartureBoard:
    """Departure board with pre-created widgets — only text updates, no destroy/create."""

    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_COLOR)

        # Header
        hdr = tk.Frame(self.frame, bg=BG_COLOR)
        hdr.pack(fill='x')
        tk.Label(hdr, text="Linje", font=('Arial', 28, 'bold'),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(side='left', padx=10)
        tk.Label(hdr, text="Retning", font=('Arial', 28, 'bold'),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(side='left', padx=20)
        tk.Label(hdr, text="Avgang", font=('Arial', 28, 'bold'),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(side='right', padx=20)

        self.rows_frame = tk.Frame(self.frame, bg=BG_COLOR)
        self.rows_frame.pack(fill='both', expand=True)

        # Pre-create max rows (dest header + 5 departures per dest, ~8 dests max)
        self.dest_headers = []
        self.dep_rows = []  # list of (line_label, dest_label, time_label)

        for _ in range(8):
            hdr_lbl = tk.Label(self.rows_frame, text="", font=('Arial', 26, 'bold'),
                               bg=BG_COLOR, fg=NEON_BLUE, anchor='w')
            self.dest_headers.append(hdr_lbl)
            group = []
            for _ in range(MAX_PER_DEST):
                row_frame = tk.Frame(self.rows_frame, bg=BG_COLOR)
                line_lbl = tk.Label(row_frame, text="", font=('Arial', 24, 'bold'),
                                    bg=BG_COLOR, fg=NEON_BLUE, width=5, anchor='w')
                dest_lbl = tk.Label(row_frame, text="", font=('Arial', 24),
                                    bg=BG_COLOR, fg=TEXT_COLOR, anchor='w')
                time_lbl = tk.Label(row_frame, text="", font=('Arial', 24),
                                    bg=BG_COLOR, fg=NEON_YELLOW, anchor='e')
                line_lbl.pack(side='left', padx=10)
                dest_lbl.pack(side='left', padx=20, fill='x', expand=True)
                time_lbl.pack(side='right', padx=20)
                group.append((row_frame, line_lbl, dest_lbl, time_lbl))
            self.dep_rows.append(group)

        self.no_data_label = tk.Label(self.rows_frame, text="", font=('Arial', 24),
                                       bg=BG_COLOR, fg=SUBTEXT_COLOR)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def update_display(self):
        with departures_lock:
            deps = list(cached_departures)

        # Group by destination
        grouped = defaultdict(list)
        for d in deps:
            grouped[d["destination"]].append(d)
        sorted_groups = sorted(grouped.items(), key=lambda kv: kv[1][0]["time"])

        row_idx = 0
        visible_rows = 0

        if not sorted_groups:
            self.no_data_label.config(text="Ingen data")
            self.no_data_label.grid(row=0, column=0, columnspan=3, pady=20)
            # Hide all pre-created rows
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

            # Show dest header
            self.dest_headers[row_idx].config(text=f"→ {dest}")
            self.dest_headers[row_idx].pack(fill='x', pady=(10, 5))

            # Show departures
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

            # Hide unused departure slots for this group
            for i in range(min(len(group), MAX_PER_DEST), MAX_PER_DEST):
                row_frame, line_lbl, dest_lbl, time_lbl = self.dep_rows[row_idx][i]
                row_frame.pack_forget()

            row_idx += 1

        # Hide unused dest groups entirely
        for idx in range(row_idx, len(self.dest_headers)):
            self.dest_headers[idx].pack_forget()
            for row_frame, _, _, _ in self.dep_rows[idx]:
                row_frame.pack_forget()


class OrdenTable:
    """Orden table with pre-created widgets. Rebuilds text only, not widgets."""

    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_COLOR)

        headers = ['Uke', 'Dato', '1IM1', '1IM2', 'Stol', 'Vasking']
        for col, header in enumerate(headers):
            tk.Label(self.frame, text=header, font=('Arial', 16, 'bold'),
                     bg=BG_COLOR, fg=NEON_YELLOW).grid(row=0, column=col, padx=7, pady=5, sticky='w')

        self.cells = []
        # Pre-create 26 week rows (covers full year)
        for row in range(1, 27):
            row_cells = []
            for col in range(6):
                lbl = tk.Label(self.frame, text="", font=('Arial', 13),
                               bg=BG_COLOR, fg=TEXT_COLOR)
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
                color = NEON_BLUE
                font_style = ('Arial', 13)
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

# Title bar
title_frame = tk.Frame(root, bg=BG_COLOR)
title_frame.pack(fill='x', pady=20)

tk.Label(title_frame, text="Bussavganger – Charlottenlund vgs",
         font=('Arial', 40, 'bold'), bg=BG_COLOR, fg=NEON_YELLOW).pack(side='left', padx=50)

time_label = tk.Label(title_frame, text='', font=('Arial', 36),
                      bg=BG_COLOR, fg=TEXT_COLOR)
time_label.pack(side='right', padx=50)

status_label = tk.Label(title_frame, text='', font=('Arial', 20),
                        bg=BG_COLOR, fg=TEXT_COLOR)
status_label.pack(side='right', padx=30)

# Main content
main_container = tk.Frame(root, bg=BG_COLOR)
main_container.pack(expand=True, fill='both', padx=20)

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
        status_label.config(text="⚠ Offline", fg=SUBTEXT_COLOR)
    elif last_update:
        ago = int((datetime.datetime.now(LOCAL_TZ) - last_update).total_seconds())
        status_label.config(text=f"Oppdatert {ago}s siden", fg=SUBTEXT_COLOR)
    root.after(10000, update_departures)


def update_orden():
    orden.update_display()
    root.after(REFRESH_ORDEN_MIN * 60 * 1000, update_orden)


# Start background API fetcher
fetch_thread = threading.Thread(target=fetch_loop, daemon=True)
fetch_thread.start()

# Initial fetch then start UI updates
update_time()
update_departures()
update_orden()
root.mainloop()