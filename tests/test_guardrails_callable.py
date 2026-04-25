"""Tests for the @guardrail decorator and CallableGuardrail."""

from specops_lib.guardrails import (
    CallableGuardrail,
    GuardrailContext,
    GuardrailResult,
    guardrail,
)

_CTX = GuardrailContext(position="tool_output")


class TestGuardrailDecorator:
    def test_bare_decorator_makes_callable_guardrail(self) -> None:
        @guardrail
        def short_only(content: str) -> GuardrailResult:
            return GuardrailResult(passed=len(content) < 100)

        assert isinstance(short_only, CallableGuardrail)
        assert short_only.name == "short_only"
        assert short_only.on_fail == "retry"
        assert short_only.max_retries == 3
        assert short_only.check("hi", _CTX).passed is True

    def test_parameterised_decorator(self) -> None:
        @guardrail(name="custom", on_fail="raise", max_retries=1)
        def reject(_content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="nope")

        assert reject.name == "custom"
        assert reject.on_fail == "raise"
        assert reject.max_retries == 1
        result = reject.check("anything", _CTX)
        assert not result.passed
        assert result.message == "nope"

    def test_callable_passes_content(self) -> None:
        captured: list[str] = []

        @guardrail
        def echo(content: str) -> GuardrailResult:
            captured.append(content)
            return GuardrailResult(passed=True)

        echo.check("hello world", _CTX)
        assert captured == ["hello world"]


class TestGuardrailResult:
    def test_default_message_empty(self) -> None:
        r = GuardrailResult(passed=True)
        assert r.message == ""
        assert r.fixed_output is None

    def test_fixed_output_optional(self) -> None:
        r = GuardrailResult(passed=False, message="fix me", fixed_output="corrected")
        assert r.fixed_output == "corrected"
