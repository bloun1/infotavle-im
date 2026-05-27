# InfoTavle IM

Digital infotavle for Charlottenlund VGS — viser sanntids bussavganger fra ATB/Entur og ordensvakt-oversikt.

## Oppsett

### Krav

- Python 3.9+
- Avhengigheter: `requests`, `xmltodict`, `Pillow`

```bash
pip install requests xmltodict Pillow
```

### Kjør

```bash
python infoboard_5.py
```

Appen starter i fullskjermmodus. Trykk **Escape** for å avslutte.

## Hvordan data hentes

### Bussavganger (ATB / Entur)

Data hentes fra **Entur API** som returnerer SIRI XML:

- **API**: `https://api.entur.io/realtime/v1/rest/et?datasetId=ATB`
- **Stopp**: `NSR:Quay:75404` (Charlottenlund vgs)
- **Oppdatering**: Hvert 60. sekund (bakgrunnstråd)
- **Metode**: Laster ned hele datasettet, filtrerer til kun Charlottenlund VGS og rutene til Tempe/Strindheim

Destinasjonen "Valøyvegen" vises som "Tempe" i displayet.

### Ordensvakt

Data leses fra **`orden.json`** — en statisk fil i samme mappe som skriptet.

- **Format**: JSON-objekt med ukenummer som nøkler
- **Oppdatering**: Hvert 5. minutt (automatisk re-les)
- **Nåværende uke**: Fremhevet i gult, tidligere uker i grått med gjennomstreking

Eksempel `orden.json`:
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

#### Kan ordensvakten oppdateres fra ekstern kilde?

Ikke per i dag — `orden.json` må redigeres manuelt. Mulige utvidelser:
- **Google Sheets** → eksport som JSON (via Apps Script)
- **Sanity CMS** → API-endepunkt som serverer JSON
- **Cronjobb** → hent fra eksternt regneark og overskriv `orden.json`

#### Følger den datoer?

Ja — `isocalendar()[1]` brukes for å finne gjeldende ukenummer og fremheve den riktige raden.

## Visuell profil

| Element | Farge | Hex |
|---------|-------|-----|
| Bakgrunn | PMS 2627 (dyp lilla) | `#3C1053` |
| Sekundær | Lilla kort | `#4A1366` |
| Overskrift | PMS 108 (gul) | `#FFD244` |
| Aksent | PMS 7473 (teal) | `#00816D` |
| Tekst | Hvit | `#FFFFFF` |
| Subtekst | Lavendel | `#B89CC8` |

### Font (midlertidig)

Arial brukes som substitutt for **Proxima Nova Alt / Widescreen XBold & Light**.
Font byttes når merkevarefontene er klare.

## Filstruktur

```
infotavle-im/
├── infoboard_5.py          ← Hovedapplikasjon
├── orden.json              ← Ordensvakt-data (manuelt redigert)
├── bg_pattern_real.png     ← Bakgrunnsmønster (IM-diamanter)
├── im_logo_small.png       ← IM-logo for header
├── infoboard.log           ← Logg (auto-generert)
└── Charlottenlund vgs Visuell Identitet/   ← Merkevare-retningslinjer
```

## Lisens

Intern bruk — Charlottenlund VGS / IM