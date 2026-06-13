# InfoTavle IM

Digital infotavle for Charlottenlund VGS — sanntids bussavganger, ordensvakt, bursdager og Discord-meldinger.

Bygget av IM-elever for IM-elever. 🎓

## Hva den viser

| Panel | Datakilde | Oppdatering |
|-------|-----------|-------------|
| 🚌 Bussavganger | ATB/Entur API (SIRI XML) | Hvert 60. sekund |
| 👮 Ordensvakt | `orden.json` (lokalt) | Hvert 5. minutt |
| 🎂 Bursdager | `bursdager.json` | Hvert 5. minutt |
| 💬 Discord | Discord Bot REST API | Hvert 60. sekund |

## Modulstruktur

Hver funksjon har sin egen fil. Slik henger det sammen:

```
felles.py ← alt deler dette (farger, fonter, UI-hjelpere)
   │
   ├── buss.py      ← henter data, bygger buss-tabell
   ├── ordens.py    ← leser JSON, bygger ordensvakt-tabell
   ├── bursdag.py   ← leser bursdager, bygger bursdagspanel
   └── discord.py   ← henter meldinger, bygger Discord-panel
       │
   main.py ← kobler alt sammen, setter opp skjerm og oppdateringsloop
```

### Hva hver fil gjør

| Fil | Linjer | Ansvar |
|-----|--------|--------|
| `felles.py` | 132 | Farger (palette), fonter, skalering (`px()`, `font()`), tidssone, `RoundedPanel`-widget, logging |
| `buss.py` | 258 | Entur API-kall, XML-parsing, `DepartureBoard`-widget, bakgrunnstråd |
| `ordens.py` | 86 | Leser `orden.json`, `OrdenTable`-widget med ukefremheving |
| `bursdag.py` | 117 | Leser `bursdager.json`, `BirthdayPanel`-widget med dato-sortering |
| `discord.py` | 187 | Discord Bot REST API, `DiscordPanel`-widget med meldingsvisning |
| `main.py` | 179 | Fullskjerm-setup, header, panel-layout, oppdateringsloop, bakgrunnstråd |

## Oppsett

### Krav

- Python 3.9+
- Avhengigheter: `requests`, `xmltodict`, `Pillow`

```bash
pip install requests xmltodict Pillow
```

### Kjør

```bash
python main.py
```

Appen starter i fullskjermmodus. Trykk **Escape** for å avslutte.

### Discord (valgfritt)

Rediger `config.json` og legg inn bot-token og kanal-ID:

```json
{
  "discord_bot_token": "DIN_BOT_TOKEN",
  "discord_channel_id": "KANAL_ID"
}
```

Uten dette viser Discord-panelet en oppsettsmelding i stedet for meldinger.

## Slik bygger du din egen infotavle

Dette prosjektet er bygget modul for modul. Slik kan du gjøre det samme:

### 1. Start med `felles.py` — fundamentet

Dette er det eneste alle andre filer avhenger av. Legg her:

- **Fargepalett** — konstanter som `PAGE_BG`, `HEADING_YELLOW`, etc.
- **Surface-klasser** — definerer utseende per panel (bakgrunn, overskrift-farge, radius)
- **Skalering** — `px()` og `font()` fungerer mot en skaleringsfaktor `S` (satt i main.py)
- **UI-hjelpere** — `RoundedPanel` (avrundede panel med Pillow-rendering)
- **Logging** — `log()` som skriver til `infoboard.log`

```python
# Skalering: referanse-skjerm = 1280px bred
S = screen_w / 1280.0

def px(ref_px):
    """Skaler PSD-referanse-piksler."""
    return max(1, round(ref_px * S))

def font(ref_px, weight='normal'):
    """Returner Tkinter font-tuple skalert med S."""
    ...
```

### 2. Lag `buss.py` — sanntidsdata

- Hent data fra et API (Entur returnerer SIRI XML)
- Parse XML til en liste med avganger (linje, destinasjon, tid)
- Bygg en tkinter-widget (`DepartureBoard`) som viser tabellen
- Kjør API-kall i en **bakgrunnstråd** — ellers fryser skjermen

### 3. Lag `ordens.py` — lokal data

- Les fra en JSON-fil (`orden.json`) med ukenummer som nøkler
- Finn gjeldende uke med `isocalendar()[1]`
- Fremhev denne uka i annen farge, skjul gamle uker
- Bygg `OrdenTable`-widget med grid-layout

### 4. Lag `bursdag.py` — bursdagspanel

- Les fra `bursdager.json` (navn → dato)
- Sorter etter dato, vis kun kommende bursdager
- Bygg `BirthdayPanel`-widget med navn, ukedag og dato

### 5. Lag `discord.py` — ekstern meldingstjeneste

- Bruk Discord Bot REST API for å hente meldinger
- Strip markdown-formatting fra meldingene
- Bygg `DiscordPanel`-widget med forfatter, innhold og tidspunkt

### 6. Koble alt i `main.py`

- Opprett tkinter-vindu i fullskjerm
- Sett skaleringsfaktor `felles.S = screen_w / 1280.0`
- Last bakgrunnsmønster og logo
- Plasser paneler med `place()` (nøyaktig posisjonering)
- Start oppdateringsloop med `root.after()` for hvert panel
- Start bakgrunnstråd for API-kall

## Datakilder

### Bussavganger (Entur)

- **API**: `https://api.entur.io/realtime/v1/rest/et?datasetId=ATB`
- **Format**: SIRI XML
- **Stopp**: `NSR:Quay:75404` (Charlottenlund vgs)
- **Oppdatering**: Bakgrunnstråd hvert 60. sekund
- Destinasjonen "Valøyvegen" vises som "Tempe"

### Ordensvakt (`orden.json`)

```json
{
  "Uke21": {
    "dato": "19.05 - 23.05",
    "1IM1": "Ola N",
    "1IM2": "Kari M",
    "stoler": "Per A",
    "vasking": "Liv B"
  }
}
```

Redigeres manuelt. Kan utvides med Google Sheets-sync eller Sanity CMS.

### Bursdager (`bursdager.json`)

```json
{
  "Ola Nordmann": "15.03.2005",
  "Kari Hansen": "22.10.2006"
}
```

Støtter formatene `DD.MM.YYYY` og `DD.MM`.

### Discord (`config.json`)

Krever en Discord Bot med tilgang til kanalen. Sett opp bot på [discord.com/developers](https://discord.com/developers).

## Visuell profil

Appen bruker skolens visuelle profil fra `Charlottenlund vgs Visuell Identitet/`.

| Element | Farge | Hex |
|---------|-------|-----|
| Bakgrunn | Dyp lilla | `#3D1053` |
| Gul panel | `PANEL_YELLOW` | `#E9B647` |
| Lilla panel | `PANEL_PURPLE` | `#4A1366` |
| Overskrift | `HEADING_YELLOW` | `#FCC745` |
| Aksent/Teal | `TEAL` | `#00816D` |
| Tekst | Hvit | `#FFFFFF` |

### Font

Bruker **Widescreen**-fontfamilien med auto-fallback til **Arial**:

- **XBold**: Overskrifter, titler
- **Light**: Brødtekst, klokke

Fontene skaleres automatisk etter skjermbredde via `felles.S`.

### Bakgrunnsmønster

Bruker `bg_pattern_real.png` (IM-diamanter). Auto-caches i riktig oppløsning ved første kjøring.

## Filstruktur

```
infotavle-im-refactor/
├── main.py                ← Start her — kobler alt sammen
├── felles.py              ← Delt: farger, fonter, UI-hjelpere, logging
├── buss.py                ← Bussavganger: Entur API + DepartureBoard
├── ordens.py              ← Ordensvakt: JSON + OrdenTable
├── bursdag.py             ← Bursdager: JSON + BirthdayPanel
├── discord.py             ← Discord: Bot API + DiscordPanel
├── orden.json             ← Ordensvakt-data (manuelt redigert)
├── bursdager.json         ← Bursdagsdata
├── config.json            ← Discord bot-konfigurasjon
├── bg_pattern_real.png    ← Bakgrunnsmønster (IM-diamanter)
├── im-logo-blo.png        ← IM-logo
├── infoboard.log           ← Logg (auto-generert)
├── Bursdag.xlsx            ← Bursdags-kildeark
├── Charlottenlund vgs Visuell Identitet/  ← Skolens profilmanual
└── IM-Visuell Identitet/                  ← IM-spesifikk profil
```

## Tidslinje

| Dato | Hva |
|------|-----|
| 13. mai | Første commit — monolitisk `infoboard_5.py` med tkinter, bakgrunnstråd, buss + ordensvakt |
| 24. mai | Visuelt løft — IM-farger, IM-mønster bakgrunn |
| 26. mai | Tidssone-fix, feilhåndling, IM-branding |
| 27. mai | Discord-panel, bursdagspanel, Widescreen font-system |
| juni | Refaktorert til moduler — én fil per funksjon |

## Planlagte utvidelser

- [ ] Google Sheets → `orden.json` automatisk sync
- [ ] Sanity CMS API for ordensvakt
- [ ] Raspberry Pi 24/7 deployment med auto-start
- [ ] Flere holdeplasser
- [ ] Yr vær-integrasjon

## Lisens

Intern bruk — Charlottenlund VGS / IM