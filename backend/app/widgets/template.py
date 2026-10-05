"""Tiny template engine for widget text (§12, ADR-006).

No general-purpose engine — not Jinja2, not even its sandbox. A template is a
string typed into a web form; the attack surface of a real engine is not worth
it for substituting a handful of values onto a 32x8 matrix.

Grammar, and nothing else:

    {{ name }}
    {{ name | filter }}
    {{ name | filter(argument) }}
    {{ name | filter | filter }}

No attribute access, no indexing, no arithmetic, no function call outside the
closed whitelist below. Rendering never raises: an unknown variable or a filter
applied to the wrong type yields an empty string, because a broken template
must not take a widget — let alone the scheduler — down.
"""

import re
from collections.abc import Callable, Mapping
from typing import Any

#: Only {{ … }} is significant. Everything else is literal text.
_EXPRESSION = re.compile(r"\{\{([^{}]*)\}\}")

#: A variable name, nothing more. This is what forbids `__class__` and friends.
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: filter or filter(argument)
_FILTER = re.compile(r"^([a-z_]+)(?:\(\s*(.*?)\s*\))?$")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, argument: str | None) -> Any:
    number = _as_float(value)
    if number is None:
        return value
    digits = int(argument) if argument and argument.lstrip("-").isdigit() else 0
    return round(number, digits) if digits > 0 else int(round(number))


def _int(value: Any, _: str | None) -> Any:
    number = _as_float(value)
    return value if number is None else int(number)


def _abs(value: Any, _: str | None) -> Any:
    number = _as_float(value)
    return value if number is None else abs(number)


def _upper(value: Any, _: str | None) -> Any:
    return str(value).upper()


def _lower(value: Any, _: str | None) -> Any:
    return str(value).lower()


def _truncate(value: Any, argument: str | None) -> Any:
    # No ellipsis: on 32 pixels every column counts.
    if not argument or not argument.isdigit():
        return value
    return str(value)[: int(argument)]


def _default(value: Any, argument: str | None) -> Any:
    empty = value is None or (isinstance(value, str) and not value.strip())
    return (argument or "") if empty else value


def _duration(value: Any, _: str | None) -> Any:
    """Seconds into something readable on 32 pixels.

    An uptime of 31863 says nothing; 8H51 says it rebooted this morning. The
    unit is always the largest that fits, so the string stays short.
    """
    seconds = _as_float(value)
    if seconds is None or seconds < 0:
        return value
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}S"
    if seconds < 3600:
        return f"{seconds // 60}M"
    if seconds < 86400:
        return f"{seconds // 3600}H{(seconds % 3600) // 60:02d}"
    return f"{seconds // 86400}D{(seconds % 86400) // 3600:02d}"


def _pad(value: Any, argument: str | None) -> Any:
    if not argument or not argument.isdigit():
        return value
    return str(value).rjust(int(argument))


#: The closed whitelist. Anything outside it is not a filter.
FILTERS: dict[str, Callable[[Any, str | None], Any]] = {
    "round": _round,
    "int": _int,
    "abs": _abs,
    "upper": _upper,
    "lower": _lower,
    "truncate": _truncate,
    "default": _default,
    "pad": _pad,
    "duration": _duration,
}




def for_matrix(text: str) -> str:
    """The boundary with the hardware. It no longer changes anything.

    **On AWTRIX 3 this stripped accents**, because that font had none and
    printed a question mark instead: "décroissante" reached the matrix as
    "d?croissante". Decomposing and dropping the combining marks gave
    "decroissante" — imperfect French, but readable.

    **AWTRIX NG draws them.** Measured on a TC001 by pushing each character on
    its own and comparing the framebuffer against the one "?" produces:
    àâäéèêëîïôöùûüÿç, ÀÂÉÈÊËÎÔÙÛÇ, the ligatures œŒæÆ, and °€µ — every one
    drawn, not one substituted. So the workaround now does harm: it is the
    only reason a French label reached the display misspelt.

    The function stays as the seam. Something will want it again — a firmware
    that drops a character, a panel with a different font — and a boundary
    that exists is easier to use than one that has to be reinvented.
    """
    return text



def render(template: str, values: Mapping[str, Any]) -> str:
    """Substitute {{ … }} in `template` using `values`. Never raises."""
    return _EXPRESSION.sub(lambda match: _render_one(match.group(1), values), template)


def _render_one(expression: str, values: Mapping[str, Any]) -> str:
    parts = [part.strip() for part in expression.split("|")]
    name, filters = parts[0], parts[1:]

    if not _NAME.match(name):
        return ""

    value: Any = values.get(name)
    for specification in filters:
        value = _apply(specification, value)

    return "" if value is None else str(value)


def _apply(specification: str, value: Any) -> Any:
    match = _FILTER.match(specification)
    if not match:
        return value

    name, argument = match.group(1), match.group(2)
    function = FILTERS.get(name)
    if function is None:
        # Unknown filter: leave the value alone rather than guess.
        return value

    try:
        return function(value, argument)
    except Exception:  # noqa: BLE001 - a template must never break a widget
        return value


def variables_used(template: str) -> set[str]:
    """Variable names a template references. Used to warn about typos in the UI."""
    found: set[str] = set()
    for match in _EXPRESSION.finditer(template):
        name = match.group(1).split("|")[0].strip()
        if _NAME.match(name):
            found.add(name)
    return found
