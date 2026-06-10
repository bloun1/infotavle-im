"""Discord messages panel — fetches messages via bot API and displays them.

Changes vs. previous version:
  * fetch_discord now also extracts image attachments/embeds and reactions.
  * DiscordPanel renders a DYNAMIC number of cards (no longer a fixed 2).
  * Long messages are shown in full: wraplength is computed from the real card
    width (no hardcoded 260), so text wraps and the card grows instead of clipping.
  * Fit-to-panel: if the messages don't fit the panel height, every card is
    shrunk uniformly (scale `ds`) down to a legible floor; only if it still
    overflows at the floor are the oldest messages dropped.
  * Images (first attachment/embed image per message) and reactions
    (custom emoji as image, unicode emoji as text) are rendered per card.
"""

import datetime
import json
import os
import threading

import requests

import tkinter as tk

from PIL import Image, ImageTk

from felles import (
    LOCAL_TZ, SCRIPT_DIR, log,
    DISCORD_CARD, DISCORD_AUTHOR, DISCORD_TEXT, DISCORD_TIME,
    YELLOW_SURFACE, RoundedPanel, px, font, rounded_image,
    twemoji_url, get_remote_image, render_text_image,
    warm_emoji_cache, has_emoji, emoji_photo, split_emoji,
)

# R15: Discord connection status tracking
discord_status = "not_configured"  # "not_configured", "ok", or error string
discord_status_lock = threading.Lock()

# Image downloading/caching now lives in felles (get_remote_image), shared
# across panels. _get_image is kept as a thin alias so call sites are unchanged.
try:
    _RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # very old Pillow
    _RESAMPLE = Image.LANCZOS


def _get_image(url):
    """Return a cached PIL.Image (RGBA) for url (delegates to felles)."""
    return get_remote_image(url)


def _photo_from(im, max_w, bg_hex):
    """Scale a PIL image to max_w (keeping aspect), flatten onto bg, -> PhotoImage."""
    w, h = im.size
    if max_w and w > max_w:
        nh = max(1, int(h * max_w / w))
        im = im.resize((int(max_w), nh), _RESAMPLE)
    if im.mode == 'RGBA':
        base = Image.new('RGB', im.size, bg_hex)
        base.paste(im, mask=im.split()[-1])
        im = base
    elif im.mode != 'RGB':
        im = im.convert('RGB')
    return ImageTk.PhotoImage(im)


# Unicode emoji are rendered as Twemoji images (in felles) so they never fall
# back to Tkinter's text rendering, which shows empty tofu boxes for colour
# emoji. Custom server emoji already come as images from Discord's CDN.


def fetch_discord():
    """Fetch Discord messages via bot API using config.json. R15: track status."""
    global discord_status
    try:
        with open(os.path.join(SCRIPT_DIR, 'config.json'), 'r', encoding="UTF-8") as f:
            cfg = json.load(f)
        token = cfg.get('discord_bot_token')
        channel_id = cfg.get('discord_channel_id')
        # How many messages to FETCH as candidates. The panel decides how many
        # actually fit on screen, so fetch a few more than will likely show.
        max_msgs = cfg.get('discord_max_messages', 6)
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

            # --- images: first image attachment, else first embed image ---
            images = []
            for att in msg.get('attachments', []):
                ct = att.get('content_type', '') or ''
                if (ct.startswith('image/') or att.get('width')) and att.get('url'):
                    images.append(att['url'])
            for emb in msg.get('embeds', []):
                img = emb.get('image') or emb.get('thumbnail')
                if isinstance(img, dict) and img.get('url'):
                    images.append(img['url'])

            # --- reactions: emoji + count ---
            reactions = []
            for rc in msg.get('reactions', []):
                emo = rc.get('emoji', {}) or {}
                count = rc.get('count', 0)
                if emo.get('id'):  # custom server emoji -> image
                    ext = 'gif' if emo.get('animated') else 'png'
                    reactions.append({
                        'url': f"https://cdn.discordapp.com/emojis/{emo['id']}.{ext}",
                        'name': emo.get('name', ''),
                        'count': count,
                    })
                elif emo.get('name'):  # unicode emoji -> twemoji image (text fallback)
                    name = emo['name']
                    reactions.append({'text': name, 'url': twemoji_url(name), 'count': count})

            result.append({
                'author': author, 'content': content, 'time': time_str,
                'images': images, 'reactions': reactions,
            })

        # Warm the image cache on this (background) thread so the UI thread
        # doesn't block on network when it renders.
        for m in result:
            warm_emoji_cache(m['content'])          # emoji inside the message text
            warm_emoji_cache(m['author'])
            for u in m['images'][:1]:
                _get_image(u)
            for rc in m['reactions']:
                if rc.get('url'):
                    _get_image(rc['url'])

        shown = [m for m in result if m['content'] or m['images']]
        if fetched_raw > 0 and len(shown) < fetched_raw // 2:
            with discord_status_lock:
                discord_status = "no_content_intent"
            return shown
        with discord_status_lock:
            discord_status = "ok"
        return shown
    except Exception as e:
        with discord_status_lock:
            discord_status = f"Frakoblet — {e}"
        log(f"Discord fetch failed ({e})")
        return []


class DiscordPanel:
    """Discord messages panel — yellow surface with Pillow rounded corners (R1+R6)."""

    DS_MIN = 0.72  # legibility floor for the shrink-to-fit scale

    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        self._photos = []    # strong refs to PhotoImages (else GC blanks them)
        self._cards = []     # currently shown card canvases
        self._header_photos = []  # header emoji refs (never cleared)

        # Header: keep the bold Widescreen title font for the text, render the
        # emoji as inline images so they don't tofu on the Pi.
        head = tk.Frame(self.rf.inner, bg=surface.bg)
        head.pack(pady=(px(6), px(4)))
        self._emoji_row(head, "📢❗1IM-FELLESINFO", font(24, 'xBold'),
                        surface.heading, surface.bg, px(24),
                        store=self._header_photos)

        self.msg_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.msg_frame.pack(fill='both', expand=True, padx=px(6), pady=px(4))

        self.no_data_label = tk.Label(self.msg_frame, text="Ingen meldinger",
                                       font=font(14), bg=surface.bg, fg=surface.heading)

    # ---- helpers -----------------------------------------------------------

    def _emoji_row(self, parent, text, fnt, fg, bg, esz, store=None):
        """Pack a single horizontal line of mixed text + inline emoji images
        into parent. Text uses fnt (so titles keep the Widescreen look)."""
        if store is None:
            store = self._photos
        row = tk.Frame(parent, bg=bg)
        row.pack()
        for kind, seg in split_emoji(text):
            if kind == 'emoji':
                photo = emoji_photo(seg, esz, bg=bg)
                store.append(photo)
                tk.Label(row, image=photo, bg=bg).pack(side='left')
            elif seg:
                tk.Label(row, text=seg, font=fnt, bg=bg, fg=fg).pack(side='left')
        return row

    def _clear_cards(self):
        for c in self._cards:
            c.destroy()
        self._cards = []
        self._photos = []

    def _build_reactions(self, parent, reacts, ds, pad):
        row = tk.Frame(parent, bg=DISCORD_CARD)
        row.pack(fill='x', padx=pad, pady=(max(2, int(4 * ds)), 0))
        fsz = max(9, int(round(12 * ds)))
        esz = max(12, int(round(18 * ds)))
        for rc in reacts:
            if rc.get('url'):
                im = _get_image(rc['url'])
                if im is not None:
                    photo = _photo_from(im, esz, DISCORD_CARD)
                    self._photos.append(photo)
                    tk.Label(row, image=photo, bg=DISCORD_CARD).pack(side='left', padx=(0, 1))
                else:
                    fallback = rc.get('text') or (f":{rc.get('name', '')}:" if rc.get('name') else '·')
                    tk.Label(row, text=fallback, font=font(fsz),
                             bg=DISCORD_CARD, fg=DISCORD_TEXT).pack(side='left', padx=(0, 1))
            else:
                tk.Label(row, text=rc.get('text', '') or '·', font=font(fsz),
                         bg=DISCORD_CARD, fg=DISCORD_TEXT).pack(side='left', padx=(0, 1))
            tk.Label(row, text=str(rc.get('count', '')), font=font(fsz),
                     bg=DISCORD_CARD, fg=DISCORD_TIME).pack(
                side='left', padx=(0, max(4, int(8 * ds))))

    def _build_card(self, msg, width, ds):
        """Build one rounded card at scale `ds`; returns (canvas, height_px)."""
        def F(sz, w=None):
            s = max(8, int(round(sz * ds)))
            return font(s, w) if w else font(s)

        pad = max(2, int(px(10) * ds))
        text_w = max(20, width - 4 * pad)

        card = tk.Canvas(self.msg_frame, bg=self.surface.bg,
                         highlightthickness=0, width=width)
        inner = tk.Frame(card, bg=DISCORD_CARD)

        tk.Label(inner, text=msg.get('author', ''), font=F(14, 'bold'),
                 bg=DISCORD_CARD, fg=DISCORD_AUTHOR, anchor='w').pack(
            fill='x', padx=pad, pady=(pad, 0))

        content = msg.get('content', '')
        if content:
            if has_emoji(content):
                # Render text + inline emoji to one image so emoji never tofu.
                # Stays a Label -> winfo_reqheight() (the fit logic) is unchanged.
                body_px = px(max(8, int(round(13 * ds))))
                photo = render_text_image(
                    content, text_w, body_px, DISCORD_TEXT, bg=DISCORD_CARD,
                    align='left', cache_key=(content, text_w, body_px))
                self._photos.append(photo)
                tk.Label(inner, image=photo, bg=DISCORD_CARD, anchor='w').pack(
                    fill='x', padx=pad, pady=(max(1, int(2 * ds)), 0))
            else:
                tk.Label(inner, text=content, font=F(13), bg=DISCORD_CARD,
                         fg=DISCORD_TEXT, anchor='w', justify='left',
                         wraplength=text_w).pack(
                    fill='x', padx=pad, pady=(max(1, int(2 * ds)), 0))

        for url in msg.get('images', [])[:1]:
            im = _get_image(url)
            if im is not None:
                photo = _photo_from(im, text_w, DISCORD_CARD)
                self._photos.append(photo)
                tk.Label(inner, image=photo, bg=DISCORD_CARD).pack(
                    padx=pad, pady=(max(2, int(4 * ds)), 0))

        reacts = msg.get('reactions', [])
        if reacts:
            self._build_reactions(inner, reacts, ds, pad)

        tk.Label(inner, text=msg.get('time', ''), font=F(11), bg=DISCORD_CARD,
                 fg=DISCORD_TIME, anchor='e').pack(
            fill='x', padx=pad, pady=(max(1, int(2 * ds)), pad))

        # Measure the assembled inner frame, then draw the rounded background
        # at the matching height and place inner on top of it.
        card.update_idletasks()
        ih = inner.winfo_reqheight()
        h = ih + 2 * pad
        r = max(1, min(int(px(8) * ds), width // 2, h // 2))
        card.config(height=h, width=width)
        bg_photo = rounded_image(width, h, r, DISCORD_CARD)
        self._photos.append(bg_photo)
        card.create_image(0, 0, anchor='nw', image=bg_photo)
        card.create_window(pad, pad, anchor='nw', window=inner,
                           width=width - 2 * pad, height=ih)
        return card, h

    def _build_all(self, messages, width, ds):
        return [self._build_card(m, width, ds) for m in messages]

    def _render(self, messages):
        self._clear_cards()

        self.msg_frame.update_idletasks()
        avail_h = self.msg_frame.winfo_height()
        width = self.msg_frame.winfo_width()
        if width < 20 or avail_h < 20:
            # Layout not ready yet (panel not placed/sized) — try again shortly.
            self.msg_frame.after(60, lambda m=messages: self._render(m))
            return

        spacing = max(1, int(px(3)))

        # Pass 1 at full scale to learn the natural total height.
        built = self._build_all(messages, width, 1.0)
        total = sum(h for _, h in built) + spacing * max(0, len(built) - 1)

        # If it overflows, shrink uniformly toward a legible floor, then rebuild.
        if total > avail_h and total > 0:
            ds = max(self.DS_MIN, (avail_h / total) * 0.98)
            for c, _ in built:
                c.destroy()
            self._photos = []
            built = self._build_all(messages, width, ds)
            spacing = max(1, int(px(3) * ds))

        # Place top-down. Never clip a card: if the next one won't fit, stop
        # (show fewer). The first card is always shown even if huge.
        used = 0
        for idx, (c, h) in enumerate(built):
            if idx > 0 and used + spacing + h > avail_h:
                c.destroy()
                break
            pad_top = spacing if idx > 0 else 0
            c.pack(fill='x', pady=(pad_top, 0))
            self._cards.append(c)
            used += pad_top + h

    # ---- public API --------------------------------------------------------

    def place(self, **kwargs):
        self.rf.place(**kwargs)

    def update_display(self, messages=None):
        if messages is None:
            messages = []

        with discord_status_lock:
            status = discord_status

        def show_notice(text, fg):
            self._clear_cards()
            self.no_data_label.config(text=text, fg=fg)
            self.no_data_label.pack(pady=px(10))

        if status == "not_configured":
            show_notice("Sett opp Discord i config.json", '#EA560D')
            return
        elif status == "no_content_intent":
            show_notice("Discord tilkoblet, men ingen meldingstekst\n— skru på Message Content Intent", '#EA560D')
            return
        elif status.startswith("Discord feil") or status.startswith("Frakoblet"):
            show_notice(f"Discord frakoblet — {status}", '#EA560D')
            return

        if not messages:
            show_notice("Ingen meldinger", self.surface.heading)
            return

        self.no_data_label.pack_forget()
        self._render(messages)
