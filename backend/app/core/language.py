"""The language of the words awtrixng-mgr puts on a matrix.

Not the same thing as the interface language. That one lives in each browser,
because two people may read the same installation in two languages. What a
clock displays has no browser and no reader to ask: the scheduler pushes at
three in the morning. So it is a setting of the installation.

Only values that are *prose* are translated — a weather condition, a moon
phase. The matching `*_code` variables stay English slugs on purpose: they are
what a template compares against, and a condition that changed name with the
language would silently break every widget on a language switch.
"""

from collections.abc import Mapping

from app.core.config import get_settings

#: What we have translations for. Anything else falls back to English rather
#: than to an empty matrix.
SUPPORTED: tuple[str, ...] = ("en", "fr")


#: What the database says, once read. Projection code runs far from a session
#: — inside a connector, during a push — and opening one per widget to learn a
#: two-letter code would be absurd. Loaded at startup, refreshed when the
#: setting changes.
_chosen: str | None = None


def remember(code: str | None) -> None:
    """Record the stored language, or forget it so the environment wins."""
    global _chosen
    _chosen = _normalise(code) if code else None


def _normalise(code: str | None) -> str:
    cleaned = (code or "en").strip().lower()[:2]
    return cleaned if cleaned in SUPPORTED else "en"


def current() -> str:
    """The language the matrix speaks.

    The stored setting first, then the environment, then English. The
    environment keeps working for an installation that set it there, and
    seeds the setting the first time the application starts.
    """
    if _chosen is not None:
        return _chosen
    return _normalise(get_settings().language)


def localise(translations: Mapping[str, Mapping[str, str]], slug: str, english: str) -> str:
    """The label for `slug` in the display language.

    Falls back to English for an unknown language and for a slug nobody has
    translated yet, so adding a weather code never has to wait for a
    translator.
    """
    return translations.get(current(), {}).get(slug, english)
