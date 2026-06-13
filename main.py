"""Infotavle-IM main entry point — starts all panels in sequence on Raspberry Pi."""
import os
import threading
import datetime

import tkinter as tk
from PIL import Image, ImageTk

from felles import (
    LOCAL_TZ, SCRIPT_DIR, PAGE_BG, HEADING_YELLOW,
    PAGE_SURFACE, YELLOW_SURFACE, ORDEN_SURFACE,
    px, font, rounded_image, log,
)
from buss import DepartureBoard, fetch_loop, is_online, last_update, REFRESH_API_SEC
from ordens import OrdenTable, REFRESH_ORDEN_MIN
from bursdag import BirthdayPanel
from discord import DiscordPanel, fetch_discord
from weather import WeatherPanel, fetch_weather_loop


# === GUI Setup ===
root = tk.Tk()
root.attributes('-fullscreen', True)
root.configure(bg=PAGE_BG)

# Compute scale factor and apply to shared module
screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()
import felles
felles.screen_w = screen_w
felles.S = screen_w / 1280.0


# R10: Background pattern
bg_pattern_photo = None


def load_bg_pattern():
    """R10/R14: Load bg_pattern, use cached resize if available."""
    global bg_pattern_photo
    cache_path = os.path.join(SCRIPT_DIR, f'bg_pattern_{screen_w}x{screen_h}.png')
    try:
        if os.path.exists(cache_path):
            img = Image.open(cache_path)
            img.load()
        else:
            img = Image.open(os.path.join(SCRIPT_DIR, 'bg_pattern_real.png'))
            img = img.resize((screen_w, screen_h), Image.LANCZOS)
            try:
                img.save(cache_path, 'PNG', optimize=True)
                log(f"Cached bg_pattern to {cache_path}")
            except OSError as e:
                log(f"Cache save failed: {e}")
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
        return img
    except Exception:
        return None


# === Header ===
header_frame = tk.Frame(root, bg=PAGE_BG)

IM_BADGE_PAD = 5
im_badge_h = px(36)
im_badge_w = im_badge_h
logo_inner_h = im_badge_h - 2 * px(IM_BADGE_PAD)
logo_inner_w = im_badge_w - 2 * px(IM_BADGE_PAD)

im_badge_canvas = tk.Canvas(header_frame, width=im_badge_w, height=im_badge_h,
                             bg=PAGE_BG, highlightthickness=0)
im_badge_photo = rounded_image(im_badge_w, im_badge_h, px(8), '#FCC745')
im_badge_canvas.create_image(0, 0, anchor='nw', image=im_badge_photo)

raw_logo = load_logo()
if raw_logo:
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

# Status
status_label = tk.Label(header_frame, text='', font=font(11),
                        bg=PAGE_BG, fg='#949BA4')
status_label.pack(side='right', padx=px(10))

header_frame.place(relx=0.022, rely=0.026, relwidth=0.909, relheight=0.065)

# === Main panels ===
board = DepartureBoard(root, PAGE_SURFACE)
board.place(relx=0.028, rely=0.100, relwidth=0.296, relheight=0.500)

bursdag = BirthdayPanel(root, YELLOW_SURFACE)
bursdag.place(relx=0.028, rely=0.610, relwidth=0.296, relheight=0.175)

weather = WeatherPanel(root, YELLOW_SURFACE)
weather.place(relx=0.028, rely=0.795, relwidth=0.296, relheight=0.190)

discord = DiscordPanel(root, YELLOW_SURFACE)
discord.place(relx=0.340, rely=0.100, relwidth=0.330, relheight=0.885)

orden = OrdenTable(root, ORDEN_SURFACE)
orden.place(relx=0.690, rely=0.100, relwidth=0.295, relheight=0.885)

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


def update_weather():
    weather.update_display()
    root.after(300000, update_weather)  # 5 min


# Start background fetch threads
fetch_thread = threading.Thread(target=fetch_loop, daemon=True)
fetch_thread.start()
weather_thread = threading.Thread(target=fetch_weather_loop, daemon=True)
weather_thread.start()

# Start update loops
update_time()
update_departures()
update_orden()
update_bursdager()
update_discord()
update_weather()

root.mainloop()