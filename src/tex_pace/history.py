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


def daily(rows: list[dict]) -> dict[str, dict]:
    """The last row of each day, keyed by date (YYYY-MM-DD)."""
    return {row["timestamp"][:10]: row for row in rows}


def plot(cfg: Config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    days = daily(read(cfg.csv))
    if not days:
        return
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(6, 4), layout="constrained")
    for ax, key, label, goal, color in ((axes[0], "words", "Words", cfg.goal_words, "tab:blue"),
                                        (axes[1], "pages", "Pages", cfg.goal_pages, "tab:orange")):
        points = [(datetime.fromisoformat(day), int(r[key])) for day, r in days.items() if r[key]]
        if points:
            ax.plot(*zip(*points), marker="o", markersize=3, color=color)
        if goal:
            ax.axhline(goal, color=color, linestyle="--", linewidth=0.8, alpha=0.6)
        ax.set_ylabel(label)
        ax.grid(True, color="0.85", linewidth=0.6)
    locator = mdates.AutoDateLocator()
    axes[1].xaxis.set_major_locator(locator)
    axes[1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    cfg.plot.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(cfg.plot, dpi=150)
    plt.close(fig)
