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
# tex-pace configuration. Paths are relative to this file. See the tex-pace README for details and examples.

{include:<31}# files to count (globs allowed); the files they \\input or \\include are counted too
exclude = []                   # files not counted, e.g. ["frontmatter/*", "appendix*.tex"]
follow_inputs = true           # false: count only the files matched by `include`
{pdf:<31}# PDF for the page count, when --pdf isn't given

[words]
headers = false                # also count words in \\section{{...}} etc.
captions = false               # also count words in figure and table captions
texcount = "texcount"          # path to texcount, if it isn't on PATH
texcount_args = []             # extra texcount arguments, e.g. ["-incbib"]

[pages]
start_label = ""               # start at the page numbered this, e.g. "1" ("" = first page of the PDF)
end_bookmarks = []             # stop before the bookmark with this title, e.g. ["References"] ([] = end of PDF)

[output]
csv = "progress/progress.csv"
plot = "progress/progress.png"

[goal]                         # optional
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
        start_label=get("pages", "start_label", str, ""),
        end_bookmarks=get("pages", "end_bookmarks", list, []),
        csv=root / get("output", "csv", str, "progress/progress.csv"),
        plot=root / get("output", "plot", str, "progress/progress.png"),
        goal_words=get("goal", "words", int, None),
        goal_pages=get("goal", "pages", int, None),
        goal_date=get("goal", "date", dt.date, None),
    )
