"""Generate the animated profile banners (assets/banner-dark.svg, assets/banner-light.svg).

Same model as the header of https://sazio.github.io: OFF and ON ganglion-cell mosaics with
elliptical difference-of-Gaussians receptive fields watch a dark disc that drifts and loom-scales.
GitHub READMEs cannot run JavaScript, so one loop is simulated here and baked into SMIL
animations; the spike raster scrolls by translating a pre-drawn strip.

    python scripts/make_banner.py
"""
import math
import random
from pathlib import Path

W, H = 1200, 320
PERIOD = 20.0          # seconds per loop
DT = 0.05              # simulation step
KEY_EVERY = 5          # one keyframe every KEY_EVERY steps (0.25 s)
RASTER_TOP, RASTER_H = 262, 40
N_ROWS = 16

THEMES = {
    "dark": dict(paper="#0d0e12", off="#9d86ff", on="#4cc38a", ink="#ecebe6", ink2="#b4b5bb",
                 ink3="#7c7f88", stim="#000000", ring="#575a66"),
    "light": dict(paper="#f3f2ee", off="#5b3fd1", on="#1d8a59", ink="#16171b", ink2="#4a4d55",
                  ink3="#7f828a", stim="#17181c", ring="none"),
}


def lattice(rng, spacing, kind, ox, oy):
    cells, dy = [], spacing * math.sqrt(3) / 2
    r, y = 0, oy - dy
    while y < H + spacing:
        x = ox - spacing + (spacing / 2 if r % 2 else 0)
        while x < W + spacing:
            s = spacing * 0.42
            th = -0.45 + rng.gauss(0, 0.35)
            cells.append(dict(kind=kind, x=x + rng.gauss(0, spacing * 0.08), y=y + rng.gauss(0, spacing * 0.08),
                              sx=s * (1 + rng.gauss(0, 0.1)), sy=s * (0.78 + rng.gauss(0, 0.08)),
                              th=th, cos=math.cos(th), sin=math.sin(th)))
            x += spacing
        y += dy
        r += 1
    return cells


def stimulus(t):
    """Disc position and radius at time t; periodic in PERIOD so the loop is seamless."""
    w = 2 * math.pi / PERIOD
    x = 860 + 230 * math.sin(w * t) + 40 * math.sin(3 * w * t + 0.7)
    y = 130 + 80 * math.sin(2 * w * t + 1.1) + 15 * math.cos(5 * w * t)
    R = 20 * (1 + 0.8 * (0.5 + 0.5 * math.sin(2 * w * t)) ** 2)
    return x, y, R


def dog(c, px, py, R):
    """Overlap of a uniform disc (approximated as a Gaussian, var R^2/4) with a DoG receptive field."""
    dx, dy = px - c["x"], py - c["y"]
    u, v = dx * c["cos"] + dy * c["sin"], -dx * c["sin"] + dy * c["cos"]
    vd = R * R / 4

    def cen(sx, sy):
        vx, vy = sx * sx + vd, sy * sy + vd
        return min(1.0, R * R / (2 * math.sqrt(vx * vy))) * math.exp(-((u * u) / vx + (v * v) / vy) / 2)

    return cen(c["sx"], c["sy"]) - 0.75 * cen(c["sx"] * 2.1, c["sy"] * 2.1)


def simulate(cells):
    steps = int(PERIOD / DT)
    kf, ks = 1 - math.exp(-DT * 6), 1 - math.exp(-DT * 1.4)
    for c in cells:
        c["drive"] = c["slow"] = 0.0
        c["r"] = []
    for k in range(2 * steps):  # first loop warms up the filters; keep the second
        x, y, R = stimulus(k * DT)
        for c in cells:
            d = dog(c, x, y, R) if abs(c["x"] - x) < R * 3 + c["sx"] * 6 else 0.0
            c["drive"] += (d - c["drive"]) * kf
            c["slow"] += (c["drive"] - c["slow"]) * ks
            resp = c["drive"] + 1.4 * (c["drive"] - c["slow"]) if c["kind"] == "off" else 2.6 * (c["slow"] - c["drive"])
            if k >= steps:
                c["r"].append(max(0.0, min(1.0, resp * 2.1)))
    return steps


def keyframes(series, steps, fmt):
    """Subsample to keyframes and drop points that are equal to both neighbours."""
    idx = list(range(0, steps, KEY_EVERY)) + [0]  # close the loop on the first value
    vals = [fmt(series[i]) for i in idx]
    times = [i * KEY_EVERY / steps for i in range(len(idx) - 1)] + [1.0]
    keep = [0] + [i for i in range(1, len(vals) - 1) if not (vals[i] == vals[i - 1] == vals[i + 1])] + [len(vals) - 1]
    return ";".join(f"{times[i]:.4g}" for i in keep), ";".join(vals[i] for i in keep)


def render(theme, cells, steps, rows):
    T = THEMES[theme]
    dur = f'dur="{PERIOD:g}s" repeatCount="indefinite"'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           f'aria-label="Simone Azeglio. The geometry of visual information. Animated retinal receptive-field mosaic.">',
           "<defs>",
           f'<linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="{T["paper"]}"/>'
           f'<stop offset="0.33" stop-color="{T["paper"]}" stop-opacity="0.94"/>'
           f'<stop offset="0.52" stop-color="{T["paper"]}" stop-opacity="0.35"/>'
           f'<stop offset="0.66" stop-color="{T["paper"]}" stop-opacity="0"/></linearGradient>',
           f'<linearGradient id="band" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{T["paper"]}" stop-opacity="0"/>'
           f'<stop offset="0.35" stop-color="{T["paper"]}" stop-opacity="0.9"/></linearGradient>',
           f'<clipPath id="clip"><rect width="{W}" height="{H}" rx="14"/></clipPath>',
           "</defs>",
           '<g clip-path="url(#clip)">',
           f'<rect width="{W}" height="{H}" fill="{T["paper"]}"/>']

    # stimulus (drawn under the cells)
    xs, ys, rs = zip(*(stimulus(k * DT) for k in range(steps)))
    kt, vx = keyframes(xs, steps, lambda v: f"{v:.1f}")
    _, vy = keyframes(ys, steps, lambda v: f"{v:.1f}")
    _, vr = keyframes(rs, steps, lambda v: f"{v:.1f}")
    ring = f' stroke="{T["ring"]}"' if T["ring"] != "none" else ""
    out.append(f'<circle fill="{T["stim"]}" fill-opacity="0.9"{ring} cx="{xs[0]:.1f}" cy="{ys[0]:.1f}" r="{rs[0]:.1f}">'
               f'<animate attributeName="cx" keyTimes="{kt}" values="{vx}" {dur}/>'
               f'<animate attributeName="cy" keyTimes="{kt}" values="{vy}" {dur}/>'
               f'<animate attributeName="r" keyTimes="{kt}" values="{vr}" {dur}/></circle>')

    # cells
    for c in cells:
        col = T["off"] if c["kind"] == "off" else T["on"]
        base = 0.32 if c["kind"] == "off" else 0.13
        geom = (f'cx="{c["x"]:.1f}" cy="{c["y"]:.1f}" rx="{c["sx"] * 1.1:.1f}" ry="{c["sy"] * 1.1:.1f}" '
                f'transform="rotate({math.degrees(c["th"]):.1f} {c["x"]:.1f} {c["y"]:.1f})"')
        if max(c["r"]) < 0.04:
            out.append(f'<ellipse {geom} fill="none" stroke="{col}" stroke-opacity="{base}"/>')
            continue
        kt, fill = keyframes(c["r"], steps, lambda v: f"{v * 0.5:.2f}")
        _, stroke = keyframes(c["r"], steps, lambda v, b=base: f"{b + 0.6 * v:.2f}")
        out.append(f'<ellipse {geom} fill="{col}" fill-opacity="0" stroke="{col}" stroke-opacity="{base}">'
                   f'<animate attributeName="fill-opacity" keyTimes="{kt}" values="{fill}" {dur}/>'
                   f'<animate attributeName="stroke-opacity" keyTimes="{kt}" values="{stroke}" {dur}/></ellipse>')

    # recorded cells, marked like electrode sites
    for row in rows:
        c = row["cell"]
        col = T["off"] if c["kind"] == "off" else T["on"]
        out.append(f'<circle cx="{c["x"]:.1f}" cy="{c["y"]:.1f}" r="2" fill="{col}"/>'
                   f'<circle cx="{c["x"]:.1f}" cy="{c["y"]:.1f}" r="5" fill="none" stroke="{col}" stroke-opacity="0.5"/>')

    # raster: a strip twice the width, scrolled left by one width per loop
    out.append(f'<rect y="{RASTER_TOP - 22}" width="{W}" height="{H - RASTER_TOP + 22}" fill="url(#band)"/>')
    out.append(f'<g><animateTransform attributeName="transform" type="translate" from="0 0" to="-{W} 0" {dur}/>')
    row_h = RASTER_H / len(rows)
    for i, row in enumerate(rows):
        col = T["off"] if row["cell"]["kind"] == "off" else T["on"]
        y = RASTER_TOP + i * row_h + row_h * 0.15
        ticks = "".join(f"M{x0 + t / PERIOD * W:.1f} {y:.1f}v{row_h * 0.7:.1f}" for t in row["spikes"] for x0 in (0, W))
        out.append(f'<path d="{ticks}" stroke="{col}" stroke-width="1.3"/>')
    out.append("</g>")

    # text over a left fade
    serif, mono = "Georgia, 'Times New Roman', serif", "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    out.append(f'<rect width="{W}" height="{RASTER_TOP - 22}" fill="url(#fade)"/>')
    out.append(f'<text x="56" y="86" font-family="{mono}" font-size="12" letter-spacing="2.2" fill="{T["ink3"]}">'
               "COMPUTATIONAL NEUROSCIENCE · MACHINE LEARNING</text>")
    out.append(f'<text x="54" y="148" font-family="{serif}" font-size="56" letter-spacing="-1.2" fill="{T["ink"]}">Simone Azeglio</text>')
    out.append(f'<text x="56" y="190" font-family="{serif}" font-style="italic" font-size="23" fill="{T["ink2"]}">'
               "The geometry of visual information.</text>")
    out.append(f'<text x="56" y="224" font-family="{serif}" font-style="italic" font-size="17">'
               f'<tspan fill="{T["ink"]}">Statistics.</tspan> <tspan fill="{T["off"]}">Symmetry.</tspan> '
               f'<tspan fill="{T["on"]}">Information.</tspan></text>')
    out.append(f'<text x="56" y="{RASTER_TOP - 6}" font-family="{mono}" font-size="10" fill="{T["ink3"]}">'
               f"spikes · {len(rows)} cells</text>")
    out.append("</g></svg>")
    return "\n".join(out)


def main():
    rng = random.Random(7)
    spacing = 36
    cells = lattice(rng, spacing * 1.12, "on", spacing * 0.31, spacing * 0.2) + lattice(rng, spacing, "off", 0, 0)
    steps = simulate(cells)

    # raster rows: the most active cells along the path, OFF rows first
    active = sorted(cells, key=lambda c: -sum(c["r"]))
    picked = [c for c in active if c["kind"] == "off"][:10] + [c for c in active if c["kind"] == "on"][:6]
    rows = []
    for c in sorted(picked, key=lambda c: (c["kind"] != "off", c["y"])):
        # 60 px/s scroll: cap the rate so ticks stay a few pixels apart instead of merging into bars
        spikes = [k * DT for k in range(steps) if rng.random() < (1.0 + 18 * c["r"][k]) * DT]
        rows.append(dict(cell=c, spikes=spikes))

    out_dir = Path(__file__).resolve().parent.parent / "assets"
    out_dir.mkdir(exist_ok=True)
    for theme in THEMES:
        svg = render(theme, cells, steps, rows)
        path = out_dir / f"banner-{theme}.svg"
        path.write_text(svg)
        print(f"{path.name}: {len(svg) / 1024:.0f} KB, {len(cells)} cells, "
              f"{sum(max(c['r']) >= 0.04 for c in cells)} animated")


if __name__ == "__main__":
    main()
