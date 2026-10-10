#!/bin/bash
# Jednorazowo: venv z bibliotekami w katalogu skilla. Bezpieczne do ponownego uruchomienia.
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -x "$DIR/.venv/bin/python" ]; then
  python3 -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install -q --disable-pip-version-check svgelements shapely manifold3d numpy pillow vtracer
"$DIR/.venv/bin/python" -c "import svgelements, shapely, manifold3d, numpy, PIL, vtracer; print('venv OK')"
