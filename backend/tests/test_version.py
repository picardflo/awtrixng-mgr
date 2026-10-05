"""The version is written in more than one file. They must agree.

Nothing breaks loudly when they drift: the interface shows one number, the
package declares another, and the mismatch is found months later while trying
to work out which build is actually deployed.
"""

import re
import tomllib
from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parents[2]

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_the_version_looks_like_a_version():
    assert SEMVER.match(__version__), __version__


def test_the_backend_package_agrees():
    data = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text())
    assert data["project"]["version"] == __version__


def test_the_changelog_mentions_it():
    """A released version with no entry is a version nobody can read back."""
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert f"## [{__version__}]" in changelog, f"CHANGELOG.md has no section for {__version__}"
