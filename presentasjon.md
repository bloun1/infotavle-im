# InfoTavle IM — Presentasjon

Klassepresentasjon | 3 personer | ~5 min

---

## Slide 1: Hei, vi er IM

Vi er tre IM-elever på Charlottenlund, og vi har bygd en digital infotavle som henger nede i skolegangen.

Den viser fire ting:

- Når bussen går fra Charlottenlund vgs
- Hvem som har ordensvakt denne uka
- Hvem som har bursdag
- Hva folk skriver på Discord

Før dette hang det papirark overalt. Nå er alt samlet på én skjerm, og den oppdaterer seg selv.

---

## Slide 2: Slik starta vi

22. mai begynte vi. Alt var i én fil — `infoboard_5.py`, 798 linjer.

Buss, ordensvakt, alt bare lå der i én stor klump. Skulle du fikse bussen, kunne du ødelegge ordensvakten. Det var litt som å rote i en skuff der alt er blandet sammen.

Det fungerte, men det var ikke bra.

---

## Slide 3: Så vi delte det opp

I stedet for én fil, lagde vi én fil per funksjon:

- `felles.py` — farger, fonter, ting alle deler
- `buss.py` — bare buss
- `ordens.py` — bare ordensvakt
- `bursdag.py` — bare bursdager
- `discord.py` — bare Discord
- `main.py` — setter alt sammen

Nå kan du jobbe med bursdag uten å røre bussen. Det er mye enklere å finne feil, og enklere for noen andre å skjønne hva koden gjør.

---

## Slide 4: Hvor dataene kommer fra

Bussavgangene henter vi fra Entur — altså ATBs eget API. Det snakker XML, ikke JSON, så det var litt omstendelig å parse. Vi oppdaterer hvert minutt i en bakgrunnstråd, for ellers fryser skjermen mens den venter på svar.

Ordensvakten og bursdagene ligger i JSON-filer som vi oppdaterer manuelt. Discord henter vi fra Discord sin bot-API.

Alt oppdaterer seg selv. Ingen trenger å trykke på noe.

---

## Slide 5: Hvordan den ser ut

Vi brukte skolens egne farger — den lilla bakgrunnen og gule overskriften dere kjenner fra profilmanualen. IM-diamant-mønsteret er bakgrunnsbilde.

Vi fant en font som heter Widescreen som passer bra. Hvis den ikke finnes på maskinen, faller vi tilbake til Arial.

Skjermen skalerer alt automatisk etter hvor stor monitoren er, så det ser bra ut enten det er en 22-tommer eller 55-tommer.

---

## Slide 6: Det som var vanskelig

Tre ting var tricky:

**Først** — Entur API-et returnerer XML. Vi var vant til JSON, så vi måtte lære oss XML-parsing fra bunnen.

**Andre** — tkinter er ikke laget for fullscreen. Skjermen freeze når vi lastet bakgrunnsbildet. Løsningen var å cache bildet i riktig størrelse før det vises.

**Tredje** — å dele opp 798 linjer i 6 filer uten at noe brakk. Det krevde at vi planla først, ikke bare begynte å klippe.

---

## Slide 7: Det vi vil gjøre videre

- Koble ordensvakten mot Google Sheets slik at lærerne kan oppdatere selv
- Kanskje vær-data fra Yr

---

## Slide 8: Oppsummering

Vi starta 22. mai med én stor fil. Nå har vi seks filer, fire datakilder, og en skjerm som oppdaterer seg selv.

Det viktigste vi lærte: hold koden din i biter. Én funksjon per fil. Da blir det enklere å bygge, enklere å fikse, og enklere å bygge videre.

Takk! Har dere spørsmål?

---

### Hvem sier hva

- **Person 1:** Slide 1–3 — hvem vi er, hvordan vi starta, oppdelingen
- **Person 2:** Slide 4–5 — dataene, hvordan den ser ut
- **Person 3:** Slide 6–8 — utfordringer, videre planer, oppsummering

Ca 1.5 min per person. Vis infotavlen live hvis skjermen står på!