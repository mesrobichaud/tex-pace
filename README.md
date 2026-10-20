# tex-pace

VSCodium and the LaTex Workshop Extension can be useful for writing LaTex documents. For shared projects VSCodium offers the flexibility of working offline with syncing to e.g., OverLeaf using git-integration. This Python package installs separately and integrates with LaTeX Workshop to track the progress of your writing. 

Each time LaTeX Workshop (VSCodium/VSCode) builds the PDF, tex-pace counts the number of words and pages in the PDF and adds them to a CSV log. Currently, a basic visual of progress can be output. 

- **Words**: body text counted by [TeXcount](https://app.uio.no/ifi/texcount/), in the files you choose (and the
  files they `\input` / `\include`). Headings, captions, maths and the bibliography are not counted by default.
- **Pages**: counted from the page labelled "1" (so roman-numbered front matter is skipped) to the page before the
  References/Bibliography bookmark.
- **Goals** (optional): a target word or page count, and a date, give the words per day still needed.

```
$ tex-pace status
  main.tex                       312
  chapters/introduction.tex    3,412
  chapters/methods.tex         5,208
                            --------
  8,932 words (+412 today), goal 80,000: 71,068 to go, 205/day for 346 days
  41 pages (+2 today)
```

## Install

You need Python 3.9 or newer, and `texcount`. 
With TinyTeX or other minimal installs: it needs to be added it with `tlmgr install texcount`. `texcount` comes with the full TeX Live, MacTeX and MiKTeX distributions.


```sh
pip install git+https://github.com/USER/tex-pace
```

The LaTeX Workshop recipe calls it by its full path, so if it's installed in an environment that env doesn't need to be active in VSCodium.

## Set up a LaTeX project

In the project folder (where the main `.tex` file is):

```sh
tex-pace init      # writes tex-pace.toml, counting the main .tex file and everything it includes
tex-pace status    # check which files are counted
```

### Add the LaTeX Workshop recipe

[`examples/latex-workshop-settings.json`](examples/latex-workshop-settings.json) has a recipe that runs latexmk and
then `tex-pace log`. Copy its contents to `settings.json` in VSCodium and replace `/path/to/tex-pace` with the full path of your installed
`tex-pace`, which `tex-pace init` prints, or `which tex-pace` (`where tex-pace` on Windows) finds. 

Put it in one of these places:

- **One project**: `.vscode/settings.json` in the folder you open in VSCodium. That is the top folder of the
  window, which may be a parent of the LaTeX project; a `.vscode` folder further down is ignored. Workspace
  settings apply in every VSCodium profile.
- **A `.code-workspace` file**: inside its `"settings": { ... }` section.
- **Every project**: your user settings (*Preferences: Open User Settings (JSON)*). These belong to the current
  VSCodium profile. In a project without a `tex-pace.toml`, `tex-pace log` only prints a warning, so this is harmless.

If the file already has `latex-workshop.latex.tools` or `latex-workshop.latex.recipes`, merge the entries into those
lists. These settings replace LaTeX Workshop's built-in tools and recipes, and the first recipe is the one used when
you save. Change the latexmk arguments if you build differently (e.g. `-xelatex` or `-lualatex` instead of `-pdf`).

To also redraw the plot after every build, add `"--plot"` to the end of the tex-pace `args`, and open
`tex-pace/progress.png` in a VSCodium tab: it refreshes when the image changes. Or run `tex-pace plot`
whenever you want to see it.

## Configuration

`tex-pace.toml`, in the project folder. Paths are relative to it.

```toml
include = ["main.tex"]          # files to count (globs allowed); their \input/\include/\subfile/\import are followed
exclude = ["frontmatter/*", "appendix*.tex"]   # not counted, and not followed
follow_inputs = true            # false: count only the files matched by `include`
pdf = "main.pdf"                # for the page count when --pdf isn't given

[words]
headers = false                 # also count words in \section{...} etc.
captions = false                # also count words in figure and table captions
texcount = "texcount"           # path to texcount, if it isn't on PATH
texcount_args = []              # extra texcount arguments, e.g. ["-incbib"]

[pages]
start_label = "1"               # first counted page ("" for the first page of the PDF)
end_bookmarks = ["References", "Bibliography"]  # counting stops before the last of these bookmarks

[output]
csv = "tex-pace/progress.csv"
plot = "tex-pace/progress.png"

[goal]
words = 80000
pages = 200
date = 2027-06-01
```

An `exclude` pattern without a `/` matches a file name in any folder (`appendix*` matches `chapters/appendix-a.tex`),
and `.tex` may be left off. A pattern with a `/` matches the whole path from the project folder.

The page count stops at a bibliography bookmark only if the PDF has one: load `hyperref` and put the bibliography in
the table of contents (e.g. `\printbibliography[heading=bibintoc]` with biblatex, or the `tocbibind` package).
Otherwise pages are counted to the end of the PDF.

## Commands

| Command | |
| --- | --- |
| `tex-pace init` | create `tex-pace.toml` (`--main FILE` to choose the main file, `--force` to overwrite) |
| `tex-pace status` | words per file, pages, and progress towards the goals, without logging |
| `tex-pace log` | count and add a row to the log (`--plot` to redraw the plot, `--pdf FILE`) |
| `tex-pace plot` | redraw the plot from the log |

Every command takes `-C DIR` to run on the project in `DIR`; `tex-pace.toml` is looked for there and in its parent
folders.

`tex-pace log` never fails the build: if counting goes wrong it prints a warning (shown in LaTeX Workshop's output)
and exits successfully, so the PDF viewer still refreshes. Use `--strict` to make errors fail instead.

The log has one row per build (`timestamp, commit, words, pages`). `commit` is the short git hash, with `+` if there
are uncommitted changes. A rebuild that changes nothing isn't logged again, and the plot shows the last build of
each day. Commit `tex-pace/` with your project to keep the history, or add it to `.gitignore`.
