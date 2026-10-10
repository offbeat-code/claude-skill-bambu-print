# bambu-print — skill dla Claude Code

Obrazek (PNG / JPG / WEBP / SVG) → kolorowy wydruk 3D na **Bambu Lab P2S z AMS**.
Wrzucasz grafikę do Claude Code, piszesz „wrzuć to do Bambu, 50 mm" — skill wektoryzuje obraz,
sprawdza, co może nie wyjść (i proponuje poprawki), buduje model z częścią na każdy kolor,
tnie go pod P2S i otwiera gotowy plik w Bambu Studio. Druk startujesz sam (Print plate → Send).

## Wymagania

- macOS (testowane na macOS 27, Apple Silicon)
- [Bambu Studio](https://github.com/bambulab/BambuStudio/releases) w `/Applications` (testowane 02.08.02.61)
- Google Chrome (podgląd SVG)
- Python 3 (systemowy wystarczy)
- Claude Code

## Instalacja

```bash
git clone https://github.com/offbeat-code/claude-skill-bambu-print.git ~/.claude/skills/bambu-print
~/.claude/skills/bambu-print/scripts/setup.sh   # opcjonalnie — skill zrobi to sam przy pierwszym użyciu
```

Uruchom nową sesję Claude Code — skill `bambu-print` pojawi się na liście i włączy się sam,
gdy poprosisz o wydruk obrazka.

Aktualizacja: `git -C ~/.claude/skills/bambu-print pull`

## Użycie

W Claude Code: przeciągnij obrazek do okna i napisz np. „wydrukuj to na Bambu, 60 mm szerokości".

Ręcznie, bez Claude:

```bash
PY=~/.claude/skills/bambu-print/.venv/bin/python
S=~/.claude/skills/bambu-print/scripts
$PY $S/raster2svg.py logo.png --out logo.svg          # PNG/JPG -> SVG (max 4 kolory)
$PY $S/svg2bambu.py logo.svg --width 50 --check       # co może nie wyjść + zalecane flagi
$PY $S/svg2bambu.py logo.svg --width 50 --open        # model + slicing + otwarcie w Bambu Studio
```

Najważniejsze opcje `svg2bambu.py`: `--width` (mm), `--outline 3 --outline-color '#FFFFFF'`
(obwódka łącząca osobne kształty), `--top 0.6` (grubsza warstwa kolorów — lepsze krycie, dłuższy druk),
`--max-colors`. Wyniki lądują w `~/Documents/BambuPrint/<nazwa>/`.

## Jak to drukuje

Baza 1.2 mm w kolorze o największej powierzchni pod całą sylwetką + 0.4 mm kolorów na wierzchu.
Zmiany filamentu są tylko w górnych warstwach, więc czas zależy głównie od liczby kolorów, nie od rozmiaru
(logo 50 mm, 3 kolory ≈ 17 min, ≈ 3.5 g).

## Ograniczenia

- Max 4 kolory (sloty AMS). Zdjęcia z cieniami/gradientami wychodzą jako uproszczony „plakat".
- Detale cieńsze niż 0.4 mm (szerokość linii dyszy) znikają — skill ostrzega i proponuje większy wymiar.
- Nie wysyła druku sam — plik otwiera się w Bambu Studio, start klikasz Ty.
- Tylko P2S z dyszą 0.4 mm i PLA (profile w `profiles-p2s/`).
