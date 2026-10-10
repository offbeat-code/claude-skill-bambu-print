---
name: bambu-print
description: Zamienia obrazek (PNG, JPG, WEBP albo SVG) w kolorowy wydruk 3D na Bambu Lab P2S z AMS — wektoryzacja, model 3D z częścią per kolor, slicing i otwarcie gotowego pliku w Bambu Studio. Używaj, gdy użytkownik wrzuca grafikę/logo/zdjęcie i chce to wydrukować, „wrzucić do Bambu", zrobić z tego brelok, toper, magnes, tabliczkę albo płaski kolorowy wydruk.
---

# Obrazek → kolorowy wydruk na Bambu P2S

Cel: użytkownik wrzuca plik i mówi „wrzuć do Bambu". Prowadzisz to do końca sam, pytając tylko o rzeczy z listy niżej.
Pliki wynikowe: `~/Documents/BambuPrint/<nazwa>/`. Skrypty: `scripts/` w tym skillu (`SKILL_DIR` = katalog tego pliku).

## 0. Środowisko (raz na komputer)

```bash
SKILL_DIR=~/.claude/skills/bambu-print
[ -x $SKILL_DIR/.venv/bin/python ] || $SKILL_DIR/scripts/setup.sh
PY=$SKILL_DIR/.venv/bin/python
```
Wymagane: macOS, Bambu Studio w `/Applications` (testowane 02.08.02.61), Google Chrome (podgląd SVG).

## 1. Wejście → SVG

- **SVG** → od razu krok 2. Jeśli zawiera `<text>`, gradienty albo obrazy osadzone — powiedz, że trzeba je zamienić na krzywe/płaskie kolory (albo wyrenderuj do PNG i idź ścieżką rastrową).
- **PNG/JPG/WEBP**:
  ```bash
  $PY $SKILL_DIR/scripts/raster2svg.py obraz.png --out ~/Documents/BambuPrint/<nazwa>/<nazwa>.svg
  $SKILL_DIR/scripts/preview.sh <svg> <katalog>/svg_preview.png
  ```
  Przeczytaj `svg_preview.png` (Read) i porównaj z oryginałem. Sprawdź: czy tło wycięte (bez białej obwódki dookoła), czy kolory te same, czy nic nie zginęło.
  - Za dużo/za mało kolorów → `--colors N` (1–4).
  - Obraz bez przezroczystości, a tło nie jest jednolite → `--keep-bg` (tło stanie się częścią wydruku) albo zasugeruj PNG z przezroczystością.
  - RMS > 35 / ostrzeżenie o gradientach → uprzedź: zdjęcia z cieniami wychodzą jak plakat w 2–4 kolorach. Najlepiej działają logo, clipart, grafiki z płaskimi kolorami.
- Otwórz SVG użytkownikowi w Chrome (`open -a "Google Chrome" plik.svg`) i poczekaj na „ok", zanim pójdziesz dalej.

## 2. Analiza — ZAWSZE przed budowaniem

Szerokość: jeśli użytkownik jej nie podał, przyjmij 50 mm i powiedz to (zmieni jednym słowem).
```bash
$PY $SKILL_DIR/scripts/svg2bambu.py plik.svg --width 50 --check
```
Wypisuje `PROBLEM:` + `NAPRAWA:` i `ZALECANE FLAGI:`. Wykrywa: osobne kawałki (niepołączone litery → obwódka łącząca), detale cieńsze niż 0.4 mm (→ większa szerokość), drobinki/szum (usuwane automatycznie), >4 kolory (scalane w najbliższe), tekst/gradienty/obrazki w SVG (→ render do PNG i ścieżka rastrowa), wymiar ponad stół.

- **Brak problemów** → od razu krok 3, bez pytania.
- **Są problemy** → JEDNA wiadomość: krótka lista „co może nie wyjść → co z tym zrobię" + jedno pytanie „poprawić tak?" (rekomendacja domyślnie tak). Przy obwódce zaproponuj kolor: jeden z kolorów projektu (nie zajmuje dodatkowego slotu) albo biały/czarny, jeśli jest wolny slot. Nie każ użytkownikowi niczego poprawiać ręcznie — naprawiasz flagami albo ścieżką rastrową.
- SVG z tekstem/gradientem/obrazkiem: `preview.sh plik.svg plik.png`, potem `raster2svg.py plik.png` (szare tło podglądu wytnie się samo) i wróć do kroku 1. Gradient wyjdzie jako 2–4 pasy kolorów — powiedz to użytkownikowi.

Obwódka (`--outline 4 --outline-color '#FFFFFF'`) wlicza się w szerokość, zamyka dziury w literach (O, A) i daje wygląd naklejki. Domyślny kolor obwódki = kolor bazy.

## 3. Budowanie → pocięty plik dla P2S

```bash
$PY $SKILL_DIR/scripts/svg2bambu.py plik.svg --width 50 [ZALECANE FLAGI] --open
```
Domyślnie: baza 1.2 mm w kolorze o największej powierzchni pod całą sylwetką + 0.4 mm (2 warstwy) kolorów na wierzchu. Opcje: `--top 0.6` (pewniejsze krycie jasnych kolorów, dłużej), `--base`, `--max-colors`, `--out`.

Skrypt wypisuje: kolory i mm², ostrzeżenia o detalach < 0.4 mm, gramy per filament, czas, liczbę zmian koloru, `preview.png` (render Bambu). Przeczytaj `preview.png`, a użytkownikowi podaj krótko: wymiar, czas, gramy, kolory → które filamenty załadować.

Na detale < 0.4 mm (ostrzeżenie > 5%): zaproponuj większą szerokość.

## 4. Druk (klika użytkownik)

`--open` otwiera plik w Bambu Studio. Powiedz użytkownikowi:
1. **Slice plate** (przetnie jeszcze raz z presetem jego drukarki — pewniejsze niż nasz plik z CLI).
2. **Print plate** → drukarka P2S, płyta PEI, sprawdzić, czy każdy kolor trafił na właściwy slot AMS (A1..A4).
3. Płyta pusta → **Send**.

Nie startujesz druku sam. Bezpośrednia wysyłka (LAN + Developer Mode, FTPS 990 + MQTT `project_file`) jest możliwa, ale nieprzetestowana na P2S i wymaga zgody użytkownika na tryb LAN-only.

## Czas i koszt — z pomiarów (2026-10-10)

- Czas zjadają zmiany koloru, nie rozmiar: logo 40/50/60 mm przy 0.8 mm kolorów = 24/25/26 min; przy 0.4 mm kolorów 50 mm = 17 min. Każda warstwa z kolorami to zmiany filamentu + czyszczenie dyszy.
- Logo Wilsad 50×14 mm, 3 kolory, `--top 0.4`: 17 min, 3.45 g — wydrukowane, użytkownik zadowolony.
- Biały na 2 warstwach może lekko prześwitywać kolorem bazy → `--top 0.6` jeśli to ważne.

## Problemy znane

- **Bambu Studio w kółko prosi o „network plug-in"** / pole Printer puste: wtyczka się nie wczytuje (na macOS 27 wtyczka 02.07 zwracała `BIND_OPCODE_DO_BIND unknown bind type 0`). Rozwiązanie: aktualizacja Bambu Studio (DMG z github.com/bambulab/BambuStudio/releases, najnowsze nie-prerelease). Test wczytania: `arch -arm64 /usr/bin/python3 -I -c "import ctypes; ctypes.CDLL('$HOME/Library/Application Support/BambuStudio/plugins/libbambu_networking.dylib')"`.
- CLI Bambu Studio nie przyjmuje SVG (exit 250) — dlatego własna konwersja. Import SVG w GUI scala kolory w jedną bryłę.
- Slicing CLI wymaga **spłaszczonych** profili (`profiles-p2s/`, bez `inherits`) i `curr_bed_type=Textured PEI Plate` w process.json. `--outputdir` musi być absolutny.
- Po aktualizacji Bambu Studio profile mogą się zestarzeć — jeśli slicing się wywala, spłaszcz na nowo z `/Applications/BambuStudio.app/Contents/Resources/profiles/BBL` (machine `Bambu Lab P2S 0.4 nozzle`, process `0.20mm Standard @BBL P2S`, filament `Bambu PLA Basic @BBL P2S`).
- Toper na tort: tylko dekoracja na patyczku, bez bezpośredniego kontaktu z jedzeniem.
