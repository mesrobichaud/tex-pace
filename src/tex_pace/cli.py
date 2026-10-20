"""Command line interface: tex-pace init | log | status | plot | recipe."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, history
from .config import CONFIG_NAME, TEMPLATE, Config, ConfigError, load
from .count import COMMENT_RE, CountError, collect_files, count_pages, count_words, git_commit


def warn(message):
    print(f"tex-pace: warning: {message}", file=sys.stderr)


def die(message):
    print(f"tex-pace: error: {message}", file=sys.stderr)
    sys.exit(1)


def measure(cfg: Config, pdf: Path | None) -> tuple[dict[str, int], int | None]:
    """Words per file and the page count (None, with a warning, if the PDF can't be read)."""
    files, warnings = collect_files(cfg)
    for w in warnings:
        warn(w)
    words = count_words(cfg, files)
    try:
        pages = count_pages(cfg, pdf or cfg.pdf)
    except CountError as e:
        warn(e)
        pages = None
    return words, pages


def progress_lines(cfg: Config, words: int, pages: int | None) -> list[str]:
    """Counts with their change since the last build before today, and the pace needed to reach the goals."""
    today = dt.date.today().isoformat()
    before = [row for day, row in history.daily(history.read(cfg.csv)).items() if day < today]
    lines = []
    for name, now, goal in (("words", words, cfg.goal_words), ("pages", pages, cfg.goal_pages)):
        if now is None:
            continue
        line = f"{now:,} {name}"
        if before and before[-1][name]:
            line += f" ({now - int(before[-1][name]):+,} today)"
        if goal:
            left = goal - now
            line += f", goal {goal:,}: " + (f"{left:,} to go" if left > 0 else "reached")
            if cfg.goal_date and left > 0:
                days = (cfg.goal_date - dt.date.today()).days
                line += (f", {math.ceil(left / days):,}/day for {days} days" if days > 0
                         else f", goal date {cfg.goal_date} has passed")
        lines.append(line)
    return lines


def cmd_log(args):
    try:
        cfg = load(args.project)
        words, pages = measure(cfg, args.pdf)
        total = sum(words.values())
        summary = "; ".join(progress_lines(cfg, total, pages))
        history.append(cfg.csv, {"timestamp": datetime.now().isoformat(timespec="seconds"),
                                 "commit": git_commit(cfg.root), "words": total,
                                 "pages": "" if pages is None else pages})
        print(f"tex-pace: {summary}")
        if args.plot:
            history.plot(cfg)
    except (ConfigError, CountError, OSError) as e:
        # A failed tool fails the LaTeX Workshop recipe (and the PDF refresh), so only warn unless --strict.
        die(e) if args.strict else warn(e)
    except Exception as e:
        if args.strict:
            raise
        warn(f"{type(e).__name__}: {e} (run with --strict for the traceback)")


def cmd_status(args):
    try:
        cfg = load(args.project)
        words, pages = measure(cfg, args.pdf)
    except (ConfigError, CountError) as e:
        die(e)
    width = max([len(name) for name in words] + [5])
    for name, n in words.items():
        print(f"  {name:<{width}}  {n:>8,}")
    print(f"  {'':<{width}}  {'-' * 8}")
    for line in progress_lines(cfg, sum(words.values()), pages):
        print(f"  {line}")


def cmd_plot(args):
    try:
        cfg = load(args.project)
    except ConfigError as e:
        die(e)
    if not history.read(cfg.csv):
        die(f"nothing logged yet in {cfg.rel(cfg.csv)} (run `tex-pace log` or build with the recipe)")
    history.plot(cfg)
    print(f"tex-pace: wrote {cfg.rel(cfg.plot)}")


def find_main(root: Path) -> str | None:
    """The .tex file in `root` with a \\documentclass (other than subfiles), preferring main.tex."""
    mains = []
    for path in sorted(root.glob("*.tex")):
        text = COMMENT_RE.sub("", path.read_text(encoding="utf-8", errors="replace"))
        if re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{(?!subfiles\})", text):
            mains.append(path.name)
    for preferred in ("main.tex", "thesis.tex"):
        if preferred in mains:
            return preferred
    return mains[0] if mains else None


def recipe_settings() -> dict:
    latexmk = ["-synctex=1", "-interaction=nonstopmode", "-file-line-error", "-pdf", "-outdir=%OUTDIR%", "%DOC%"]
    log = ["log", "-C", "%DIR%", "--pdf", "%OUTDIR%/%DOCFILE%.pdf", "--plot"]
    # An absolute path, since VS Code's PATH often lacks conda envs, pipx, etc.
    scripts = Path(sys.executable).parent
    script = next((scripts / name for name in ("tex-pace", "tex-pace.exe") if (scripts / name).is_file()), None)
    command, args = (str(script), log) if script else (sys.executable, ["-m", "tex_pace", *log])
    return {
        "latex-workshop.latex.tools": [
            {"name": "latexmk", "command": "latexmk", "args": latexmk, "env": {}},
            {"name": "tex-pace", "command": command, "args": args, "env": {}},
        ],
        "latex-workshop.latex.recipes": [
            {"name": "latexmk + tex-pace", "tools": ["latexmk", "tex-pace"]},
            {"name": "latexmk", "tools": ["latexmk"]},
        ],
    }


def cmd_recipe(args):
    text = json.dumps(recipe_settings(), indent=2) + "\n"
    if not args.write:
        print(text, end="")
        return
    path = Path(args.project).resolve() / ".vscode" / "settings.json"
    if path.exists():
        die(f"{path} already exists; add these settings to it by hand:\n\n{text}")
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    print(f"tex-pace: wrote {path}")


def cmd_init(args):
    root = Path(args.project).resolve()
    path = root / CONFIG_NAME
    if path.exists() and not args.force:
        die(f"{path} already exists (use --force to overwrite it)")
    main = args.main or find_main(root)
    if main is None:
        warn(f"no .tex file with a \\documentclass in {root}; edit `include` in {CONFIG_NAME}")
        main = "main.tex"
    goal_date = dt.date.today().replace(year=dt.date.today().year + 1, day=1).isoformat()
    path.write_text(TEMPLATE.format(main=main, pdf=Path(main).with_suffix(".pdf").as_posix(), goal_date=goal_date))
    print(f"tex-pace: wrote {path} (counting {main} and the files it includes)")
    print("\nNext: check the include/exclude lists, then run `tex-pace status`. To log every build, add this to")
    print(".vscode/settings.json (or run `tex-pace recipe --write`):\n")
    print(json.dumps(recipe_settings(), indent=2))


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-C", "--project", type=Path, default=Path("."), metavar="DIR",
                        help=f"project folder; {CONFIG_NAME} is looked for here and in its parents (default: .)")
    pdf = argparse.ArgumentParser(add_help=False)
    pdf.add_argument("--pdf", type=lambda p: Path(p).resolve(), help="compiled PDF (default: `pdf` in the config)")

    parser = argparse.ArgumentParser(prog="tex-pace", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", parents=[common], help=f"create {CONFIG_NAME} for a LaTeX project")
    p.add_argument("--main", help="main .tex file, relative to the project (default: detected)")
    p.add_argument("--force", action="store_true", help=f"overwrite an existing {CONFIG_NAME}")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("log", parents=[common, pdf], help="count words and pages and add them to the log")
    p.add_argument("--plot", action="store_true", help="also update the plot")
    p.add_argument("--strict", action="store_true", help="exit with an error if counting fails (default: warn)")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("status", parents=[common, pdf], help="show the counts per file, without logging")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("plot", parents=[common], help="plot the logged counts over time")
    p.set_defaults(func=cmd_plot)

    p = sub.add_parser("recipe", parents=[common], help="print LaTeX Workshop settings that log every build")
    p.add_argument("--write", action="store_true", help="write them to .vscode/settings.json if it doesn't exist")
    p.set_defaults(func=cmd_recipe)

    args = parser.parse_args(argv)
    args.func(args)
