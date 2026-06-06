"""Weather panel — fetches forecast from Yr.no API and displays current conditions."""

import datetime
import json
import os
import threading
import time

import requests
import tkinter as tk

from felles import (
    LOCAL_TZ, SCRIPT_DIR, log,
    WHITE, TEAL, HEADING_YELLOW,
    YELLOW_SURFACE, RoundedPanel, px, font,
)

# Yr.no Locationforecast API (free, no key required)
YR_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
YR_HEADERS = {'User-Agent': 'infotavle-im/1.0 charlottenlund-vgs'}
YR_LAT = 63.4145  # Charlottenlund VGS, Trondheim
YR_LON = 10.4654

# Cache
_weather_data = None
_last_fetch_time = None
REFRESH_WEATHER_SEC = 600  # 10 min
_is_online = False


def _weather_icon(symbol_code):
    """Map Yr.no symbol_code to a unicode weather character."""
    mapping = {
        'clearsky': '☀️', 'clearsky_day': '☀️', 'clearsky_night': '🌙',
        'fair': '🌤️', 'fair_day': '🌤️', 'fair_night': '🌙',
        'partlycloudy': '⛅', 'partlycloudy_day': '⛅', 'partlycloudy_night': '☁️',
        'cloudy': '☁️',
        'rainshowers': '🌦️', 'rainshowers_day': '🌦️', 'rainshowers_night': '🌧️',
        'rainshowersandthunder': '⛈️',
        'sleetshowers': '🌨️', 'sleetshowers_day': '🌨️', 'sleetshowers_night': '🌨️',
        'snowshowers': '❄️', 'snowshowers_day': '❄️', 'snowshowers_night': '❄️',
        'rain': '🌧️', 'heavyrain': '🌧️', 'heavyrainandthunder': '⛈️',
        'sleet': '🌨️', 'heavysleet': '🌨️',
        'snow': '❄️', 'heavysnow': '❄️',
        'fog': '🌫️', 'mist': '🌫️',
        'wind': '💨',
    }
    if symbol_code in mapping:
        return mapping[symbol_code]
    prefix = symbol_code.split('_')[0]
    for key in mapping:
        if key.startswith(prefix):
            return mapping[key]
    return '🌡️'


def _wind_beaufort(ms):
    """Convert m/s to Beaufort scale description (Norwegian)."""
    if ms < 0.3: return 'stille'
    if ms < 1.6: return 'flau vind'
    if ms < 3.4: return 'svak vind'
    if ms < 5.5: return 'lett bris'
    if ms < 8.0: return 'laber bris'
    if ms < 10.8: return 'frisk bris'
    if ms < 13.9: return 'sterk bris'
    if ms < 17.2: return 'sterk vind'
    if ms < 20.8: return 'storm'
    return 'sterk storm'


def fetch_weather():
    """Fetch weather from Yr.no. Returns dict or None."""
    global _weather_data, _last_fetch_time, _is_online
    try:
        params = {'lat': YR_LAT, 'lon': YR_LON}
        resp = requests.get(YR_URL, params=params, headers=YR_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        _is_online = True
        _last_fetch_time = datetime.datetime.now(LOCAL_TZ)
        _weather_data = data
        log("Weather fetched successfully")
        return data
    except Exception as e:
        _is_online = False
        log(f"Weather fetch error: {e}")
        return _weather_data


def fetch_weather_loop():
    """Background thread that fetches weather periodically."""
    while True:
        fetch_weather()
        time.sleep(REFRESH_WEATHER_SEC)


def get_current_weather():
    """Parse current weather from cached Yr.no data. Returns dict or None."""
    if not _weather_data:
        return None
    try:
        timeseries = _weather_data['properties']['timeseries']
        now = datetime.datetime.now(LOCAL_TZ)

        best = None
        best_diff = float('inf')
        for entry in timeseries:
            t = datetime.datetime.fromisoformat(entry['time']).astimezone(LOCAL_TZ)
            diff = abs((t - now).total_seconds())
            if diff < best_diff:
                best = entry
                best_diff = diff

        if not best:
            return None

        instant = best['data']['instant']['details']
        temp = instant.get('air_temperature', '--')
        wind_speed = instant.get('wind_speed', 0)
        humidity = instant.get('relative_humidity', '--')

        symbol_code = 'clearsky'
        if best['data'].get('next_1_hours'):
            symbol_code = best['data']['next_1_hours']['summary'].get('symbol_code', 'clearsky')

        forecast_items = []
        for entry in timeseries:
            t = datetime.datetime.fromisoformat(entry['time']).astimezone(LOCAL_TZ)
            if t <= now:
                continue
            if len(forecast_items) >= 4:
                break
            sym = (entry['data'].get('next_1_hours') or entry['data'].get('next_6_hours') or {}).get('summary', {}).get('symbol_code', 'clearsky')
            t_detail = entry['data']['instant']['details']
            forecast_items.append({
                'time': t.strftime('%H:%M'),
                'temp': t_detail.get('air_temperature', '--'),
                'icon': _weather_icon(sym),
            })

        return {
            'temp': f"{temp:.0f}°" if isinstance(temp, (int, float)) else temp,
            'icon': _weather_icon(symbol_code),
            'wind': f"{wind_speed:.0f} m/s ({_wind_beaufort(wind_speed)})",
            'humidity': f"{humidity}%",
            'forecast': forecast_items,
        }
    except Exception as e:
        log(f"Weather parse error: {e}")
        return None


class WeatherPanel:
    """Weather panel — yellow surface showing current weather + mini forecast."""
    def __init__(self, parent, surface):
        self.surface = surface
        self.rf = RoundedPanel(parent, surface)

        # Title
        tk.Label(self.rf.inner, text="VÆR", font=font(14, 'xBold'),
                 bg=surface.bg, fg=surface.heading).pack(pady=(px(6), px(2)))

        # Current weather row
        self.current_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.current_frame.pack(fill='x', padx=px(6))

        self.icon_label = tk.Label(self.current_frame, text="🌡️", font=font(28, 'normal'),
                                   bg=surface.bg, fg=WHITE)
        self.icon_label.pack(side='left', padx=(px(4), px(2)))

        self.temp_label = tk.Label(self.current_frame, text="--°", font=font(28, 'xBold'),
                                   bg=surface.bg, fg=WHITE)
        self.temp_label.pack(side='left', padx=px(2))

        # Details column
        self.details_frame = tk.Frame(self.current_frame, bg=surface.bg)
        self.details_frame.pack(side='left', fill='y', padx=px(8))

        self.wind_label = tk.Label(self.details_frame, text="", font=font(11, 'normal'),
                                    bg=surface.bg, fg=WHITE)
        self.wind_label.pack(anchor='w')

        self.humidity_label = tk.Label(self.details_frame, text="", font=font(11, 'normal'),
                                       bg=surface.bg, fg=WHITE)
        self.humidity_label.pack(anchor='w')

        # Forecast rows
        self.forecast_frame = tk.Frame(self.rf.inner, bg=surface.bg)
        self.forecast_frame.pack(fill='x', padx=px(6), pady=(px(4), px(2)))

        self.forecast_labels = []
        for _ in range(4):
            row = tk.Frame(self.forecast_frame, bg=surface.bg)
            row.pack(fill='x', pady=px(1))
            time_lbl = tk.Label(row, text="", font=font(11, 'normal'), bg=surface.bg, fg=WHITE, width=5, anchor='w')
            time_lbl.pack(side='left')
            icon_lbl = tk.Label(row, text="", font=font(11, 'normal'), bg=surface.bg, fg=WHITE, width=3)
            icon_lbl.pack(side='left')
            temp_lbl = tk.Label(row, text="", font=font(11, 'bold'), bg=surface.bg, fg=WHITE, anchor='e')
            temp_lbl.pack(side='right')
            self.forecast_labels.append((time_lbl, icon_lbl, temp_lbl))

    def place(self, **kwargs):
        self.rf.place(**kwargs)

    def update_display(self):
        weather = get_current_weather()
        if not weather:
            return

        self.icon_label.config(text=weather['icon'])
        self.temp_label.config(text=weather['temp'])
        self.wind_label.config(text=f"💨 {weather['wind']}")
        self.humidity_label.config(text=f"💧 {weather['humidity']}")

        for i, (time_lbl, icon_lbl, temp_lbl) in enumerate(self.forecast_labels):
            if i < len(weather['forecast']):
                fc = weather['forecast'][i]
                time_lbl.config(text=fc['time'])
                icon_lbl.config(text=fc['icon'])
                temp_lbl.config(text=f"{fc['temp']}°" if isinstance(fc['temp'], (int, float)) else fc['temp'])
            else:
                time_lbl.config(text="")
                icon_lbl.config(text="")
                temp_lbl.config(text="")