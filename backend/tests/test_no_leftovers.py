"""Nothing should still carry the previous project's name.

This port copied a great deal of awtrixhub, and a global rename catches most
of it. What it does not catch is the handful of places where the name is
*data* rather than an identifier — a string shown on a page, the name of a
cookie — because nothing fails when they are wrong.

Two got through and neither was found by a test:

- the dashboard's matrix banner read "AWTRIXHUB READY", which Florian saw in
  his browser before anyone here did;
- the session cookie was `awtrixhub_session`. The two applications can run
  behind the same Caddy, so a shared cookie name means signing into one signs
  you out of the other — and the symptom points at nothing.

The migration's docstring is excluded: it talks about awtrixhub on purpose.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Where the old name is legitimate, because the text is *about* that project.
ALLOWED = {
    ROOT / "backend" / "app" / "db" / "migrations",
    ROOT / "backend" / "tests" / "test_no_leftovers.py",
    ROOT / "CHANGELOG.md",
    ROOT / "README.md",
    ROOT / "docs",
}

SOURCES = [
    (ROOT / "backend" / "app", ("*.py",)),
    (ROOT / "frontend" / "src", ("*.ts", "*.tsx")),
]


def files() -> list[Path]:
    found: list[Path] = []
    for root, patterns in SOURCES:
        for pattern in patterns:
            found += [
                path
                for path in root.rglob(pattern)
                if not any(allowed in path.parents or allowed == path for allowed in ALLOWED)
            ]
    return found


@pytest.mark.parametrize("name", ["awtrixhub", "AWTRIXHUB", "Awtrixhub"])
def test_the_previous_projects_name_is_gone(name: str):
    guilty = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if name in line
    ]
    assert not guilty, f"{name} still appears in: {', '.join(guilty)}"


def test_the_session_cookie_belongs_to_this_project():
    """Not a style point: both applications may sit behind the same proxy."""
    from app.core.auth import COOKIE_NAME

    assert COOKIE_NAME == "awtrixng_session"
