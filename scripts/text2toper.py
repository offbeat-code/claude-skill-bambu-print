"""Napis -> PNG -> SVG gotowy dla svg2bambu.py --typ toper.

Linie wyśrodkowane, ciasno jedna pod drugą (jak w toperach użytkownika), żeby wydłużenia liter się zazębiały;
resztę odłączonych kawałków łączy potem svg2bambu --bridge.
"""
import argparse, glob, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_font(name):
    if os.path.exists(name):
        return name
    key = name.lower().replace(' ', '')
    cands = glob.glob(os.path.join(SKILL, 'fonts', '*.[ot]t[fc]')) + glob.glob('/System/Library/Fonts/Supplemental/*') + glob.glob(os.path.expanduser('~/Library/Fonts/*'))
    hit = [p for p in cands if key in os.path.basename(p).lower().replace(' ', '').replace('-', '')]
    if not hit:
        sys.exit(f'nie znam fontu "{name}" — dostępne w skillu: {[os.path.basename(p) for p in glob.glob(os.path.join(SKILL, "fonts", "*.[ot]t[fc]"))]}')
    return hit[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('text', help='linie oddzielone "|", np. "Chrzest|Święty|Ola"')
    ap.add_argument('--font', default='AlexBrush', help='nazwa (szuka w fonts/ skilla, systemie) albo ścieżka .ttf/.otf')
    ap.add_argument('--spacing', type=float, default=0.72, help='odstęp linii jako ułamek rozmiaru fontu (mniej = ciaśniej)')
    ap.add_argument('--out', required=True, help='ścieżka .svg')
    a = ap.parse_args()

    font = ImageFont.truetype(find_font(a.font), 400)
    lines = [l.strip() for l in a.text.split('|') if l.strip()]
    d0 = ImageDraw.Draw(Image.new('L', (1, 1)))
    W = int(max(d0.textlength(l, font=font) for l in lines)) + 400
    im = Image.new('RGBA', (W, int(400 * (a.spacing * (len(lines) - 1) + 1.6)) + 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text(((W - d.textlength(l, font=font)) / 2, 100 + i * 400 * a.spacing), l, font=font, fill=(25, 25, 25, 255))
    im = im.crop(im.getbbox())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    png = os.path.splitext(a.out)[0] + '.png'
    im.save(png)
    print(f'font: {os.path.basename(find_font(a.font))}, linie: {lines}, PNG -> {png}')
    py = os.path.join(SKILL, '.venv', 'bin', 'python')
    subprocess.run([py, os.path.join(SKILL, 'scripts', 'raster2svg.py'), png, '--colors', '1', '--out', a.out], check=True)


if __name__ == '__main__':
    main()
