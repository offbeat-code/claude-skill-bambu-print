"""PNG/JPG/WEBP -> SVG z płaskimi kolorami (max 4) gotowe do svg2bambu.py.

Tło: przezroczystość z kanału alfa, a gdy jej brak — kolor z ramki obrazka wycinany flood-fillem od brzegów.
Kolory: k-means; --colors N wymusza liczbę, inaczej dobierane automatycznie (najmniejsze k z RMS < progu).
"""
import argparse, os, re, subprocess, sys
from collections import Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import vtracer


def kmeans(px, k, iters=30):
    rng = np.random.default_rng(0)
    c = [px[rng.integers(len(px))]]
    for _ in range(1, k):  # k-means++
        d = np.min(((px[:, None] - np.array(c)[None]) ** 2).sum(-1), 1)
        c.append(px[rng.choice(len(px), p=d / d.sum())])
    c = np.array(c, float)
    for _ in range(iters):
        lab = ((px[:, None] - c[None]) ** 2).sum(-1).argmin(1)
        c = np.array([px[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
    rms = np.sqrt(((px - c[lab]) ** 2).sum(-1).mean())
    return c, rms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--out', required=True, help='ścieżka wyjściowego .svg')
    ap.add_argument('--colors', type=int, default=0, help='liczba kolorów (1-4); 0 = auto')
    ap.add_argument('--keep-bg', action='store_true', help='nie wycinaj tła (obraz bez alfy)')
    ap.add_argument('--bg-tol', type=int, default=40, help='tolerancja koloru tła przy wycinaniu')
    a = ap.parse_args()

    img = Image.open(a.image).convert('RGBA')
    scale = max(1, min(4, 3000 // max(img.size)))
    img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    arr = np.array(img).astype(int)
    alpha = arr[..., 3] > 128

    if alpha.all() and not a.keep_bg:
        rgb = Image.fromarray(arr[..., :3].astype(np.uint8))
        marker = (255, 0, 255)
        w, h = rgb.size
        for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
            if rgb.getpixel(xy) != marker:
                ImageDraw.floodfill(rgb, xy, marker, thresh=a.bg_tol)
        alpha = (np.array(rgb) != marker).any(-1)
        print(f'tło wycięte: {100 * (1 - alpha.mean()):.0f}% pikseli')

    px = arr[..., :3][alpha].astype(float)
    if len(px) == 0:
        sys.exit('po wycięciu tła nic nie zostało — użyj --keep-bg albo mniejszego --bg-tol')
    sample = px[np.random.default_rng(1).choice(len(px), min(40000, len(px)), replace=False)]
    if a.colors:
        cents, rms = kmeans(sample, a.colors)
    else:
        for k in range(1, 5):  # max 4 = sloty AMS
            cents, rms = kmeans(sample, k)
            if rms < 22:
                break
    k = len(cents)
    print(f'kolory: {k}, średni błąd koloru RMS={rms:.1f}' + ('  (UWAGA: obraz ma więcej kolorów niż 4 sloty AMS — uproszczony do 4)' if rms >= 22 and k == 4 else ''))
    if rms > 35:
        print('UWAGA: duży błąd koloru — obraz ma gradienty/cienie, wydruk będzie mocno uproszczony')

    lab = ((arr[..., :3][..., None, :] - cents[None, None]) ** 2).sum(-1).argmin(-1)
    # kolor, który jest tylko cienką obwódką (antyaliasing/JPG na granicy dwóch kolorów), wywalamy
    while len(cents) > 1:
        cores = []
        for i in range(len(cents)):
            m = Image.fromarray(((lab == i) & alpha).astype(np.uint8) * 255)
            area = (np.array(m) > 0).sum()
            core = (np.array(m.filter(ImageFilter.MinFilter(4 * scale + 1))) > 0).sum()
            cores.append(core / max(area, 1))
        worst = int(np.argmin(cores))
        if cores[worst] >= 0.25:
            break
        print(f'pomijam kolor #{"".join(f"{int(round(v)):02X}" for v in cents[worst])} — tylko cienka krawędź')
        cents = np.delete(cents, worst, 0)
        lab = ((arr[..., :3][..., None, :] - cents[None, None]) ** 2).sum(-1).argmin(-1)
    k = len(cents)
    # obwódka-resztka tła: cienkie fragmenty koloru stykające się z tłem -> przezroczyste
    size = 2 * (scale + scale // 2) + 1
    near_bg = np.array(Image.fromarray((~alpha).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(size))) > 0
    for i in range(k):
        m = Image.fromarray(((lab == i) & alpha).astype(np.uint8) * 255)
        opened = np.array(m.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))) > 0
        halo = (np.array(m) > 0) & ~opened & near_bg
        if halo.any():
            alpha = alpha & ~halo
    out = np.zeros_like(arr)
    out[..., :3] = np.round(cents).astype(int)[lab]
    out[..., 3] = np.where(alpha, 255, 0)
    tmp = a.out + '.quant.png'
    Image.fromarray(out.astype(np.uint8)).save(tmp)
    vtracer.convert_image_to_svg_py(tmp, a.out, colormode='color', hierarchical='cutout', mode='spline',
                                    filter_speckle=16, color_precision=8, layer_difference=8, corner_threshold=60,
                                    length_threshold=4.0, splice_threshold=45, path_precision=2)
    os.remove(tmp)
    svg = open(a.out).read()
    pal = np.round(cents).astype(int)
    snap = lambda m: 'fill="#%02X%02X%02X"' % tuple(pal[((pal - [int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)]) ** 2).sum(1).argmin()])
    svg = re.sub(r'fill="#([0-9A-Fa-f]{6})"', snap, svg)  # vtracer uśrednia kolory — przyciągamy do palety
    m = re.search(r'width="(\d+)" height="(\d+)"', svg)
    svg = svg.replace(m.group(0), m.group(0) + f' viewBox="0 0 {m.group(1)} {m.group(2)}"', 1)
    open(a.out, 'w').write(svg)
    fills = Counter(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg))
    for col, n in fills.most_common():
        share = (np.round(cents).astype(int)[lab][alpha] == [int(col[i:i + 2], 16) for i in (1, 3, 5)]).all(-1).mean()
        print(f'  {col.upper()}: {n} ścieżek, {100 * share:.0f}% powierzchni')
    print(f'SVG -> {a.out}')


if __name__ == '__main__':
    main()
