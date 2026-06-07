"""Orden (duty schedule) table — reads orden.json and displays current/future weeks."""

import datetime
import json
import os
import re

import tkinter as tk

from felles import (
    LOCAL_TZ, SCRIPT_DIR,
    WHITE, GOLD_HILITE,
    ORDEN_SURFACE, RoundedPanel, px, font,
)

REFRESH_ORDEN_MIN = 5


def fetch_orden():
    with open(os.path.join(SCRIPT_DIR, 'orden.json'), 'r', encoding="UTF-8") as f:
        return json.load(f)


class OrdenTable:
    """Orden table — purple surface with Pillow rounded corners (R1+R6).
    R3: Centered. Bug 4: Hides past weeks."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        # Title — centered
        tk.Label(self.rf.inner, text="ORDENSELEV", font=font(24, 'xBold'),
                 bg=surface.bg, fg=surface.heading).pack(pady=(px(4), px(2)))

        self.center_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.center_frame.pack(fill='both', expand=True, padx=px(4))

        self.grid_frame = tk.Frame(self.center_frame, bg=surface.bg)
        self.grid_frame.pack(anchor='center')

        headers = ['UKE', 'DATO', '1IM1', '1IM2', 'VASK']
        for col, header in enumerate(headers):
            tk.Label(self.grid_frame, text=header, font=font(14, 'xBold'),
                     bg=surface.bg, fg=WHITE).grid(row=0, column=col, padx=px(3), pady=px(2), sticky='w')

        self.cells = []
        for row in range(1, 27):
            row_cells = []
            for col in range(5):
                lbl = tk.Label(self.grid_frame, text="", font=font(11),
                               bg=surface.bg, fg=WHITE)
                lbl.grid(row=row, column=col, padx=px(3), pady=px(1), sticky='w')
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