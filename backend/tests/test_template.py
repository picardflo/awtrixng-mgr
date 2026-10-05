"""The template engine is the security brick of §12: it must substitute, and
do strictly nothing else."""

import pytest

from app.widgets.template import render, variables_used

VALUES = {
    "host": "plex",
    "value": 76.4,
    "unit": "%",
    "title": "Dune Part Two",
    "empty": "",
    "nothing": None,
    "count": 3,
}


def r(template: str) -> str:
    return render(template, VALUES)


class TestSubstitution:
    def test_plain_text_is_untouched(self):
        assert r("Zabbix OK") == "Zabbix OK"

    def test_single_variable(self):
        assert r("{{ host }}") == "plex"

    def test_mixed_text_and_variables(self):
        assert r("{{ host }} CPU {{ value }}{{ unit }}") == "plex CPU 76.4%"

    def test_same_variable_twice(self):
        assert r("{{ host }}/{{ host }}") == "plex/plex"

    def test_whitespace_inside_braces_is_optional(self):
        assert r("{{host}}") == r("{{ host }}") == "plex"

    def test_unknown_variable_becomes_empty(self):
        assert r("[{{ nope }}]") == "[]"

    def test_none_becomes_empty(self):
        assert r("[{{ nothing }}]") == "[]"


class TestFilters:
    @pytest.mark.parametrize(
        ("template", "expected"),
        [
            ("{{ value | round }}", "76"),
            ("{{ value | round(1) }}", "76.4"),
            ("{{ value | int }}", "76"),
            ("{{ host | upper }}", "PLEX"),
            ("{{ host | lower }}", "plex"),
            ("{{ title | truncate(4) }}", "Dune"),
            ("{{ count | pad(3) }}", "  3"),
            ("{{ nothing | default(n/a) }}", "n/a"),
            ("{{ empty | default(n/a) }}", "n/a"),
            ("{{ host | default(n/a) }}", "plex"),
        ],
    )
    def test_filter(self, template, expected):
        assert r(template) == expected

    def test_filters_chain_left_to_right(self):
        assert r("{{ title | upper | truncate(4) }}") == "DUNE"

    def test_filter_on_wrong_type_leaves_value_alone(self):
        assert r("{{ host | round }}") == "plex"

    def test_unknown_filter_leaves_value_alone(self):
        assert r("{{ host | frobnicate }}") == "plex"

    def test_negative_numbers(self):
        assert render("{{ v | abs }}", {"v": -12.5}) == "12.5"


class TestSafety:
    """Nothing here must ever evaluate, import, or reach an attribute."""

    @pytest.mark.parametrize(
        "template",
        [
            "{{ __import__('os').system('rm -rf /') }}",
            "{{ ''.__class__.__mro__ }}",
            "{{ host.__class__ }}",
            "{{ config['SECRET'] }}",
            "{{ 7*7 }}",
            "{{ self }}",
            "{{ request.application }}",
            "{{ host | __class__ }}",
        ],
    )
    def test_dangerous_expressions_render_empty_or_inert(self, template):
        result = render(template, VALUES | {"config": {"SECRET": "leak"}})
        assert "leak" not in result
        assert "49" not in result
        assert "class" not in result.lower()

    def test_never_raises_on_garbage(self):
        for template in ["{{", "}}", "{{ }}", "{{ | }}", "{{ a | b( }}", "{{{{ }}}}"]:
            render(template, VALUES)  # must not raise

    def test_values_are_never_executed(self):
        # A value that looks like code stays a string.
        assert render("{{ v }}", {"v": "{{ host }}"}) == "{{ host }}"


class TestVariablesUsed:
    def test_lists_referenced_names(self):
        assert variables_used("{{ host }} {{ value | round }}") == {"host", "value"}

    def test_ignores_invalid_names(self):
        assert variables_used("{{ 7*7 }} {{ host }}") == {"host"}

    def test_empty_template(self):
        assert variables_used("no variables") == set()


class TestDuration:
    """Seconds are not readable on a 32-pixel matrix."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (45, "45S"),
            (60, "1M"),
            (900, "15M"),
            (3600, "1H00"),
            (31863, "8H51"),
            (86400, "1D00"),
            (190000, "2D04"),
            (0, "0S"),
        ],
    )
    def test_formats(self, seconds, expected):
        assert render("{{ v | duration }}", {"v": seconds}) == expected

    def test_a_non_number_is_left_alone(self):
        assert render("{{ v | duration }}", {"v": "soon"}) == "soon"

    def test_a_negative_value_is_left_alone(self):
        assert render("{{ v | duration }}", {"v": -5}) == "-5"

    def test_missing_value_stays_empty(self):
        assert render("{{ nope | duration }}", {}) == ""

    def test_it_stays_short_enough_for_the_matrix(self):
        """The whole point: it must fit next to an icon."""
        for seconds in (59, 3599, 86399, 999999):
            assert len(render("{{ v | duration }}", {"v": seconds})) <= 5
