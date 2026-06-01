"""Birthday panel — reads bursdager.json and shows upcoming birthdays with countdown."""

import datetime
import json
import os

import tkinter as tk

from felles import (
    LOCAL_TZ, SCRIPT_DIR,
    WHITE, BIRTHDAY_TODAY,
    YELLOW_SURFACE, RoundedPanel, px, font,
)


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

    birthdays.sort(key=lambda b: b['days_until'])
    return birthdays[:4]


class BirthdayPanel:
    """Birthday panel — yellow surface with Pillow rounded corners (R1+R6).
    R4: reads from bursdager.json. R7: shows next upcoming. R8: centered. R9: countdown + red today."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        tk.Label(self.rf.inner, text="UKENS BURSDAGSBARN", font=font(14, 'xBold'),
                 bg=surface.bg, fg=surface.heading).pack(pady=(px(6), px(4)))

        self.row_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.row_frame.pack(fill='both', expand=True, padx=px(6))

        self.row_labels = []
        for _ in range(4):
            lbl = tk.Label(self.row_frame, text="", font=font(14, 'bold'),
                           bg=surface.bg, fg=WHITE, anchor='center')
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
                color = BIRTHDAY_TODAY if b['is_today'] else WHITE
                lbl.config(text=text, fg=color)
            else:
                lbl.config(text="")