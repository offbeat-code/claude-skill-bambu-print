#!/bin/bash
# Podgląd SVG jako PNG (headless Chrome, bo Quick Look ignoruje viewBox). Użycie: preview.sh plik.svg wyjscie.png
set -e
SVG="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; OUT="$2"
TMP="$(mktemp -d)"; printf '<html><body style="margin:0;background:#bbb"><img src="file://%s" style="width:1000px;display:block"></body></html>' "$SVG" > "$TMP/p.html"
H=$(python3 -c "import re,sys;t=open(sys.argv[1]).read(800);m=re.search(r'viewBox=\"[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)\"',t);print(int(1000*float(m.group(2))/float(m.group(1)))+4 if m else 1000)" "$SVG")
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --allow-file-access-from-files --screenshot="$OUT" --window-size=1000,$H "file://$TMP/p.html" >/dev/null 2>&1
rm -rf "$TMP"; echo "podgląd -> $OUT"
