"""12-lead ECG as SVG on grid paper: a 3x4 lead layout (2.5 s each) plus a 10 s lead II rhythm strip.

Units are millimetres at standard paper speed (25 mm/s) and gain (10 mm/mV). The SVG contains only
lead names and the speed/gain note, no prose, so it needs no translation.
"""

from collections.abc import Mapping, Sequence

SPEED = 25  # mm/s
GAIN = 10  # mm/mV
SECONDS = 10
WIDTH = SPEED * SECONDS  # 250 mm
ROW = 30  # mm between baselines
MARGIN = 5
HEIGHT = 4 * ROW + 2 * MARGIN
LAYOUT = (("I", "aVR", "V1", "V4"), ("II", "aVL", "V2", "V5"), ("III", "aVF", "V3", "V6"))
RHYTHM = "II"
DISPLAY_RATE = 250  # Hz; 500 Hz input is halved, invisible at this scale, half the file size

GRID = f"""<defs>
<pattern id="minor" width="1" height="1" patternUnits="userSpaceOnUse"><path d="M1 0H0V1" fill="none" stroke="#f4b6b6" stroke-width="0.05"/></pattern>
<pattern id="major" width="5" height="5" patternUnits="userSpaceOnUse"><rect width="5" height="5" fill="url(#minor)"/><path d="M5 0H0V5" fill="none" stroke="#e57373" stroke-width="0.15"/></pattern>
</defs>
<rect width="{WIDTH + 2 * MARGIN}" height="{HEIGHT}" fill="#fff"/>
<rect x="{MARGIN}" y="{MARGIN}" width="{WIDTH}" height="{4 * ROW}" fill="url(#major)"/>"""


def _trace(samples: Sequence[float], rate: int, start: float, seconds: float, x0: float, y0: float) -> str:
    step = max(1, rate // DISPLAY_RATE)
    first, last = round(start * rate), round((start + seconds) * rate)
    points = " ".join(
        f"{x0 + (i - first) / rate * SPEED:.2f},{y0 - samples[i] * GAIN:.2f}" for i in range(first, min(last, len(samples)), step)
    )
    return f'<polyline points="{points}"/>'


def render_svg(leads: Mapping[str, Sequence[float]], rate: int) -> bytes:
    col = SECONDS / 4
    parts, labels = [], []
    for r, row in enumerate(LAYOUT):
        y0 = MARGIN + ROW * (r + 0.5)
        for c, lead in enumerate(row):
            x0 = MARGIN + c * col * SPEED
            parts.append(_trace(leads[lead], rate, c * col, col, x0, y0))
            labels.append(f'<text x="{x0 + 1}" y="{y0 - ROW / 2 + 4}">{lead}</text>')
    y0 = MARGIN + ROW * 3.5
    parts.append(_trace(leads[RHYTHM], rate, 0, SECONDS, MARGIN, y0))
    labels.append(f'<text x="{MARGIN + 1}" y="{y0 - ROW / 2 + 4}">{RHYTHM}</text>')
    labels.append(f'<text x="{MARGIN + WIDTH}" y="{HEIGHT - 1}" text-anchor="end">{SPEED} mm/s  {GAIN} mm/mV</text>')
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH + 2 * MARGIN} {HEIGHT}" width="{WIDTH + 2 * MARGIN}mm" height="{HEIGHT}mm">
{GRID}
<g fill="none" stroke="#000" stroke-width="0.2" stroke-linejoin="round">{"".join(parts)}</g>
<g font-family="sans-serif" font-size="3">{"".join(labels)}</g>
</svg>
"""
    return svg.encode()
