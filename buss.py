"""Bus departure board — Entur GraphQL fetcher and display widget."""
import tkinter as tk
import datetime
import threading
from collections import defaultdict

import requests

from felles import (
    LOCAL_TZ, SCRIPT_DIR, log,
    PAGE_BG, HEADING_YELLOW, WHITE, TEAL,
    px, font, rounded_image,
)

# === Constants ===
GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
GRAPHQL_HEADERS = {
    'ET-Client-Name': 'Charlottenlund vgs IM',
    'Content-Type': 'application/json',
}
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
MAX_PER_DEST = 3
REFRESH_API_SEC = 60

# === State ===
cached_departures = []
last_update = None
is_online = True
departures_lock = threading.Lock()


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
        self.grid.pack(fill='both', expand=True, padx=px(6), pady=(px(4), px(6)))

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