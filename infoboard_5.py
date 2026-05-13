import tkinter as tk
import requests
import xmltodict
import datetime
import json
from datetime import timezone, timedelta
from collections import defaultdict

# === Timezone setup ===
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Oslo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=1))  # fallback for Windows

# === Constants ===
API_URL = "https://api.entur.io/realtime/v1/rest/et?datasetId=ATB"
HEADERS = {'ET-Client-Name': 'Charlottenlund vgs'}
STOP_PLACE = "NSR:Quay:75404"

# === Colors ===
BG_COLOR = '#0b0f14'       
NEON_YELLOW = '#FFC700'   
NEON_BLUE = '#00ADEF'       
TEXT_COLOR = '#E6F0FF'     
SUBTEXT_COLOR = '#A8C0D8'

# === Globals ===
cached_departures = []
last_update = None
is_online = True


# === Helpers ===
def log(msg):
    now = datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    with open("infoboard.log", "a", encoding="utf-8") as f:
        f.write(f"[{now}] {msg}\n")


def fetch_orden():
    with open('orden.json', 'r', encoding="UTF-8") as f:
        return json.load(f)


def fetch_departures():
    """Fetch and cache departures, group by destination."""
    global cached_departures, last_update, is_online
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=6)
        response.raise_for_status()
        xml_content = response.text
        doc = xmltodict.parse(xml_content)

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

                        # --- Destination normalization ---
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
        cached_departures = departures[:12]
        last_update = datetime.datetime.now(LOCAL_TZ)
        is_online = True
        log(f"✅ Updated from API ({len(cached_departures)} departures)")
        return cached_departures

    except Exception as e:
        is_online = False
        log(f"⚠️ Using cached data ({e})")
        return cached_departures

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


# === Drawing Functions ===
def draw_board():
    for widget in board_frame.winfo_children():
        widget.destroy()

    # Header row
    tk.Label(board_frame, text="Linje", font=('Arial', 28, 'bold'),
             bg=BG_COLOR, fg=TEXT_COLOR).grid(row=0, column=0, padx=10)
    tk.Label(board_frame, text="Retning", font=('Arial', 28, 'bold'),
             bg=BG_COLOR, fg=TEXT_COLOR).grid(row=0, column=1, sticky="w", padx=20)
    tk.Label(board_frame, text="Avgang", font=('Arial', 28, 'bold'),
             bg=BG_COLOR, fg=TEXT_COLOR).grid(row=0, column=2, sticky="e", padx=20)

    departures = fetch_departures()
    if not departures:
        tk.Label(board_frame, text="Ingen data", font=('Arial', 24),
                 bg=BG_COLOR, fg=SUBTEXT_COLOR).grid(row=1, column=0, columnspan=3, pady=20)
        return

    # Group by destination
    grouped = defaultdict(list)
    for d in departures:
        grouped[d["destination"]].append(d)

    # Sort by next departure time
    sorted_groups = sorted(grouped.items(), key=lambda kv: kv[1][0]["time"])

    row = 1
    for dest, group in sorted_groups:
        tk.Label(board_frame, text=f"→ {dest}", font=('Arial', 26, 'bold'),
                 bg=BG_COLOR, fg=NEON_BLUE).grid(row=row, column=0, columnspan=3, pady=(10, 5))
        row += 1

        group.sort(key=lambda x: x["time"])
        for dep in group[:5]:
            time_text = format_time(dep["time"])
            if not time_text:
                continue
            tk.Label(board_frame, text=dep['line'], font=('Arial', 24, 'bold'),
                     bg=BG_COLOR, fg=NEON_BLUE).grid(row=row, column=0, pady=5)
            tk.Label(board_frame, text=dep['destination'], font=('Arial', 24),
                     bg=BG_COLOR, fg=TEXT_COLOR).grid(row=row, column=1, padx=20, pady=5, sticky="w")
            tk.Label(board_frame, text=time_text, font=('Arial', 24),
                     bg=BG_COLOR, fg=NEON_YELLOW).grid(row=row, column=2, padx=20, pady=5, sticky="e")
            row += 1


def draw_orden_table():
    orden_data = fetch_orden()
    for widget in orden_frame.winfo_children():
        widget.destroy()

    headers = ['Uke', 'Dato', '1IM1', '1IM2', 'Stol', 'Vasking']
    for col, header in enumerate(headers):
        tk.Label(orden_frame, text=header, font=('Arial', 16, 'bold'),
                 bg=BG_COLOR, fg=NEON_YELLOW).grid(row=0, column=col, padx=7, pady=5, sticky='w')

    current_week = datetime.datetime.now().isocalendar().week
    for i, (uke, info) in enumerate(orden_data.items(), start=1):
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
            tk.Label(orden_frame, text=val, font=font_style,
                     bg=BG_COLOR, fg=color).grid(row=i, column=col, padx=7, pady=3, sticky='w')

# === Periodic Updates ===
def refresher():
    draw_board()
    draw_orden_table()
    root.after(60000, refresher)


def update_time():
    time_label.config(text=datetime.datetime.now(LOCAL_TZ).strftime('%H:%M:%S'))
    root.after(1000, update_time)


# === GUI Setup ===
root = tk.Tk()
root.attributes('-fullscreen', True)
root.configure(bg=BG_COLOR)

# --- Title bar ---
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

# --- Main content ---
main_container = tk.Frame(root, bg=BG_COLOR)
main_container.pack(expand=True, fill='both', padx=20)

board_frame = tk.Frame(main_container, bg=BG_COLOR)
board_frame.pack(side='left', fill='both', expand=True, padx=(0, 20))

orden_frame = tk.Frame(main_container, bg=BG_COLOR)
orden_frame.pack(side='right', fill='both', expand=False, padx=(0, 0))

root.bind('<Escape>', lambda e: root.destroy())

update_time()
refresher()
root.mainloop()
