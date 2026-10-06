#!/usr/bin/env python3
"""Refuses a manual that would mislead its reader.

    ./scripts/check-manual.py

The manual lives in `docs/manuel/` and travels with the code, so every link
and every image is a path that either resolves or does not. This checks that
it does.

It used to check a Gogs wiki, where the rules were the opposite — links had to
be absolute because Gogs resolved relative ones against the wrong root, and
images had to carry a raw URL because a wiki repository cannot serve files.
Moving the manual into the repository removed both constraints, and with them
a whole family of ways to be wrong.

What is enforced, and why each rule exists rather than being good taste:

- **Links must resolve to a file.** A manual read in a fork, offline, or from
  a file browser has no server to paper over a wrong path.
- **Images must exist.** Checking the file name alone was once not enough: a
  page shipped with `{R}/rappels.png`, a placeholder never substituted. The
  name matched, the check passed, and two images were broken for a day.
- **No link may leave for a host the reader cannot reach.** The manual
  referenced a private Gogs for months; from outside it was a dead end.
- **Table rows must agree** on their column count — an unescaped `|` inside a
  cell splits it in two and the table falls apart.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "manuel"

#: Hosts that only exist on the author's network. A manual that sends its
#: reader to one of these has sent them nowhere.
PRIVATE = ("gogs.home.lan", "docker-vm", ".home.lan")


def check(manual: pathlib.Path) -> list[str]:
    problems: list[str] = []

    for page in sorted(manual.glob("*.md")):
        text = page.read_text(encoding="utf-8")

        for label, target in re.findall(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", text):
            if target.startswith("#"):
                continue
            if target.startswith("http"):
                for host in PRIVATE:
                    if host in target:
                        problems.append(
                            f"{page.name}: « {label} » -> {target} : hôte privé, "
                            "injoignable pour un lecteur extérieur"
                        )
                continue
            path, _, _anchor = target.partition("#")
            if not (page.parent / path).resolve().exists():
                problems.append(f"{page.name}: « {label} » -> cible absente : {target}")

        for alt, url in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text):
            if url.startswith("http"):
                problems.append(
                    f"{page.name}: image « {alt} » -> {url} : une image du manuel "
                    "doit vivre dans le dépôt, pas sur un serveur"
                )
            elif not (page.parent / url).resolve().exists():
                problems.append(f"{page.name}: image « {alt} » absente : {url}")

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
    manual = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else MANUAL
    if not manual.is_dir():
        print(f"{manual} n'est pas un dossier")
        return 2

    problems = check(manual)
    pages = len(list(manual.glob("*.md")))
    if problems:
        print(f"{len(problems)} problème(s) sur {pages} page(s) :\n")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1

    print(f"✓ {pages} pages : liens, images et tableaux conformes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
