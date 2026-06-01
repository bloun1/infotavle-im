"""Discord messages panel — fetches messages via bot API and displays them."""

import datetime
import json
import os
import threading

import requests

import tkinter as tk

from felles import (
    LOCAL_TZ, SCRIPT_DIR, log,
    DISCORD_CARD, DISCORD_AUTHOR, DISCORD_TEXT, DISCORD_TIME,
    YELLOW_SURFACE, RoundedPanel, px, font, rounded_image,
)

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
        if fetched_raw > 0 and len(shown) < fetched_raw // 2:
            with discord_status_lock:
                discord_status = "no_content_intent"
            return shown
        with discord_status_lock:
            discord_status = "ok"
        return shown[:max_msgs]
    except Exception as e:
        with discord_status_lock:
            discord_status = f"Frakoblet — {e}"
        log(f"Discord fetch failed ({e})")
        return []


class DiscordPanel:
    """Discord messages panel — yellow surface with Pillow rounded corners (R1+R6)."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        tk.Label(self.rf.inner, text="📢❗1IM-FELLESINFO", font=font(24, 'xBold'),
                 bg=surface.bg, fg=surface.heading).pack(pady=(px(6), px(4)))

        self.msg_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.msg_frame.pack(fill='both', expand=True, padx=px(6), pady=px(4))

        self.msg_widgets = []
        for _ in range(2):
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
            card._inner = card_inner
            card._photo = None
            card.bind('<Configure>', lambda e, c=card, ci=card_inner: self._configure_card(c, ci))
            self.msg_widgets.append((card, author_lbl, content_lbl, time_lbl))

        self.no_data_label = tk.Label(self.msg_frame, text="Ingen meldinger",
                                       font=font(14), bg=surface.bg, fg=surface.heading)

    def _configure_card(self, card, card_inner):
        w = card.winfo_width()
        if w < 4:
            return
        card_inner.update_idletasks()
        ih = card_inner.winfo_reqheight()
        pad = max(1, min(px(8), w // 2))
        h = ih + 2 * pad
        r = max(1, min(px(8), w // 2, h // 2))
        card.config(height=h)
        card.delete('all')
        photo = rounded_image(w, h, r, DISCORD_CARD)
        card._photo = photo
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

        if status == "not_configured":
            self.no_data_label.config(text="Sett opp Discord i config.json", fg='#EA560D')
            self.no_data_label.pack(pady=px(10))
            for card, _, _, _ in self.msg_widgets:
                card.pack_forget()
            return
        elif status == "no_content_intent":
            self.no_data_label.config(text="Discord tilkoblet, men ingen meldingstekst\n— skru på Message Content Intent", fg='#EA560D')
            self.no_data_label.pack(pady=px(10))
            for card, _, _, _ in self.msg_widgets:
                card.pack_forget()
            return
        elif status.startswith("Discord feil") or status.startswith("Frakoblet"):
            self.no_data_label.config(text=f"Discord frakoblet — {status}", fg='#EA560D')
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