"""
Build the Ethiogen logo variants from the source artwork.

The source (tools/brand/logo-source.png) is a running figure and star in
blue/orange/green on an opaque white field. None of that palette belongs to
the theme, and the opaque field made the mark render as a white slab on dark
headers. This script recolours the three strokes into the brand ramp and knocks
the background out to transparency.

Two variants are produced, because one ramp cannot serve every header colour:

  ethiogen-logo.png           bright ramp, for DARK backgrounds (bg-slate-900)
  ethiogen-logo-light.png     deep ramp,   for LIGHT backgrounds (bg-white)
  ethiogen-logo-onbrand.png   knockout white, for BRAND-coloured surfaces
  favicon.png                 square + padded, cut from the dark variant

Contrast against each background (WCAG, computed with tools/brand/contrast):
  brand-500 #f97316   6.37:1 on slate-900   but only 2.80:1 on white
  brand-600 #ea580c   5.02:1 / 3.56:1      -- safe on both
  brand-700 #c2410c   3.45:1 / 5.18:1
  amber-400 #fbbf24  10.69:1               but only 1.67:1 on white
  amber-700 #b45309   3.56:1 / 5.02:1      -- safe on both

So the dark variant uses brand-500/600 + amber-400 for maximum pop, and the
light variant steps down to brand-700/600 + amber-700 so the mark keeps at
least 3:1 everywhere instead of washing out to a pale smudge on white.

Run:  .venv\\Scripts\\python.exe tools\\build_logo.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "brand", "logo-source.png")
OUT_DIR = os.path.join(ROOT, "static", "branding")

# Stroke colours sampled from the source artwork.
SRC_COLOURS = [(0x00, 0x50, 0xA0), (0xF0, 0x70, 0x00), (0x00, 0x90, 0x30)]

VARIANTS = {
    # name                     figure      swoosh      star/lower
    # Full colour: the artwork exactly as drawn (blue / orange / green). Only
    # the opaque white field is removed, so the mark sits on any theme surface
    # without a white slab. This is the brand mark; the ramps below are
    # single-hue treatments for surfaces where it would not read.
    "ethiogen-logo.png": SRC_COLOURS,
    "ethiogen-logo-light.png": [(0xC2, 0x41, 0x0C), (0xEA, 0x58, 0x0C), (0xB4, 0x53, 0x09)],
    "ethiogen-logo-mono.png": [(0xF9, 0x73, 0x16), (0xEA, 0x58, 0x0C), (0xFB, 0xBF, 0x24)],
    # Knockout white, for sitting on a brand-coloured surface (the mini app
    # header pill is an orange gradient). Alpha still comes from the source, so
    # the gaps between strokes stay transparent and the mark still reads.
    "ethiogen-logo-onbrand.png": [(0xFF, 0xFF, 0xFF), (0xFF, 0xFF, 0xFF), (0xFF, 0xF4, 0xE6)],
}

MAX_H = 512
PAD = 12
P = 6.0
WHITE = 255


def recolour(dst_colours):
    im = Image.open(SRC).convert("RGB")
    w, h = im.size
    src_px = im.load()

    out = Image.new("RGBA", (w, h))
    dst_px = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b = src_px[x, y]

            # alpha = distance from the white backdrop, so anti-aliased edge
            # pixels keep partial coverage instead of a hard jaggy cut
            alpha = WHITE - min(r, g, b)
            if alpha <= 2:
                dst_px[x, y] = (0, 0, 0, 0)
                continue

            f = WHITE / float(alpha)
            ur = max(0, min(WHITE, int(r * f)))
            ug = max(0, min(WHITE, int(g * f)))
            ub = max(0, min(WHITE, int(b * f)))

            # scale back up before measuring, or every edge pixel looks
            # equally close to all three source colours
            t = alpha / float(WHITE)
            mr = int(ur + (WHITE - ur) * (1 - t))
            mg = int(ug + (WHITE - ug) * (1 - t))
            mb = int(ub + (WHITE - ub) * (1 - t))

            weights = []
            for sc in SRC_COLOURS:
                d2 = (mr - sc[0]) ** 2 + (mg - sc[1]) ** 2 + (mb - sc[2]) ** 2
                weights.append(1.0 / (d2 ** (P / 2.0) + 1e-6))
            tot = sum(weights)

            nr = ng = nb = 0.0
            for wgt, dc in zip(weights, dst_colours):
                nr += dc[0] * wgt
                ng += dc[1] * wgt
                nb += dc[2] * wgt

            dst_px[x, y] = (int(nr / tot), int(ng / tot), int(nb / tot), alpha)

    return out


def crop_and_fit(img):
    bbox = img.getbbox()
    bbox = (max(0, bbox[0] - PAD), max(0, bbox[1] - PAD),
            min(img.width, bbox[2] + PAD), min(img.height, bbox[3] + PAD))
    img = img.crop(bbox)
    if img.height > MAX_H:
        s = MAX_H / img.height
        img = img.resize((max(1, int(img.width * s)), MAX_H), Image.LANCZOS)
    return img


def main():
    if not os.path.exists(SRC):
        raise SystemExit("missing %s" % SRC)

    dark = None
    for name, cols in VARIANTS.items():
        logo = crop_and_fit(recolour(cols))
        path = os.path.join(OUT_DIR, name)
        logo.save(path, "PNG", optimize=True)
        ramp = "  ".join("#%02x%02x%02x" % c for c in cols)
        print("  %-26s %6.1f KB  %-11s  %s"
              % (name, os.path.getsize(path) / 1024,
                 "%dx%d" % logo.size, ramp))
        if name == "ethiogen-logo.png":
            dark = logo

    # favicon: square and padded, so browsers do not crop the wide mark down
    # to something tiny and off-centre at 16px
    side = max(dark.size)
    fav = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    fav.alpha_composite(dark, ((side - dark.width) // 2, (side - dark.height) // 2))
    fav = fav.resize((256, 256), Image.LANCZOS)
    path = os.path.join(OUT_DIR, "favicon.png")
    fav.save(path, "PNG", optimize=True)
    print("  %-26s %6.1f KB  256x256" % ("favicon.png", os.path.getsize(path) / 1024))


if __name__ == "__main__":
    main()
