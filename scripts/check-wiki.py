#!/usr/bin/env python3
"""Refuses a wiki that would mislead its reader.

Run against a clone of the wiki repository:

    ./scripts/check-wiki.py ~/awtrixng-mgr.wiki

What it enforces, and why each rule exists rather than being good taste:

- **Links must be `[Texte](wiki/Page)`.** Gogs resolves relative links against
  the *repository* root, not the wiki's, so `[X](Page)` renders a URL that
  answers 400. Measured, not assumed.
- **No anchors.** Gogs emits no `id` on headings, so `#section` silently drops
  the reader at the top of the page.
- **Images must exist** in docs/screenshots/ **and point at the repository's
  raw URL**. Checking the file name alone is not enough: a page once shipped
  with `{R}/rappels.png`, a placeholder never substituted. The name matched, so
  the check passed, and the wiki showed two broken images for a day.
- **Table rows must agree** on their column count — an unescaped `|` inside a
  cell splits it in two and the table falls apart.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"

#: Where the wiki must fetch its images. The wiki repository cannot serve
#: files, so they live in the main one and are linked by their raw URL.
IMAGE_BASE = "https://gogs.home.lan/fpicard/awtrixng-mgr/raw/master/docs/screenshots/"


def check(wiki: pathlib.Path) -> list[str]:
    pages = {p.stem for p in wiki.glob("*.md")}
    images = {p.name for p in SHOTS.glob("*.png")}
    problems: list[str] = []

    for page in sorted(wiki.glob("*.md")):
        text = page.read_text()

        for label, target in re.findall(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", text):
            if target.startswith(("http", "#")):
                continue
            if not target.startswith("wiki/"):
                problems.append(f"{page.name}: « {label} » -> {target} : écrire wiki/Page")
                continue
            name, _, anchor = target[len("wiki/"):].partition("#")
            if name not in pages:
                problems.append(f"{page.name}: « {label} » -> page absente : {name}")
            if anchor:
                problems.append(
                    f"{page.name}: « {label} » -> ancre #{anchor} : Gogs ne pose pas d'id "
                    "sur les titres, le lecteur atterrirait en haut de page"
                )

        for alt, url in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text):
            if not url.startswith(IMAGE_BASE):
                problems.append(
                    f"{page.name}: image « {alt} » -> {url} : doit commencer par "
                    f"{IMAGE_BASE}"
                )
            elif url[len(IMAGE_BASE):] not in images:
                problems.append(f"{page.name}: image « {alt} » absente de docs/screenshots/")

        rows: list[int] = []
        start = 0
        for number, line in enumerate(text.split("\n"), 1):
            if line.lstrip().startswith("|"):
                if not rows:
                    start = number
                rows.append(line.count("|") - line.count("\\|"))
            elif rows:
                if len(set(rows)) > 1:
                    problems.append(
                        f"{page.name}: tableau ligne {start} : colonnes irrégulières "
                        f"{sorted(set(rows))} — un | non échappé ?"
                    )
                rows = []

    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[0])
        print(f"\nusage : {sys.argv[0]} <clone du wiki>")
        return 2

    wiki = pathlib.Path(sys.argv[1]).expanduser()
    if not wiki.is_dir():
        print(f"{wiki} n'est pas un dossier")
        return 2

    problems = check(wiki)
    pages = len(list(wiki.glob("*.md")))
    if problems:
        print(f"{len(problems)} problème(s) sur {pages} page(s) :\n")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1

    print(f"✓ {pages} pages : liens, images et tableaux conformes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
