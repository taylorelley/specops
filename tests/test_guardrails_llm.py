"""LLMGuardrail tests with a stub judge — no real LLM call."""

import json

import pytest

from specops_lib.guardrails import GuardrailContext, LLMGuardrail

_CTX = GuardrailContext(position="agent_output")


def _judge_returning(text: str):
    """Build a stub JudgeFn that returns ``text`` regardless of inputs."""

    async def _judge(_system: str, _user: str) -> str:
        return text

    return _judge


def _judge_capturing():
    captured = {"system": None, "user": None}

    async def _judge(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return json.dumps({"passed": True})

    return _judge, captured


class TestLLMGuardrail:
    async def test_passes_when_judge_returns_passed_true(self) -> None:
        g = LLMGuardrail(
            "no PII",
            judge=_judge_returning(json.dumps({"passed": True})),
        )
        result = await g.check_async("Hello world", _CTX)
        assert result.passed is True

    async def test_fails_when_judge_returns_passed_false(self) -> None:
        payload = json.dumps({"passed": False, "reason": "contains PII"})
        g = LLMGuardrail("no PII", judge=_judge_returning(payload))
        result = await g.check_async("My SSN is …", _CTX)
        assert result.passed is False
        assert "PII" in result.message

    async def test_extracts_fixed_output(self) -> None:
        payload = json.dumps({"passed": False, "reason": "redact", "fixed_output": "[REDACTED]"})
        g = LLMGuardrail("no PII", judge=_judge_returning(payload))
        result = await g.check_async("ssn=...", _CTX)
        assert result.fixed_output == "[REDACTED]"

    async def test_tolerates_code_fences(self) -> None:
        payload = "```json\n" + json.dumps({"passed": True}) + "\n```"
        g = LLMGuardrail("policy", judge=_judge_returning(payload))
        assert (await g.check_async("hi", _CTX)).passed is True

    async def test_malformed_json_falls_back_to_fail(self) -> None:
        g = LLMGuardrail("policy", judge=_judge_returning("not json at all"))
        result = await g.check_async("hi", _CTX)
        assert result.passed is False
        assert "unparseable" in result.message.lower()

    async def test_judge_exception_falls_back_to_fail(self) -> None:
        async def _broken(_s: str, _u: str) -> str:
            raise RuntimeError("provider down")

        g = LLMGuardrail("policy", judge=_broken)
        result = await g.check_async("hi", _CTX)
        assert result.passed is False
        assert "errored" in result.message.lower()

    async def test_prompts_concatenate_policy_and_content(self) -> None:
        judge, captured = _judge_capturing()
        g = LLMGuardrail("the policy text", judge=judge)
        await g.check_async("the candidate output", _CTX)
        assert "the policy text" in captured["user"]
        assert "the candidate output" in captured["user"]
        assert "JSON" in captured["system"]

    def test_sync_check_raises(self) -> None:
        g = LLMGuardrail("policy", judge=_judge_returning("{}"))
        with pytest.raises(NotImplementedError):
            g.check("anything", _CTX)
