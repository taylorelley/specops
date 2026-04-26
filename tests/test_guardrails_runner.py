"""Tests for GuardrailRunner across the four on_fail modes and three positions.

Exercises the runner directly (no full agent loop) so we can pin the
exact decision/content/message that comes out of each branch.
"""

from typing import Any

import pytest

from specialagent.agent.loop.guardrails import (
    GuardrailRunner,
    resolve_refs,
    synthesize_approval_guardrails,
)
from specops_lib.config.schema import GuardrailRef, ToolApprovalConfig
from specops_lib.guardrails import (
    CallableGuardrail,
    GuardrailContext,
    GuardrailRegistry,
    GuardrailResult,
    RegexGuardrail,
)


def _fail(msg: str = "nope", fixed: str | None = None):
    def _check(_content: str) -> GuardrailResult:
        return GuardrailResult(passed=False, message=msg, fixed_output=fixed)

    return _check


def _pass():
    def _check(_content: str) -> GuardrailResult:
        return GuardrailResult(passed=True)

    return _check


@pytest.fixture
def runner_with_capture():
    events: list[dict] = []

    async def on_event(ev_type: str, channel: str, content: str, **kwargs: Any) -> None:
        events.append({"event_type": ev_type, "content": content, **kwargs})

    return GuardrailRunner(on_event=on_event), events


class TestOnFailRetry:
    async def test_retry_emits_event_and_increments_counter(self, runner_with_capture) -> None:
        runner, events = runner_with_capture
        g = CallableGuardrail(_fail("be shorter"), name="size", on_fail="retry", max_retries=2)
        outcome = await runner.enforce(
            content="long output",
            guardrails=[g],
            position="tool_output",
            execution_id="E1",
            step_id="step:0",
        )
        assert outcome.decision == "retry"
        assert outcome.retry_message == "be shorter"
        assert any(e["event_kind"] == "guardrail_result" for e in events)

    async def test_retry_upgrades_to_raise_when_budget_exhausted(self, runner_with_capture) -> None:
        runner, _ = runner_with_capture
        g = CallableGuardrail(_fail(), name="size", on_fail="retry", max_retries=1)
        first = await runner.enforce(
            content="x",
            guardrails=[g],
            position="tool_output",
            execution_id="E1",
            step_id="step:0",
        )
        assert first.decision == "retry"
        second = await runner.enforce(
            content="x",
            guardrails=[g],
            position="tool_output",
            execution_id="E1",
            step_id="step:0",
        )
        assert second.decision == "raise"
        assert "max_retries" in second.error_message


class TestOnFailRaise:
    async def test_raise_propagates_message(self, runner_with_capture) -> None:
        runner, _ = runner_with_capture
        g = CallableGuardrail(_fail("blocked"), name="block", on_fail="raise")
        outcome = await runner.enforce(
            content="x",
            guardrails=[g],
            position="tool_input",
            execution_id="E1",
            step_id="step:0",
        )
        assert outcome.decision == "raise"
        assert outcome.error_message == "blocked"


class TestOnFailFix:
    async def test_fix_replaces_when_fixed_output_present(self, runner_with_capture) -> None:
        runner, _ = runner_with_capture
        g = CallableGuardrail(
            _fail("redact pls", fixed="[REDACTED]"),
            name="redactor",
            on_fail="fix",
        )
        outcome = await runner.enforce(
            content="ssn=123-45-6789",
            guardrails=[g],
            position="agent_output",
            execution_id="E1",
            step_id="step:0",
        )
        assert outcome.decision == "replace"
        assert outcome.content == "[REDACTED]"

    async def test_fix_without_fixed_output_falls_through_to_raise(
        self, runner_with_capture
    ) -> None:
        runner, _ = runner_with_capture
        g = CallableGuardrail(_fail("nope", fixed=None), name="bad", on_fail="fix")
        outcome = await runner.enforce(
            content="x",
            guardrails=[g],
            position="agent_output",
            execution_id="E1",
            step_id="step:0",
        )
        assert outcome.decision == "raise"
        assert "no fixed_output" in outcome.error_message


class TestOnFailEscalate:
    async def test_escalate_emits_hitl_waiting(self, runner_with_capture) -> None:
        runner, events = runner_with_capture
        g = CallableGuardrail(_fail("needs human"), name="approval", on_fail="escalate")
        outcome = await runner.enforce(
            content="x",
            guardrails=[g],
            position="tool_input",
            tool_name="exec",
            execution_id="E1",
            step_id="step:0",
        )
        assert outcome.decision == "pause"
        assert outcome.pause_payload["guardrail"] == "approval"
        assert outcome.pause_payload["reason"] == "needs human"
        kinds = [e.get("event_kind") for e in events]
        assert "hitl_waiting" in kinds


class TestPositions:
    async def test_each_position_emits_one_event(self, runner_with_capture) -> None:
        runner, events = runner_with_capture
        g = CallableGuardrail(_pass(), name="pass_all")
        for pos in ("tool_input", "tool_output", "agent_output"):
            await runner.enforce(
                content="x",
                guardrails=[g],
                position=pos,  # type: ignore[arg-type]
                execution_id="E1",
                step_id="step:0",
            )
        positions_emitted = [
            e.get("payload_json") for e in events if e.get("event_kind") == "guardrail_result"
        ]
        # Three pass-events with the position embedded in payload_json.
        assert len(positions_emitted) == 3


class TestResolveRefs:
    def test_named_ref_uses_registry(self) -> None:
        registry = GuardrailRegistry()
        registry.register(
            CallableGuardrail(_pass(), name="pii_block", on_fail="raise", max_retries=1)
        )
        refs = [GuardrailRef(name="pii_block", on_fail="retry", max_retries=5)]
        resolved = resolve_refs(refs, registry=registry)
        assert len(resolved) == 1
        # Overrides applied.
        assert resolved[0].on_fail == "retry"
        assert resolved[0].max_retries == 5

    def test_inline_regex_ref(self) -> None:
        refs = [GuardrailRef(name="", pattern=r"secret", on_fail="raise")]
        resolved = resolve_refs(refs, registry=GuardrailRegistry())
        assert len(resolved) == 1
        assert isinstance(resolved[0], RegexGuardrail)
        assert resolved[0].on_fail == "raise"

    def test_unresolvable_ref_dropped(self) -> None:
        refs = [GuardrailRef(name="missing")]
        resolved = resolve_refs(refs, registry=GuardrailRegistry())
        assert resolved == []


class TestSynthesizeApproval:
    def test_per_tool_ask_synthesised(self) -> None:
        cfg = ToolApprovalConfig(
            default_mode="always_run",
            per_tool={"exec": "ask_before_run", "read_file": "always_run"},
        )
        synth = synthesize_approval_guardrails(cfg)
        assert "exec" in synth
        assert synth["exec"][0]["on_fail"] == "escalate"
        assert "read_file" not in synth
        assert "__default__" not in synth

    def test_default_mode_ask_marks_default_key(self) -> None:
        cfg = ToolApprovalConfig(default_mode="ask_before_run", per_tool={})
        synth = synthesize_approval_guardrails(cfg)
        assert "__default__" in synth
        assert synth["__default__"][0]["on_fail"] == "escalate"

    def test_always_run_default_no_synth(self) -> None:
        cfg = ToolApprovalConfig(default_mode="always_run", per_tool={})
        synth = synthesize_approval_guardrails(cfg)
        assert synth == {}


class TestRunnerErrorIsolation:
    async def test_guardrail_exception_treated_as_fail(self, runner_with_capture) -> None:
        runner, _ = runner_with_capture

        class Boom(CallableGuardrail):
            def check(self, content: str, context: GuardrailContext) -> GuardrailResult:
                raise RuntimeError("explode")

        g = Boom(_pass(), name="boom", on_fail="raise")
        outcome = await runner.enforce(
            content="x",
            guardrails=[g],
            position="tool_input",
            execution_id="E1",
            step_id="step:0",
        )
        assert outcome.decision == "raise"
        assert "explode" in outcome.error_message
