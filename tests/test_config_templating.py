"""Tests for the ${VAR} substitution helper used by Phase 2 (api_tool)."""

import pytest

from specops_lib.config.templating import (
    MissingVariableError,
    substitute_vars,
    substitute_vars_in_mapping,
)


class TestSubstituteVars:
    def test_replaces_single_placeholder(self) -> None:
        assert substitute_vars("Bearer ${T}", {"T": "abc"}) == "Bearer abc"

    def test_replaces_multiple(self) -> None:
        result = substitute_vars("${A}-${B}-${A}", {"A": "1", "B": "2"})
        assert result == "1-2-1"

    def test_missing_raises_in_strict(self) -> None:
        with pytest.raises(MissingVariableError):
            substitute_vars("Bearer ${T}", {})

    def test_missing_kept_when_not_strict(self) -> None:
        assert substitute_vars("Bearer ${T}", {}, strict=False) == "Bearer ${T}"

    def test_non_string_returned_as_is(self) -> None:
        assert substitute_vars(123, {"T": "x"}) == 123  # type: ignore[arg-type]

    def test_unicode_values(self) -> None:
        assert substitute_vars("hi ${name}", {"name": "Zürich"}) == "hi Zürich"

    def test_dotted_and_dashed_names(self) -> None:
        assert substitute_vars("${apitool.stripe.KEY}", {"apitool.stripe.KEY": "sk_x"}) == "sk_x"


class TestSubstituteMapping:
    def test_applies_per_value(self) -> None:
        out = substitute_vars_in_mapping(
            {"Authorization": "Bearer ${K}", "X-Trace": "static"},
            {"K": "abc"},
        )
        assert out == {"Authorization": "Bearer abc", "X-Trace": "static"}

    def test_strict_propagates_missing(self) -> None:
        with pytest.raises(MissingVariableError):
            substitute_vars_in_mapping({"H": "${X}"}, {})
