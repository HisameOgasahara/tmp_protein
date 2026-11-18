"""Draw the two figures the README leads with, from the stored result files.

Everything is plain SVG written by hand: no plotting library, nothing to
install, and the output is text that diffs. The inputs are the committed run
folders, so the figures regenerate exactly from the repository alone.

    python src/figures.py            # writes docs/figures/*.svg

Figure 1 puts three populations on one `pae_interaction` axis -- the labelled
calibration set, the 160 unselected designs, and the 50 sequences drawn on the
one backbone -- because the whole argument of this repository is about where
those three sit relative to the same pass line.

Figure 2 draws the design that passed, as predicted by AF2, on the target it
was designed against.
"""

import csv
import math
import sys
from pathlib import Path


VERSION = "0.2.0"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/figures"

CALIBRATION = "results/2026-11-18-trka88-calibration/calibration.csv"
BROAD = "results/2026-11-19-trka-design-v2/designs.csv"
FOCUS = "results/2026-11-19-design04-focus/designs.csv"
PASSED = "results/2026-11-19-design04-focus/predictions/design_04_r22_af2pred.pdb"

PASS_PAE = 10.0
CONTROL_PAE = 5.862
# The prediction renumbers both chains from 1, so the design-frame hotspot
# numbers shift. The shift is checked against residue identity below, because
# a wrong offset would quietly mark the wrong residues.
HOTSPOTS = {108: ("MET", "Met108"), 115: ("PHE", "Phe115"), 145: ("LEU", "Leu145")}
HOTSPOT_OFFSET = -20


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def label(x, y, text, size=14, anchor="end", fill="#0f172a", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{fill}" font-weight="{weight}" '
            f'font-family="Helvetica,Arial,sans-serif">{escape(text)}</text>')


def read_rows(path):
    with (ROOT / path).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def designs(path):
    """Scored, non-control rows of a run."""
    return [row for row in read_rows(path)
            if row["control"] == "False" and row["status"] == "success"]


# --------------------------------------------------------------------- figure 1

W1, H1 = 880, 430
X0, X1 = 200, 852
PAE_MAX = 30.0
ROWS_Y = (152, 264, 368)
BAR_MAX = 74
AXIS_Y = 386
BIN = 0.5


def x_of(value):
    return X0 + (X1 - X0) * min(value, PAE_MAX) / PAE_MAX


def bars(values, baseline, fill):
    """One bar per bin, heights proportional to the square root of the count.

    Linear heights would hide the handful of designs out at the good end: the
    plateau bin holds dozens, so everything else rounds to a pixel. The square
    root keeps every non-empty bin visible while preserving the shape, and the
    caption says so.
    """
    counts = {}
    for value in values:
        index = int(min(value, PAE_MAX - 1e-9) / BIN)
        counts[index] = counts.get(index, 0) + 1
    tallest = math.sqrt(max(counts.values()))
    pixels = (X1 - X0) * BIN / PAE_MAX
    return "".join(
        f'<rect x="{X0 + index * pixels:.1f}" '
        f'y="{baseline - BAR_MAX * math.sqrt(count) / tallest:.1f}" '
        f'width="{pixels - 0.9:.1f}" '
        f'height="{BAR_MAX * math.sqrt(count) / tallest:.1f}" fill="{fill}"/>'
        for index, count in sorted(counts.items()))


def dots(groups, baseline, radius=5.0, step=10.6):
    """One circle per value. Values sharing a bin stack, across all groups."""
    flat = sorted((value, style) for style, values in groups for value in values)
    seen = {}
    out = []
    for value, (fill, stroke) in flat:
        key = round(value / BIN)
        level = seen.get(key, 0)
        seen[key] = level + 1
        out.append(f'<circle cx="{x_of(value):.1f}" '
                   f'cy="{baseline - radius - level * step:.1f}" r="{radius}" '
                   f'fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    return "".join(out)


def figure_pae():
    calibration = read_rows(CALIBRATION)
    binders = [float(r["pae_interaction"]) for r in calibration
               if r["binder_experimental"] == "True"]
    others = [float(r["pae_interaction"]) for r in calibration
              if r["binder_experimental"] != "True"]
    broad = [float(r["pae_interaction"]) for r in designs(BROAD)]
    focus = [float(r["pae_interaction"]) for r in designs(FOCUS)]
    passed = min(focus)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W1} {H1}" '
             f'width="{W1}" height="{H1}" font-family="Helvetica,Arial,sans-serif">',
             f'<rect width="{W1}" height="{H1}" fill="#ffffff"/>',
             label(28, 34, "같은 자로 잰 세 집단", 19, "start", "#0f172a", "bold"),
             label(28, 56, "가로축 pae_interaction — 낮을수록 AF2가 계면을 믿는다",
                   13, "start", "#64748b")]

    # The pass line goes down first so the data sits on top of it.
    line_x = x_of(PASS_PAE)
    parts.append(f'<line x1="{line_x:.1f}" y1="64" x2="{line_x:.1f}" y2="{AXIS_Y}" '
                 f'stroke="#dc2626" stroke-width="2" stroke-dasharray="6 4"/>')
    parts.append(label(line_x + 7, 76, "통과선 10", 13, "start", "#dc2626", "bold"))

    # Row 1 -- the labelled set, one dot per design.
    parts.append(dots([(("#ffffff", "#94a3b8"), others),
                       (("#1d4ed8", "#1d4ed8"), binders)], ROWS_Y[0]))
    parts.append(label(X0 - 18, ROWS_Y[0] - 20, "교정 집합 20개", 15, "end",
                       "#0f172a", "bold"))
    parts.append(label(X0 - 18, ROWS_Y[0] - 2, "실험 라벨이 붙은 공개 설계",
                       12, "end", "#64748b"))
    legend_x = X0 + 356
    parts.append(f'<circle cx="{legend_x}" cy="84" r="5" fill="#1d4ed8"/>')
    parts.append(label(legend_x + 13, 89, f"실험상 결합 {len(binders)}개",
                       12, "start", "#1d4ed8"))
    parts.append(f'<circle cx="{legend_x}" cy="106" r="5" fill="#ffffff" '
                 f'stroke="#94a3b8" stroke-width="1.6"/>')
    parts.append(label(legend_x + 13, 111, f"실험상 비결합 {len(others)}개",
                       12, "start", "#64748b"))

    # Row 2 -- the unselected designs.
    parts.append(bars(broad, ROWS_Y[1], "#94a3b8"))
    parts.append(label(X0 - 18, ROWS_Y[1] - 20, f"날것 설계 {len(broad)}개", 15, "end",
                       "#0f172a", "bold"))
    parts.append(label(X0 - 18, ROWS_Y[1] - 2, "백본 20개 × 서열 8 · 0개 통과",
                       12, "end", "#64748b"))

    # Row 3 -- one backbone, resampled. The marker is drawn under the bars.
    pass_x = x_of(passed)
    parts.append(f'<line x1="{pass_x:.1f}" y1="292" x2="{pass_x:.1f}" '
                 f'y2="{ROWS_Y[2] - 2:.1f}" stroke="#0f172a" stroke-width="1.2"/>')
    parts.append(bars(focus, ROWS_Y[2], "#0284c7"))
    parts.append(label(pass_x, 286, f"design_04_r22  {passed:.3f}  — 유일한 통과",
                       13, "middle", "#0f172a", "bold"))
    parts.append(label(X0 - 18, ROWS_Y[2] - 20, f"design_04 서열 {len(focus)}개", 15, "end",
                       "#0f172a", "bold"))
    parts.append(label(X0 - 18, ROWS_Y[2] - 2, "백본 1개 × 서열 50 · 1개 통과",
                       12, "end", "#64748b"))

    # Axis.
    parts.append(f'<line x1="{X0}" y1="{AXIS_Y}" x2="{X1}" y2="{AXIS_Y}" '
                 f'stroke="#0f172a" stroke-width="1.4"/>')
    for tick in range(0, int(PAE_MAX) + 1, 5):
        tx = x_of(tick)
        parts.append(f'<line x1="{tx:.1f}" y1="{AXIS_Y}" x2="{tx:.1f}" y2="{AXIS_Y + 6}" '
                     f'stroke="#0f172a" stroke-width="1.4"/>')
        parts.append(label(tx, AXIS_Y + 22, str(tick), 13, "middle", "#0f172a"))

    # The control rode along in every batch, so it belongs to the axis.
    cx = x_of(CONTROL_PAE)
    parts.append(f'<polygon points="{cx:.1f},{AXIS_Y - 7} {cx - 5.5:.1f},{AXIS_Y - 17} '
                 f'{cx + 5.5:.1f},{AXIS_Y - 17}" fill="#15803d"/>')
    parts.append(label(cx - 10, AXIS_Y - 8, f"양성 대조군 {CONTROL_PAE}", 12,
                       "end", "#15803d"))

    parts.append(label(28, AXIS_Y + 40,
                       "막대 높이는 각 줄 안에서 개수의 제곱근에 비례 · 구간 폭 0.5",
                       12, "start", "#94a3b8"))
    parts.append(label(X1, AXIS_Y + 40, "pae_interaction", 13, "end", "#64748b"))
    parts.append("</svg>")
    return "\n".join(parts)


# --------------------------------------------------------------------- figure 2

W2 = 840
TOP, BOTTOM, SIDE = 92, 78, 44


def read_ca(path):
    chains = {}
    with (ROOT / path).open() as handle:
        for line in handle:
            if line.startswith("ATOM") and line[12:16].strip() == "CA":
                chains.setdefault(line[21], []).append(
                    (int(line[22:26]), line[17:20],
                     (float(line[30:38]), float(line[38:46]), float(line[46:54]))))
    return chains


def centroid(points):
    return [sum(p[i] for p in points) / len(points) for i in range(3)]


def normalise(vector):
    length = math.sqrt(sum(c * c for c in vector)) or 1.0
    return [c / length for c in vector]


def long_axis(points):
    """Direction of greatest spread, by power iteration on the covariance."""
    centre = centroid(points)
    shifted = [[p[i] - centre[i] for i in range(3)] for p in points]
    cov = [[sum(v[i] * v[j] for v in shifted) / len(points) for j in range(3)]
           for i in range(3)]
    vector = normalise([1.0, 0.3, 0.1])
    for _ in range(200):
        vector = normalise([sum(cov[i][j] * vector[j] for j in range(3)) for i in range(3)])
    return vector


def figure_structure():
    chains = read_ca(PASSED)
    binder, target = chains["A"], chains["B"]
    for original, (expected, _) in HOTSPOTS.items():
        found = next((name for number, name, _ in target
                      if number == original + HOTSPOT_OFFSET), None)
        if found != expected:
            raise RuntimeError(f"Hotspot B{original} maps to {found}, expected {expected}. "
                               f"The renumbering offset is wrong, so the marks would "
                               f"point at the wrong residues.")

    # View plane: the binder's own long axis, so its fold is seen side-on, plus
    # the direction towards the target, so the docking is seen rather than
    # looked down. A plain PCA of the whole complex puts the binder end-on.
    binder_points = [xyz for _, _, xyz in binder]
    axis = long_axis(binder_points)
    separation = [t - b for t, b in zip(centroid([xyz for _, _, xyz in target]),
                                        centroid(binder_points))]
    overlap = sum(a * b for a, b in zip(separation, axis))
    across = normalise([s - overlap * a for s, a in zip(separation, axis)])
    centre = centroid([xyz for _, _, xyz in binder + target])

    def spread(direction):
        values = [sum((xyz[i] - centre[i]) * direction[i] for i in range(3))
                  for _, _, xyz in binder + target]
        return max(values) - min(values)

    # The canvas is landscape, so the wider of the two directions goes across it.
    horizontal, vertical = ((axis, across) if spread(axis) >= spread(across)
                            else (across, axis))

    def project(xyz):
        shifted = [xyz[i] - centre[i] for i in range(3)]
        return (sum(a * b for a, b in zip(shifted, horizontal)),
                sum(a * b for a, b in zip(shifted, vertical)))

    flat = [project(xyz) for _, _, xyz in binder + target]
    xs = [p[0] for p in flat]
    ys = [p[1] for p in flat]
    # The drawing fills the width and the canvas height follows from the shape,
    # so no orientation leaves a band of empty paper.
    scale = (W2 - 2 * SIDE) / (max(xs) - min(xs))
    height = round(TOP + BOTTOM + (max(ys) - min(ys)) * scale)
    offset_x = SIDE - min(xs) * scale
    offset_y = TOP + max(ys) * scale

    def place(xyz):
        px, py = project(xyz)
        return px * scale + offset_x, -py * scale + offset_y

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W2} {height}" '
             f'width="{W2}" height="{height}" font-family="Helvetica,Arial,sans-serif">',
             f'<rect width="{W2}" height="{height}" fill="#ffffff"/>',
             label(28, 34, "design_04_r22 — 세 기준을 전부 통과한 첫 설계", 19,
                   "start", "#0f172a", "bold"),
             label(28, 56, "AF2 initial guess 예측 구조 · Cα 트레이스 · "
                           "회색이 표적 TrkA D5, 파란색이 설계한 결합여",
                   13, "start", "#64748b")]

    trace = " ".join(f"{x:.1f},{y:.1f}" for x, y in (place(xyz) for _, _, xyz in target))
    parts.append(f'<polyline points="{trace}" fill="none" stroke="#cbd5e1" '
                 f'stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>')

    placed = [place(xyz) for _, _, xyz in binder]
    for index in range(len(placed) - 1):
        shade = index / max(len(placed) - 2, 1)
        colour = (int(147 + (23 - 147) * shade), int(197 + (58 - 197) * shade),
                  int(253 + (138 - 253) * shade))
        (ax, ay), (bx, by) = placed[index], placed[index + 1]
        parts.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                     f'stroke="rgb{colour}" stroke-width="4.6" stroke-linecap="round"/>')

    marks = []
    for original, (_, name) in sorted(HOTSPOTS.items()):
        xyz = next(coords for number, _, coords in target
                   if number == original + HOTSPOT_OFFSET)
        hx, hy = place(xyz)
        marks.append([hx, hy, name])
        parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="6.5" fill="#f59e0b" '
                     f'stroke="#ffffff" stroke-width="2"/>')
    # Hotspots cluster at the interface, so their labels would land on top of
    # each other. Push each one clear of the ones already placed.
    binder_x = sum(point[0] for point in placed) / len(placed)
    taken = []
    for hx, hy, name in sorted(marks, key=lambda mark: mark[1]):
        # Label away from the binder, which is the crowded side.
        side = 1 if hx >= binder_x else -1
        ty = hy + 5
        while any(abs(ty - other) < 17 for other in taken):
            ty += 17
        taken.append(ty)
        parts.append(f'<line x1="{hx + side * 8:.1f}" y1="{hy:.1f}" '
                     f'x2="{hx + side * 14:.1f}" y2="{ty - 4:.1f}" '
                     f'stroke="#f59e0b" stroke-width="1.4"/>')
        parts.append(label(hx + side * 17, ty, name, 13,
                           "start" if side > 0 else "end", "#b45309", "bold"))

    for (px, py), text in ((placed[0], "N"), (placed[-1], "C")):
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#1e3a8a" '
                     f'stroke="#ffffff" stroke-width="2"/>')
        parts.append(label(px, py - 11, text, 13, "middle", "#1e3a8a", "bold"))

    parts.append(label(28, height - 52, "주황색은 설계가 겨냥한 hotspot 3개", 12,
                       "start", "#b45309"))
    parts.append(f'<rect x="28" y="{height - 44}" width="{W2 - 56}" height="32" rx="6" '
                 f'fill="#f1f5f9"/>')
    parts.append(label(W2 / 2, height - 23,
                       "pae_interaction 9.389  ·  plddt_binder 89.58  ·  "
                       "접힘 0.702 Å  ·  설계한 자리에서 1.407 Å",
                       14, "middle", "#0f172a", "bold"))
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draw in (("pae-overview", figure_pae), ("design04-r22", figure_structure)):
        path = OUT / f"{name}.svg"
        path.write_text(draw() + "\n", encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size:,} bytes")
    print(f"figures {VERSION}", file=sys.stderr)
