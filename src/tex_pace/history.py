"""The progress log (one CSV row per build) and its plot."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .config import Config

FIELDS = ("timestamp", "commit", "words", "pages")


def read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append(path: Path, row: dict) -> bool:
    """Add `row` unless it repeats the counts and commit of the last row of the same day. True if added."""
    rows = read(path)
    if rows:
        last = rows[-1]
        if last["timestamp"][:10] == row["timestamp"][:10] and all(
                last[k] == str(row[k]) for k in ("commit", "words", "pages")):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, FIELDS)
        if not rows:
            writer.writeheader()
        writer.writerow(row)
    return True


class LogError(Exception):
    pass


def daily(rows: list[dict]) -> dict[str, dict]:
    """The last row of each day, keyed by date (YYYY-MM-DD), in date order (rows may be added out of order)."""
    for line, row in enumerate(rows, start=2):
        try:
            datetime.fromisoformat(row["timestamp"])
            int(row["words"]), int(row["pages"] or 0)
        except (KeyError, TypeError, ValueError):
            raise LogError(f"can't read line {line}: {','.join(map(str, row.values()))!r} (expected e.g. "
                           f"2026-10-20,,12500,41 or 2026-10-20T14:30:00,,12500,)") from None
    return {row["timestamp"][:10]: row for row in sorted(rows, key=lambda row: row["timestamp"])}


def _smooth(x, y, n=300):
    """A monotone cubic (PCHIP) through the points: smooth, but never overshooting them (or dipping below zero)."""
    import numpy as np

    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        return x, y
    h, d = np.diff(x), np.diff(y) / np.diff(x)
    m = np.empty_like(y)
    m[0], m[-1] = d[0], d[-1]
    w1, w2 = 2 * h[1:] + h[:-1], h[1:] + 2 * h[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        m[1:-1] = np.where(d[:-1] * d[1:] > 0, (w1 + w2) / (w1 / d[:-1] + w2 / d[1:]), 0)
    xs = np.linspace(x[0], x[-1], n)
    k = np.clip(np.searchsorted(x, xs, side="right") - 1, 0, len(x) - 2)
    t = (xs - x[k]) / h[k]
    ys = ((2 * t**3 - 3 * t**2 + 1) * y[k] + (t**3 - 2 * t**2 + t) * h[k] * m[k]
          + (-2 * t**3 + 3 * t**2) * y[k + 1] + (t**3 - t**2) * h[k] * m[k + 1])
    return xs, ys


def plot(cfg: Config):
    """Words and pages over time, one panel each, labelled only with the latest counts."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    days = daily(read(cfg.csv))
    if not days:
        return
    series = []
    for key, goal, color in (("words", cfg.goal_words, "#2a78d6"), ("pages", cfg.goal_pages, "#eb6834")):
        points = [(mdates.date2num(datetime.fromisoformat(day)), int(r[key])) for day, r in days.items() if r[key]]
        if points:
            series.append((key, goal, color, points))
    fig, axes = plt.subplots(len(series), 1, sharex=True, squeeze=False, figsize=(4, 0.3 + 1.6 * len(series)),
                             layout="constrained")
    for ax, (key, goal, color, points) in zip(axes[:, 0], series):
        x, y = zip(*points)
        ax.fill_between(*_smooth(x, y), color=color, alpha=0.15, linewidth=0)
        ax.plot(*_smooth(x, y), color=color, linewidth=2, solid_capstyle="round")
        ax.plot(x[-1], y[-1], "o", color=color, markersize=7, markeredgecolor="white", markeredgewidth=1.5,
                clip_on=False)
        ax.text(0, 1, f"{y[-1]:,}" + (f" of {goal:,}" if goal else "") + f" {key}", transform=ax.transAxes,
                ha="left", va="top", fontsize=13, color="#0b0b0b")
        ax.set_ylim(0, max(y) * 1.4 or 1)       # headroom above the curve for the label
        ax.set_yticks([])
        for side in ("left", "right", "top"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("0.85")
        ax.tick_params(length=0, labelsize=8, labelcolor="#6b6a66")
    start, end = mdates.date2num(datetime.fromisoformat(min(days))), mdates.date2num(datetime.fromisoformat(max(days)))
    bottom = axes[-1, 0]
    bottom.set_xticks([start, end] if end > start else [start])
    bottom.xaxis.set_major_formatter(lambda v, _: f"{mdates.num2date(v):%b} {mdates.num2date(v).day}")
    if end > start:
        bottom.set_xlim(start, end)
        bottom.get_xticklabels()[0].set_ha("left")
        bottom.get_xticklabels()[-1].set_ha("right")
    cfg.plot.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(cfg.plot, dpi=150)
    plt.close(fig)
