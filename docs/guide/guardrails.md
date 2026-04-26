# Guardrails

Guardrails are checks that run before or after every tool call, and
after the agent's final reply. They decide what to do when a check
fails:

- **`retry`** — feed the failure message back to the LLM as a hint and
  let it try again (bounded by `max_retries`).
- **`raise`** — abort the step; the user sees the guardrail's reason.
- **`fix`** — replace the offending output with a corrected version
  the guardrail itself supplies.
- **`escalate`** — pause the execution durably for human approval
  (Phase 4 wires the resume side).

This is Phase 3 of the
[Agentspan idea adoption](../adr/0001-agentspan-idea-adoption.md). The
public API (`GuardrailResult`, `OnFail`, `Position`, `@guardrail`,
`RegexGuardrail`, `LLMGuardrail`) is derived from Agentspan and
re-implemented natively in Apache-2.0 Python — see `NOTICE` for the
attribution statement.

## Three kinds of guardrails

### Callable
A plain Python function decorated with `@guardrail`:

```python
from specops_lib.guardrails import GuardrailResult, guardrail

@guardrail(on_fail="raise")
def word_limit(content: str) -> GuardrailResult:
    if len(content.split()) > 500:
        return GuardrailResult(passed=False, message="Output too long, please shorten.")
    return GuardrailResult(passed=True)
```

### Regex
Pattern match in `block` (fail when matched) or `allow` (fail when
not matched) mode:

```python
from specops_lib.guardrails import RegexGuardrail

pii_block = RegexGuardrail(
    r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
    mode="block",
    name="pii_ssn",
    on_fail="fix",  # paired with a fixer to redact, see below
)
```

### LLM judge
Defer the decision to a temperature-0 model call:

```python
from specops_lib.guardrails import LLMGuardrail

policy = "Reject any output that gives medical, legal, or financial advice."
medical_advice_judge = LLMGuardrail(policy, judge=my_judge_fn, on_fail="raise")
```

The `judge` callable receives `(system_prompt, user_prompt)` and
returns the model's raw response. The guardrail expects the response
to be a JSON object: `{"passed": bool, "reason": str, "fixed_output": str?}`.
Malformed JSON is treated as failure (the guardrail name and parser
error appear in the journal).

## Where guardrails attach

| Position | Fires at | Configured via |
| --- | --- | --- |
| `tool_input` | Just before a tool dispatches. | Per-tool config (`tools.openapi_tools.<id>.guardrails`, `tools.mcp_servers.<id>.guardrails`) and `tools.guardrails` (applies to every tool). |
| `tool_output` | Just after the tool returns. | Same configs as above. |
| `agent_output` | After the LLM produces a final assistant message. | `agents.defaults.guardrails`. |

A tool-attached guardrail fires at *both* `tool_input` and
`tool_output` by default; the first failure wins. To scope a check to
one position, inspect `context.position` inside a `CallableGuardrail`
and return `passed=True` for the positions you don't care about.

## Configuration

Guardrails are described as `GuardrailRef` objects in YAML or JSON:

```yaml
agents:
  defaults:
    guardrails:
      - name: word_limit          # references a registered guardrail
        on_fail: retry
        max_retries: 2

tools:
  guardrails:                     # applies to every tool
    - name: pii_ssn
      on_fail: fix

  openapi_tools:
    stripe:
      spec_url: https://api.stripe.com/openapi.json
      guardrails:
        - pattern: "POST.*charges"     # inline RegexGuardrail
          regex_mode: block
          on_fail: escalate            # pause for approval
          name: stripe_charges_gate
```

Resolution order for each `GuardrailRef`:

1. If `name` matches a registered guardrail in the runtime registry,
   that wins (with `on_fail` / `max_retries` overrides applied).
2. Otherwise, if `pattern` is set, an inline `RegexGuardrail` is
   built.
3. Otherwise, if `prompt` is set, an inline `LLMGuardrail` is built
   (when a judge is available).
4. Otherwise, the ref is logged and skipped.

## On-fail semantics

When a guardrail fails, the agent loop returns one of these
synthetic markers in the tool result the LLM sees:

- `[GUARDRAIL retry on <position>: <name>] <message>` — feed back to
  the LLM. Counter increments per `(step, guardrail)`; once the
  counter reaches `max_retries` the runner upgrades to `raise`.
- `[GUARDRAIL raise on <position>: <name>] <message>` — the LLM sees
  the error and replies to the user.
- `replace` outcomes substitute the content silently; the LLM sees
  the corrected value, no marker.
- `[GUARDRAIL escalate on <position>: <name>] <reason>` — emits a
  `hitl_waiting` event into the durable journal. Phase 4 wires the
  resume side; for Phase 3 the LLM sees the marker and explains to
  the user that approval is pending.

Every decision (pass or fail) emits a `guardrail_result` event into
the durable execution journal so you can audit who blocked what and
why.

## Backwards compatibility

The existing `ToolApprovalConfig` (the in-channel
"yes/no" approval prompt) keeps working. At agent start a synthesiser
maps each `ask_before_run` tool entry to an `escalate` guardrail named
`legacy_approval`. The YAML schema is unchanged; existing roles in
`marketplace/roles/` continue to load.

When Phase 4 lands, the in-memory `asyncio.Future` queue inside
`ToolApprovalManager` will be replaced with the journal-backed
resume; user behaviour stays identical.

## Limitations / follow-ups

- `Tool.guardrails` (class-level defaults on a `Tool` subclass) is
  declared on the base class but not yet resolved into guardrail
  instances at registration time — Phase 3 ships with config-driven
  attachment only. Tool authors who want a hard-coded default check
  should register a guardrail at module import via
  `default_registry().register(...)` and reference it from agent YAML.
- The Tools tab UI lists configured guardrails but doesn't yet let
  you add or edit them; use the YAML config or the API for now.
- LLM-judge guardrails currently use the agent's main provider via
  the runner-injected judge callable. A separate "judge provider"
  knob (cost control / model isolation) is a Phase 4+ follow-up.
