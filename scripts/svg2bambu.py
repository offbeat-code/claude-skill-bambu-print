"""SVG (płaskie kolory) -> 3MF z częścią per kolor -> slicing Bambu Studio CLI (P2S) -> .gcode.3mf.

Wariant "baza + kolor na wierzchu": cała sylwetka w kolorze bazowym (największa powierzchnia)
do wysokości --base, nad nią każdy kolor do --base + --top. Zmiany filamentu tylko w górnych warstwach.
"""
import argparse, json, os, re, subprocess, sys, zipfile
import numpy as np
from svgelements import SVG, Shape, Path, Color, Text
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union
from shapely import make_valid, affinity
import manifold3d as m3

BS = next(iter(sorted(__import__('glob').glob('/Applications/Bambu*Studio*.app/Contents/MacOS/BambuStudio'))), None)
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BED_CENTER = 128.0  # P2S: stół 256x256
LAYER = 0.2

# Presety z wydruków użytkownika (historia Bambu, 2026-10, 3 toppery) —
# przodem do płyty (lustro), grubość ~2 mm (z wagi), nóżka 4-4.5 mm x 73-99 mm ze zwężonym czubkiem.
DEFAULTS = dict(width=80.0, base=1.2, top=0.4, face='up', outline=0.0, leg=0.0, hole=0.0, thicken=0.0)
PRESETS = {
    'toper': dict(width=120.0, base=1.6, top=0.4, face='down', leg=90.0, thicken=0.3),
    'brelok': dict(width=40.0, base=2.4, top=0.6, face='up', outline=1.5, hole=4.0),
}


def svg_regions(path):
    svg = SVG.parse(path, reify=True)
    regions = {}
    for el in svg.elements():
        if isinstance(el, Text) or not isinstance(el, Shape) or el.fill is None or el.fill.value is None or el.fill.alpha == 0:
            continue
        p = Path(el)
        p.reify()
        g = None
        for sp in p.as_subpaths():
            sp = Path(sp)
            if len(sp) == 0:
                continue
            n = min(2000, max(16, int(sp.length(error=1e-3) / 2)))
            pts = [(q.x, q.y) for q in (sp.point(t) for t in np.linspace(0, 1, n)) if q is not None]
            if len(pts) < 3:
                continue
            poly = make_valid(Polygon(pts))
            g = poly if g is None else g.symmetric_difference(poly)
        if g is None or g.is_empty:
            continue
        key = Color(el.fill).hex[:7].upper()
        for k in list(regions):  # paint order: wyższy kształt zakrywa niższy
            if k != key:
                regions[k] = regions[k].difference(g)
        regions[key] = g if key not in regions else regions[key].union(g)
    return {k: v for k, v in regions.items() if not v.is_empty and v.area > 1e-6}


def rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)


def merge_colors(regions, max_colors, near=24.0):
    """Scala najbardziej podobne kolory (mniejszy w większy): zawsze prawie identyczne (antyaliasing), potem aż zostanie max_colors."""
    regions = dict(regions)
    while len(regions) > 1:
        keys = list(regions)
        pairs = [(np.linalg.norm(rgb(x) - rgb(y)), x, y) for i, x in enumerate(keys) for y in keys[i + 1:]]
        d, x, y = min(pairs)
        if len(regions) <= max_colors and d > near:
            break
        small, target = sorted((x, y), key=lambda k: regions[k].area)
        print(f'scalam {small} -> {target} (odległość koloru {d:.0f})')
        regions[target] = regions[target].union(regions.pop(small))
    return regions


def to_cross_section(g, scale, h):
    contours = []
    for pg in (g.geoms if hasattr(g, 'geoms') else [g]):
        if pg.geom_type != 'Polygon' or pg.area * scale * scale < 0.05:
            continue
        for ring in [pg.exterior, *pg.interiors]:
            c = np.array(ring.coords[:-1]) * scale
            c[:, 1] = h - c[:, 1]  # SVG y w dół -> 3D y w górę
            contours.append(c)
    return m3.CrossSection(contours, m3.FillRule.EvenOdd)


def mesh_xml(man, oid, dx, dy):
    m = man.to_mesh()
    v, t = m.vert_properties[:, :3], m.tri_verts
    vs = ''.join(f'<vertex x="{x + dx:.4f}" y="{y + dy:.4f}" z="{z:.4f}"/>' for x, y, z in v)
    ts = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in t)
    return f'<object id="{oid}" type="model"><mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>\n'


def write_3mf(parts, out, dx, dy):
    n = len(parts) + 1
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n<resources>\n')
    model += ''.join(mesh_xml(man, i + 1, dx, dy) for i, (_, man) in enumerate(parts))
    model += f'<object id="{n}" type="model"><components>' + ''.join(
        f'<component objectid="{i + 1}"/>' for i in range(len(parts))) + '</components></object>\n'
    model += f'</resources>\n<build><item objectid="{n}"/></build>\n</model>\n'
    ms = f'<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <object id="{n}">\n    <metadata key="name" value="{os.path.basename(out)}"/>\n    <metadata key="extruder" value="1"/>\n'
    for i, (col, _) in enumerate(parts):
        ms += (f'    <part id="{i + 1}" subtype="normal_part">\n      <metadata key="name" value="kolor_{col}"/>\n'
               f'      <metadata key="extruder" value="{i + 1}"/>\n    </part>\n')
    ms += '  </object>\n</config>\n'
    ct = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('3D/3dmodel.model', model)
        z.writestr('Metadata/model_settings.config', ms)


def pieces(g):
    return [p for p in (g.geoms if hasattr(g, 'geoms') else [g]) if p.geom_type == 'Polygon']


def thin_share(g):
    return (g.area - g.buffer(-0.2).buffer(0.2).area) / g.area if g.area else 0  # węższe niż linia 0.4 mm


def to_mm(regions, width):
    u = unary_union(list(regions.values()))
    minx, miny, maxx, _ = u.bounds
    s = width / (maxx - minx)
    return {k: affinity.scale(affinity.translate(g, -minx, -miny), s, s, origin=(0, 0)) for k, g in regions.items()}


def thicken(mm, t):
    """Pogrubia każdą kreskę o t mm; nakładki oddaje mniejszym kolorom (detale na wierzchu)."""
    out, claimed = {}, Polygon()
    for k in sorted(mm, key=lambda k: mm[k].area):
        g = mm[k].buffer(t / 2, join_style=1).difference(claimed)
        out[k], claimed = g, claimed.union(g)
    return out


def add_leg(union, length, width=4.5, tip=4.0, overlap=5.0):
    """Nóżka topera pod sylwetką (współrzędne SVG: y w dół). Szuka pionu przy środku, który trafia w kształt."""
    minx, miny, maxx, maxy = union.bounds
    cx0 = (minx + maxx) / 2
    for off in [0] + [s * d for d in np.arange(1, (maxx - minx) * 0.3, 1.0) for s in (1, -1)]:
        cx = cx0 + off
        hit = union.intersection(Polygon([(cx - width / 2, miny - 1), (cx + width / 2, miny - 1), (cx + width / 2, maxy + 1), (cx - width / 2, maxy + 1)]))
        if hit.area > width * overlap * 0.8:
            break
    y0 = hit.bounds[3]  # najniższy punkt kształtu w tym pionie
    y1 = y0 + length
    w = width / 2
    return Polygon([(cx - w, y0 - overlap), (cx + w, y0 - overlap), (cx + w, y1 - tip), (cx + 0.5, y1), (cx - 0.5, y1), (cx - w, y1 - tip)])


def bridges(union, width):
    """Mostki: każdy kawałek odłączony od największego łączy najkrótszym odcinkiem szer. width. Zwraca geometrię mostków."""
    main, rest, added = None, sorted(pieces(union), key=lambda p: -p.area), []
    main, rest = rest[0], rest[1:]
    while rest:
        d, i, (p1, p2) = min((p.distance(main), i, nearest_points(p, main)) for i, p in enumerate(rest))
        p = rest.pop(i)
        if d > 1e-6:
            # wejście 0.6 mm w oba kształty, żeby mostek na pewno się zrósł
            v = np.array([p2.x - p1.x, p2.y - p1.y]) / d
            b = LineString([(p1.x - v[0] * 0.6, p1.y - v[1] * 0.6), (p2.x + v[0] * 0.6, p2.y + v[1] * 0.6)]).buffer(width / 2, cap_style=1)
            added.append(b)
            main = main.union(b)
        main = main.union(p)
    return unary_union(added) if added else Polygon()


def add_hole(union, d):
    """Ucho breloka na górze sylwetki: (ucho, otwór)."""
    minx, miny, maxx, _ = union.bounds
    cx = (minx + maxx) / 2
    col = union.intersection(Polygon([(cx - 1, miny - 1), (cx + 1, miny - 1), (cx + 1, miny + 50), (cx - 1, miny + 50)]))
    top = col.bounds[1] if not col.is_empty else miny
    r = d / 2 + 2.2
    c = Point(cx, top - d / 2 + 0.6)
    return c.buffer(r, 64), c.buffer(d / 2, 64)


def dome(g, height, h_svg, z0):
    """Wypukłość 3D: warstwy co 0.2 mm z rosnącym wcięciem (profil ćwiartki koła, promień = wysokość)."""
    n = max(1, round(height / LAYER))
    r, man = height, None
    for i in range(n):
        zt = (i + 1) * LAYER
        inset = r - np.sqrt(max(r * r - (zt - (height - r)) ** 2, 0)) if zt > height - r else 0
        gi = g.buffer(-inset, join_style=1) if inset else g
        if gi.is_empty:
            break
        layer = to_cross_section(gi, 1, h_svg).extrude(LAYER).translate((0, 0, z0 + i * LAYER))
        man = layer if man is None else man + layer
    return man


def analyze(svg_text, regions, a):
    """Lista (problem, naprawa) + rekomendowane flagi. Nic nie zmienia."""
    issues, rec = [], {}
    for tag, what in (('<text', 'tekst (<text>)'), ('Gradient', 'gradienty'), ('<image', 'osadzony obrazek'), ('<filter', 'filtry/cienie')):
        if tag in svg_text:
            issues.append((f'SVG zawiera {what} — tego nie zamienię wprost na bryły',
                           'wyrenderować SVG do PNG i przejść ścieżką rastrową (raster2svg.py)'))
    mm = to_mm(regions, a.width - a.thicken)
    if a.thicken:
        mm = thicken(mm, a.thicken)
    u = unary_union(list(mm.values()))
    _, _, w, h = u.bounds
    h += a.leg
    n = len(pieces(u))
    if n > 1 and a.leg and not a.outline and not a.bridge:
        issues.append((f'{n} osobnych kawałków (słowa, kropki, akcenty) — odpadną od topera',
                       'mostki 1.2 mm do najbliższej litery (litery zostają cienkie, bez obwódki)'))
        rec['bridge'] = 1.2
    elif n > 1 and not a.outline and not a.bridge:
        need = next((o for o in (1, 1.5, 2, 3, 4, 5, 6, 8) if len(pieces(u.buffer(o, join_style=1))) == 1), None)
        if need:
            issues.append((f'{n} osobnych kawałków (np. niepołączone litery) — wydrukują się luzem',
                           f'obwódka {need} mm dookoła łącząca wszystko w jeden kawałek'))
            rec['outline'] = need
        else:
            issues.append((f'{n} osobnych kawałków, za daleko od siebie na obwódkę', 'tabliczka pod spodem albo druk osobno'))
    for k, g in mm.items():
        t = thin_share(g)
        if t > 0.05:
            bigger = next((f for f in (1.25, 1.5, 2, 3) if thin_share(affinity.scale(g, f, f)) <= 0.05 and a.width * f <= 250), None)
            issues.append((f'{k}: {100 * t:.0f}% detali cieńszych niż 0.4 mm — znikną albo będą postrzępione',
                           f'większy wydruk: szerokość {a.width * bigger:.0f} mm' if bigger else 'uprościć grafikę (pogrubić linie)'))
            if bigger:
                rec['width'] = max(rec.get('width', 0), round(a.width * bigger))
        tiny = [p for p in pieces(g) if p.area < a.min_island]
        if tiny:
            issues.append((f'{k}: {len(tiny)} drobinek < {a.min_island} mm2 (kropki/szum) — mogą się nie wydrukować',
                           'usuwam je automatycznie'))
    if max(w, h) > 250:
        issues.append((f'wymiar {w:.0f} x {h:.0f} mm nie mieści się na stole 256 mm', 'mniejsza szerokość'))
    return issues, rec, (w, h, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('svg')
    ap.add_argument('--typ', choices=sorted(PRESETS), help='preset: toper (lustro, nóżka, 120 mm), brelok (40 mm, ucho, obwódka)')
    ap.add_argument('--width', type=float, help='szerokość w mm (bez nóżki)')
    ap.add_argument('--base', type=float, help='grubość bazy w mm')
    ap.add_argument('--top', type=float, help='grubość warstwy kolorów w mm (0.4 = 2 warstwy)')
    ap.add_argument('--face', choices=['up', 'down'], help='down = przód na płycie (lustro, faktura płyty, ostre krawędzie kolorów)')
    ap.add_argument('--relief', type=float, default=0, help='efekt 3D: kolory inne niż baza wystają o tyle mm (tylko --face up)')
    ap.add_argument('--dome', action='store_true', help='zaokrąglone (wypukłe) krawędzie wystających kolorów')
    ap.add_argument('--iron', action='store_true', help='prasowanie wierzchniej warstwy (gładszy, błyszczący wierzch)')
    ap.add_argument('--leg', type=float, help='nóżka topera, długość w mm (0 = brak)')
    ap.add_argument('--hole', type=float, help='otwór na kółko breloka, średnica w mm (0 = brak)')
    ap.add_argument('--max-colors', type=int, default=4, help='sloty AMS; nadmiarowe kolory scalane w najbliższe')
    ap.add_argument('--outline', type=float, help='obwódka w mm dookoła całości (łączy osobne kawałki)')
    ap.add_argument('--thicken', type=float, help='pogrubienie każdej kreski o tyle mm (cienkie skrypty — wytrzymałość)')
    ap.add_argument('--bridge', type=float, default=0, help='mostki tej szerokości (mm) do odłączonych kawałków — kropki, akcenty, słowa; litery zostają cienkie')
    ap.add_argument('--outline-color', default='base', help='kolor obwódki: HEX (#FFFFFF) albo "base" = kolor bazy')
    ap.add_argument('--min-island', type=float, default=0.5, help='usuń drobinki mniejsze niż tyle mm2')
    ap.add_argument('--check', action='store_true', help='tylko analiza problemów, bez modelu i slicingu')
    ap.add_argument('--profiles', default=os.path.join(SKILL, 'profiles-p2s'), help='spłaszczone profile (machine.json, process.json, fil_template.json)')
    ap.add_argument('--out', help='katalog wyjściowy (domyślnie ~/Documents/BambuPrint/<nazwa>)')
    ap.add_argument('--open', action='store_true', help='otwórz wynik w Bambu Studio')
    a = ap.parse_args()
    for k, v in {**DEFAULTS, **PRESETS.get(a.typ, {})}.items():
        if getattr(a, k) is None:
            setattr(a, k, v)
    if a.relief and a.face == 'down':
        sys.exit('--relief działa tylko z --face up (przód na płycie jest płaski)')
    print(f'ustawienia: typ={a.typ or "-"} szer={a.width:g} baza={a.base:g} kolory={a.top:g} przód={a.face}'
          f' relief={a.relief:g}{" kopuła" if a.dome else ""} nóżka={a.leg:g} otwór={a.hole:g} obwódka={a.outline:g} pogrubienie={a.thicken:g}{" prasowanie" if a.iron else ""}')

    svg_text = open(a.svg, errors='ignore').read()
    regions = merge_colors(svg_regions(a.svg), a.max_colors)
    if a.check:
        issues, rec, (w, h, n) = analyze(svg_text, regions, a)
        print(f'kolory: {len(regions)} {list(regions)}; {w:.0f} x {h:.0f} mm; kawałków: {n}')
        for prob, fix in issues:
            print(f'PROBLEM: {prob}\n  NAPRAWA: {fix}')
        if not issues:
            print('OK — brak problemów')
        flags = ' '.join(f'--{k} {v}' for k, v in rec.items())
        print(f'ZALECANE FLAGI: {flags or "(brak)"}')
        return
    if '<text' in svg_text:
        sys.exit('SVG zawiera <text> — zamień tekst na krzywe albo wyrenderuj do PNG')
    if not BS:
        sys.exit('Nie znaleziono Bambu Studio w /Applications')
    name = os.path.splitext(os.path.basename(a.svg))[0]
    a.out = os.path.abspath(a.out or os.path.expanduser(f'~/Documents/BambuPrint/{name}'))

    mm = to_mm(regions, a.width - 2 * a.outline - a.thicken)  # obwódka i pogrubienie wliczają się w zadaną szerokość
    for k in mm:  # drobinki
        mm[k] = unary_union([p for p in pieces(mm[k]) if p.area >= a.min_island] or [Polygon()])
    if a.thicken:
        mm = thicken(mm, a.thicken)
    mm = {k: g for k, g in mm.items() if not g.is_empty}
    union = unary_union(list(mm.values()))
    base_col = max(mm, key=lambda k: mm[k].area)
    if a.bridge and len(pieces(union)) > 1:
        br = bridges(union, a.bridge)
        print(f'mostki: {len(pieces(br))} x {a.bridge:g} mm')
        mm[base_col] = mm[base_col].union(br.difference(union))
        union = union.union(br)
    if a.outline:
        sil = union.buffer(a.outline, join_style=1)
        oc = base_col if a.outline_color == 'base' else a.outline_color.upper()
        mm[oc] = sil.difference(union).union(mm.get(oc, Polygon()))
        if len(mm) > a.max_colors:
            sys.exit(f'kolor obwódki {oc} to {len(mm)}. kolor > {a.max_colors} slotów AMS — wybierz jeden z istniejących: {list(mm)}')
        union, base_col = sil, oc
    if a.leg:
        leg = add_leg(union, a.leg)
        mm[base_col] = mm[base_col].union(leg.difference(union))
        union = union.union(leg)
    if a.hole:
        tab, hole = add_hole(union, a.hole)
        mm[base_col] = mm[base_col].union(tab.difference(union))
        union = union.union(tab).difference(hole)
        mm = {k: g.difference(hole) for k, g in mm.items()}
    if a.face == 'down':  # przód leży na płycie -> lustro, żeby po odwróceniu czytało się normalnie
        cx = (union.bounds[0] + union.bounds[2]) / 2
        mm = {k: affinity.scale(g, -1, 1, origin=(cx, 0)) for k, g in mm.items()}
        union = affinity.scale(union, -1, 1, origin=(cx, 0))
    minx, miny, maxx, maxy = union.bounds
    mm = {k: affinity.translate(g, -minx, -miny) for k, g in mm.items()}
    union = affinity.translate(union, -minx, -miny)
    W, h = maxx - minx, maxy - miny

    parts = []
    for col, g in sorted(mm.items(), key=lambda kv: kv[0] != base_col):
        z_col, z_base = (0, a.top) if a.face == 'down' else (a.base, 0)
        if col != base_col and a.relief:
            hr = a.top + a.relief
            top = dome(g, hr, h, a.base) if a.dome else to_cross_section(g, 1, h).extrude(hr).translate((0, 0, a.base))
        else:
            top = to_cross_section(g, 1, h).extrude(a.top).translate((0, 0, z_col))
        man = to_cross_section(union, 1, h).extrude(a.base).translate((0, 0, z_base)) + top if col == base_col else top
        parts.append((col, man))
        t = thin_share(g)
        print(f'{col}: {g.area:.0f} mm2' + (' (baza)' if col == base_col else '')
              + (f', UWAGA {100 * t:.0f}% cieńsze niż 0.4 mm' if t > 0.05 else ''))
    print(f'kawałków: {len(pieces(union))}')
    if a.leg and len(pieces(union)) > 1:
        print(f'UWAGA: toper z {len(pieces(union))} osobnych kawałków — nie trzymające się nóżki odpadną (połącz litery w projekcie albo --outline)')
    a.width = W

    os.makedirs(a.out, exist_ok=True)
    in3mf = os.path.join(a.out, name + '.3mf')
    write_3mf(parts, in3mf, BED_CENTER - a.width / 2, BED_CENTER - h / 2)

    tpl = json.load(open(os.path.join(a.profiles, 'fil_template.json')))
    fils = []
    for i, (col, _) in enumerate(parts):
        tpl['filament_colour'] = [col]
        f = os.path.join(a.out, f'fil{i + 1}.json')
        json.dump(tpl, open(f, 'w'), indent=1)
        fils.append(f)
    process = os.path.join(a.profiles, 'process.json')
    if a.iron:
        p = json.load(open(process))
        p['ironing_type'] = 'top'
        process = os.path.join(a.out, 'process.json')
        json.dump(p, open(process, 'w'), indent=1)
    cmd = [BS, '--slice', '0', '--arrange', '0',
           '--load-settings', f"{os.path.join(a.profiles, 'machine.json')};{process}",
           '--load-filaments', ';'.join(fils), '--outputdir', a.out, '--export-3mf', name + '.gcode.3mf', in3mf]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    out = os.path.join(a.out, name + '.gcode.3mf')
    if r.returncode != 0 or not os.path.exists(out):
        sys.exit(f'slicing nieudany (exit {r.returncode}):\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
    info = zipfile.ZipFile(out).read('Metadata/slice_info.config').decode()
    pred = int(re.search(r'key="prediction" value="(\d+)"', info).group(1))
    weight = re.search(r'key="weight" value="([\d.]+)"', info).group(1)
    z = zipfile.ZipFile(out)
    gcode = z.read('Metadata/plate_1.gcode').decode(errors='ignore')
    changes = len(re.findall(r'^M620 S[0-3](?!\d)', gcode, re.M))
    open(os.path.join(a.out, 'preview.png'), 'wb').write(z.read('Metadata/plate_1.png'))
    for m in re.finditer(r'<filament id="(\d+)"[^>]*color="([^"]+)"[^>]*used_g="([^"]+)"', info):
        print(f'  filament {m.group(1)}: {m.group(2)} {m.group(3)} g')
    print(f'{a.width:.0f} x {h:.0f} mm, {weight} g, {pred // 3600}h{pred % 3600 // 60:02d}m, zmian koloru: {changes}')
    print(f'plik -> {out}\npodgląd -> {os.path.join(a.out, "preview.png")}')
    if a.open:
        subprocess.run(['open', '-a', os.path.dirname(os.path.dirname(os.path.dirname(BS))), out])


if __name__ == '__main__':
    main()
