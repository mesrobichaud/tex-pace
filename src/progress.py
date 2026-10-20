#!/usr/bin/env python3
"""Log the thesis word and page counts after each build, and plot them over time.

Words: body text of the files in CHAPTERS, counted by TeXcount (headings, captions and the bibliography are not
counted). Pages: from the PDF page labelled "1" up to the page before the last "References" bookmark.

    python3 tools/progress.py log --pdf main.pdf [--plot]
    python3 tools/progress.py plot

Needs texcount (TeX Live / MacTeX), pypdf, and matplotlib for the plot.
"""
import argparse
import csv
import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent       # repo root (this file is in tools/)
CHAPTERS = [                                         # chapter files, relative to ROOT
    "chapters/introduction.tex",
    "chapters/methods.tex",
]
BIB_TITLES = ("references", "bibliography")          # bookmark titles where the counted pages end
CSV_PATH = ROOT / "tools" / "progress.csv"
PNG_PATH = ROOT / "tools" / "progress.png"
FIELDS = ("timestamp", "commit", "words", "pages")


def count_words():
    """Words in body text of CHAPTERS (files they \\input or \\include are followed)."""
    out = subprocess.run(["texcount", "-inc", "-total", "-utf8", *CHAPTERS], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return int(re.findall(r"Words in text:\s*(\d+)", out)[-1])


def _bookmarks(outline):
    for item in outline:
        if isinstance(item, list):
            yield from _bookmarks(item)
        else:
            yield item


def count_pages(pdf):
    """Pages from the one labelled "1" to the page before the last References bookmark (end of PDF if none)."""
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    labels = reader.page_labels
    start = labels.index("1") if "1" in labels else 0
    end = len(reader.pages)
    for item in _bookmarks(reader.outline):
        if item.title.strip().lower() in BIB_TITLES:
            end = reader.get_destination_page_number(item)
    return end - start


def git_commit():
    """Short hash of HEAD, with "+" if there are uncommitted changes."""
    run = lambda *args: subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return run("rev-parse", "--short", "HEAD") + ("+" if run("status", "--porcelain") else "")


def log(pdf):
    row = {"timestamp": datetime.now().isoformat(timespec="seconds"), "commit": git_commit(),
           "words": count_words(), "pages": count_pages(pdf)}
    new = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(row)
    print(f"progress: {row['words']} words, {row['pages']} pages")


def plot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with open(CSV_PATH, newline="") as f:
        daily = {row["timestamp"][:10]: row for row in csv.DictReader(f)}     # last build of each day
    dates = [datetime.fromisoformat(day) for day in daily]

    fig, (ax_w, ax_p) = plt.subplots(2, 1, sharex=True, figsize=(6, 4), layout="constrained")
    ax_w.plot(dates, [int(r["words"]) for r in daily.values()], marker="o", markersize=3)
    ax_p.plot(dates, [int(r["pages"]) for r in daily.values()], marker="o", markersize=3, color="tab:orange")
    ax_w.set_ylabel("Words")
    ax_p.set_ylabel("Pages")
    for ax in (ax_w, ax_p):
        ax.grid(True, color="0.85", linewidth=0.6)
    fig.autofmt_xdate()
    fig.savefig(PNG_PATH, dpi=150)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("log", "plot"))
    parser.add_argument("--pdf", default=ROOT / "main.pdf", help="compiled thesis PDF (default: main.pdf)")
    parser.add_argument("--plot", action="store_true", help="after logging, also update the plot")
    args = parser.parse_args()
    if args.command == "log":
        log(args.pdf)
    if args.command == "plot" or args.plot:
        plot()
