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
#:
#: The distinction that matters is not "does the word appear" but **"can it
#: run, or can anyone read it"**. A comment saying why a migration disables
#: foreign keys — because awtrixhub lost every widget target that way — is the
#: most valuable line in the file. A label saying it on a page is a defect.
#:
#: So: nothing in an identifier, a string or any executed path, which
#: `test_the_name_never_appears_in_running_code` enforces precisely; and
#: nothing in the interface, which `test_no_user_facing_string…` enforces.
#: Prose explaining the lineage stays.
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


def test_no_user_facing_string_still_says_awtrix_3():
    """The firmware this project does *not* speak.

    Found on a screenshot: testing a connection answered "AWTRIX 3 détecté,
    firmware 1.1.2" — a sentence contradicting itself, and the sort of thing
    only an eye on an image catches. The code comments mention AWTRIX 3 all
    the time and should: they explain what changed. The interface must not.
    """
    import re

    for catalogue in ("fr", "en"):
        path = ROOT / "frontend" / "src" / "i18n" / f"messages.{catalogue}.ts"
        guilty = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if re.search(r'"[^"]*AWTRIX ?3[^"]*"', line)
        ]
        assert not guilty, f"messages.{catalogue}.ts still says AWTRIX 3: {guilty}"


def test_the_name_never_appears_in_running_code():
    """Comments may say it. Code may not.

    Parsed rather than grepped: the file is read as a syntax tree, docstrings
    are dropped, and what is left is what actually runs — identifiers, string
    literals, attribute names. A leftover there is a behaviour; a leftover in
    a comment is a reason.

    This is the rule Florian asked for on 5 October 2026 — "il doit rester 0
    trace" — read the way it is useful: a `secrets.example.md` documenting
    Zabbix and Tautulli was a trace and went; a docstring explaining that
    awtrixhub lost every widget target to a cascading drop is why the
    migration is written as it is.
    """
    import ast

    guilty: list[str] = []
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # Collected by identity, because `ast.walk` descends into an
        # expression statement and would meet the docstring's constant again
        # on the way down. Skipping the statement is not enough — the first
        # version of this test did exactly that and flagged two docstrings.
        docstrings = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }

        for node in ast.walk(tree):
            if id(node) in docstrings:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "awtrixhub" in node.value.lower():
                    guilty.append(f"{path.relative_to(ROOT)}: string {node.value[:60]!r}")
            if isinstance(node, ast.Name) and "awtrixhub" in node.id.lower():
                guilty.append(f"{path.relative_to(ROOT)}: name {node.id}")
            if isinstance(node, ast.Attribute) and "awtrixhub" in node.attr.lower():
                guilty.append(f"{path.relative_to(ROOT)}: attribute {node.attr}")

    assert not guilty, "the previous project's name is in running code: " + "; ".join(guilty)


def test_the_built_interface_carries_no_trace():
    """What is actually served. The only measure that counts for a user."""
    dist = ROOT / "frontend" / "dist"
    if not dist.exists():
        import pytest

        pytest.skip("frontend not built")
    guilty = [
        str(path.relative_to(ROOT))
        for path in dist.rglob("*")
        if path.is_file()
        and path.suffix in {".js", ".css", ".html"}
        and "awtrixhub" in path.read_text(encoding="utf-8", errors="ignore").lower()
    ]
    assert not guilty, f"the built interface still carries it: {guilty}"
