"""RegexGuardrail tests: block / allow modes, anchoring, flags."""

import re

from specops_lib.guardrails import GuardrailContext, RegexGuardrail

_CTX = GuardrailContext(position="tool_output")


class TestRegexBlockMode:
    def test_block_fails_on_match(self) -> None:
        g = RegexGuardrail(r"secret", mode="block")
        assert g.check("nothing here", _CTX).passed is True
        result = g.check("password = secret123", _CTX)
        assert result.passed is False
        assert "matched" in result.message

    def test_block_passes_when_no_match(self) -> None:
        g = RegexGuardrail(r"\bAPI_KEY\b", mode="block")
        assert g.check("safe content", _CTX).passed is True


class TestRegexAllowMode:
    def test_allow_fails_when_pattern_missing(self) -> None:
        g = RegexGuardrail(r"^OK:", mode="allow")
        result = g.check("Error: bad", _CTX)
        assert result.passed is False
        assert "did not match" in result.message

    def test_allow_passes_when_pattern_present(self) -> None:
        g = RegexGuardrail(r"^OK:", mode="allow")
        assert g.check("OK: ready", _CTX).passed is True


class TestFlags:
    def test_case_insensitive(self) -> None:
        g = RegexGuardrail(r"PASSWORD", mode="block", flags=re.IGNORECASE)
        assert g.check("My password is x", _CTX).passed is False

    def test_multiline(self) -> None:
        g = RegexGuardrail(r"^STOP$", mode="block", flags=re.MULTILINE)
        assert g.check("line1\nSTOP\nline3", _CTX).passed is False
        assert g.check("line1\nSTOPPED\nline3", _CTX).passed is True


class TestUnicodePatterns:
    def test_unicode_match(self) -> None:
        g = RegexGuardrail(r"Zürich", mode="block")
        assert g.check("located in Zürich", _CTX).passed is False
