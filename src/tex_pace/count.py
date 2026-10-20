"""Word counts (via TeXcount), page counts (via pypdf) and the git commit of a project."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import Config

COMMENT_RE = re.compile(r"(?<!\\)%.*")
INCLUDE_RE = re.compile(
    r"\\(?:(?P<cmd>input|include|subfileinclude|subfile)\s*\{(?P<file>[^}]*)\}"
    r"|(?P<imp>(?:sub)?(?:import|inputfrom|includefrom))\*?\s*\{(?P<dir>[^}]*)\}\s*\{(?P<ifile>[^}]*)\})")
BRIEF_RE = re.compile(r"^(\d+)\+(\d+)\+(\d+) \(.*?\) File: (.*)$", re.M)


class CountError(Exception):
    pass


def _resolve(name: str, folders: list[Path]) -> Path | None:
    """The .tex file LaTeX would load for \\input{name}, looked for in each of `folders`."""
    name = name.strip()
    candidate = name if name.endswith(".tex") else name + ".tex"
    for folder in folders:
        if (folder / candidate).is_file():
            return (folder / candidate).resolve()
    return None


def collect_files(cfg: Config) -> tuple[list[Path], list[str]]:
    """The files to count, in reading order, and warnings about inputs that could not be found."""
    files, seen, warnings = [], set(), []

    def visit(path: Path, base: Path):
        if path in seen:
            return
        seen.add(path)
        if cfg.is_excluded(path):
            return
        files.append(path)
        if not cfg.follow_inputs:
            return
        text = COMMENT_RE.sub("", path.read_text(encoding="utf-8", errors="replace"))
        for m in INCLUDE_RE.finditer(text):
            if m["cmd"]:
                name, folders, child_base = m["file"], [base, path.parent], base
            else:                                       # \import{dir}{file}: dir is from the project root,
                sub = m["imp"].startswith("sub")        # \subimport{dir}{file}: from the importing file
                folder = (base if sub else cfg.root) / m["dir"].strip()
                name, folders = m["ifile"], [folder] + ([path.parent / m["dir"].strip()] if sub else [])
                child_base = folder
            child = _resolve(name, folders)
            if child:
                visit(child, child_base if m["cmd"] else child.parent)
            elif Path(name.strip()).suffix in ("", ".tex"):     # \input{plot.pgf} etc. are not text
                warnings.append(f"{cfg.rel(path)}: could not find the file in {m[0]}")

    for pattern in cfg.include:
        matches = sorted(cfg.root.glob(pattern))
        if not matches:
            warnings.append(f"`include` pattern {pattern!r} matches no files in {cfg.root} (paths are relative to {cfg.path.name})")
        for match in matches:
            visit(match.resolve(), cfg.root)
    return files, warnings


def count_words(cfg: Config, files: list[Path]) -> dict[str, int]:
    """Words in each file, keyed by path relative to the project root."""
    if not files:
        return {}
    names = [cfg.rel(f) for f in files]
    try:
        run = subprocess.run([cfg.texcount, "-brief", "-utf8", *cfg.texcount_args, *names], cwd=cfg.root,
                             capture_output=True, text=True)
    except FileNotFoundError:
        raise CountError(f"`{cfg.texcount}` not found: install it (`tlmgr install texcount`, e.g. for TinyTeX), "
                         f"or set words.texcount in {cfg.path.name} to its full path") from None
    if run.returncode != 0:
        raise CountError(f"texcount failed: {run.stderr.strip() or run.stdout.strip()}")
    counts = {}
    for text, headers, captions, name in BRIEF_RE.findall(run.stdout):
        counts[name.strip()] = int(text) + cfg.headers * int(headers) + cfg.captions * int(captions)
    return {name: counts.get(name, 0) for name in names}


def _bookmarks(outline):
    for item in outline:
        if isinstance(item, list):
            yield from _bookmarks(item)
        else:
            yield item


def count_pages(cfg: Config, pdf: Path) -> int:
    """Pages from the one labelled start_label to the page before the last end bookmark (or the end)."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    if not pdf.is_file():
        raise CountError(f"PDF not found: {pdf}")
    try:
        reader = PdfReader(pdf)
        labels = reader.page_labels
        start = labels.index(cfg.start_label) if cfg.start_label in labels else 0
        end = len(reader.pages)
        titles = {t.strip().lower() for t in cfg.end_bookmarks}
        for item in _bookmarks(reader.outline):
            if item.title.strip().lower() in titles:
                end = reader.get_destination_page_number(item)
    except (PyPdfError, OSError) as e:
        raise CountError(f"could not read {pdf}: {e}") from None
    return max(end - start, 0)


def git_commit(root: Path) -> str:
    """Short hash of HEAD, with "+" if there are uncommitted changes ("" outside a git repository)."""
    def git(*args):
        try:
            run = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        except FileNotFoundError:
            return None
        return run.stdout.strip() if run.returncode == 0 else None

    head = git("rev-parse", "--short", "HEAD")
    return head + ("+" if git("status", "--porcelain") else "") if head else ""
