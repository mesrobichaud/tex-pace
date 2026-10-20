"""Find and read a project's tex-pace.toml."""
from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CONFIG_NAME = "tex-pace.toml"

TEMPLATE = """\
# tex-pace configuration. Paths are relative to this file.

# Files whose words are counted (globs allowed). Files they \\input, \\include, \\subfile or \\import are
# followed too, unless excluded below.
include = ["{main}"]

# Files left out of the count, and not followed. A pattern without a "/" matches a file name in any folder.
exclude = [
    # "frontmatter/*",
    # "appendix*.tex",
]

# Set to false to count only the files matched by `include`.
follow_inputs = true

# Compiled PDF used for the page count (the LaTeX Workshop recipe passes --pdf, which overrides this).
pdf = "{pdf}"

[words]
headers = false        # also count words in \\section{{...}} etc.
captions = false       # also count words in figure and table captions
texcount = "texcount"  # path to texcount, if it is not on PATH
texcount_args = []     # extra arguments for texcount, e.g. ["-incbib"]

[pages]
# Pages are counted from the PDF page labelled `start_label` (so roman-numbered front matter is skipped) up to
# the page before the last bookmark named in `end_bookmarks` (needs hyperref). Use start_label = "" to start
# at the first page, and end_bookmarks = [] to count to the end of the PDF.
start_label = "1"
end_bookmarks = ["References", "Bibliography"]

[output]
csv = "tex-pace/progress.csv"
plot = "tex-pace/progress.png"

[goal]
# words = 80000
# pages = 200
# date = {goal_date}
"""


class ConfigError(Exception):
    pass


@dataclass
class Config:
    path: Path
    include: list[str]
    exclude: list[str]
    follow_inputs: bool
    pdf: Path
    headers: bool
    captions: bool
    texcount: str
    texcount_args: list[str]
    start_label: str
    end_bookmarks: list[str]
    csv: Path
    plot: Path
    goal_words: int | None
    goal_pages: int | None
    goal_date: dt.date | None

    @property
    def root(self) -> Path:
        return self.path.parent

    def rel(self, path: Path) -> str:
        """`path` relative to the project root (absolute if it is outside it), with forward slashes."""
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def is_excluded(self, path: Path) -> bool:
        rel = self.rel(path)
        for pattern in self.exclude:
            for pat in (pattern, pattern + ".tex"):
                if fnmatch(rel, pat) or ("/" not in pat and PurePosixPath(rel).match(pat)):
                    return True
        return False


def find(start: Path) -> Path | None:
    """The nearest tex-pace.toml in `start` or one of its parents."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / CONFIG_NAME).is_file():
            return folder / CONFIG_NAME
    return None


def load(start: Path) -> Config:
    path = find(start)
    if path is None:
        raise ConfigError(f"no {CONFIG_NAME} in {start.resolve()} or its parents (create one with `tex-pace init`)")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None

    def get(table, key, kind, default):
        section = data if table is None else data.get(table, {})
        value = section.get(key, default)
        if value is not None and not isinstance(value, kind):
            name = key if table is None else f"{table}.{key}"
            raise ConfigError(f"{path}: `{name}` should be {getattr(kind, '__name__', kind)}, not {value!r}")
        if kind is list and value and not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{path}: `{key}` should be a list of strings")
        return value

    root = path.parent
    include = get(None, "include", list, None)
    if not include:
        raise ConfigError(f"{path}: `include` should list at least one .tex file")
    return Config(
        path=path,
        include=include,
        exclude=get(None, "exclude", list, []),
        follow_inputs=get(None, "follow_inputs", bool, True),
        pdf=root / get(None, "pdf", str, "main.pdf"),
        headers=get("words", "headers", bool, False),
        captions=get("words", "captions", bool, False),
        texcount=get("words", "texcount", str, "texcount"),
        texcount_args=get("words", "texcount_args", list, []),
        start_label=get("pages", "start_label", str, "1"),
        end_bookmarks=get("pages", "end_bookmarks", list, ["References", "Bibliography"]),
        csv=root / get("output", "csv", str, "tex-pace/progress.csv"),
        plot=root / get("output", "plot", str, "tex-pace/progress.png"),
        goal_words=get("goal", "words", int, None),
        goal_pages=get("goal", "pages", int, None),
        goal_date=get("goal", "date", dt.date, None),
    )
