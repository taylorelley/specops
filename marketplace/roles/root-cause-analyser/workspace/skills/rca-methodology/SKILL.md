---
name: rca-methodology
description: "Structured root cause analysis techniques: 5-whys, fishbone, fault-tree, and causal graphs. Use when investigating incidents, recurring bugs, or systemic failures."
metadata: {"specialagent":{"emoji":"🔍"}}
---

# Root Cause Analysis Methodology

Choose the right technique for the failure you're investigating. The goal is durable understanding, not the appearance of investigation.

## Choosing a Technique

| Technique | Best for | Time | Output |
|-----------|----------|------|--------|
| **5-whys** | Single, linear failure with one obvious symptom | 30–60 min | Causal chain |
| **Fishbone (Ishikawa)** | Multi-factor failure, brainstorming with a team | 1–2 hours | Categorized cause map |
| **Fault tree** | Safety-critical or rare failures, quantitative analysis | Half day+ | Logical AND/OR tree |
| **Causal graph** | Complex distributed-system incidents with feedback loops | Half day+ | Directed acyclic graph |
| **Timeline reconstruction** | Any incident — always start here | 30–90 min | Chronological event list |

Always start with a timeline. The technique you layer on top depends on what the timeline reveals.

## 5-Whys

Ask "why" until the answer is a process, design, or systemic factor — not a person.

```
Symptom: API returned 500s for 12 minutes at 14:03 UTC.

Why? — Database connection pool was exhausted.
Why? — A new code path opened connections without closing them on error.
Why? — The error path skipped the `with` block's cleanup.
Why? — The reviewer didn't catch it; there was no test for the error case.
Why? — Our test template doesn't cover error paths by default.

Root cause: Test scaffolding does not require error-path coverage.
Action: Update test template to require error-path tests for new endpoints.
```

Rules:
- Stop when "why" stops producing useful answers, not at exactly five.
- If a "why" produces multiple answers, branch — you have multiple contributing factors.
- "Human error" is never a root cause. Ask why the system allowed the error.

## Fishbone (Ishikawa)

Six standard categories — adapt to your domain:

- **People** — training, fatigue, on-call rotation, ownership clarity
- **Process** — runbooks, change management, review gates
- **Tools** — observability, deploy tooling, alerting
- **Code / Design** — architecture, defaults, abstractions
- **Environment** — load, dependencies, third-party services
- **Data** — schema, volume, validation

For each category, list contributing factors. Then mark each as **causal** (removing it would have prevented the incident) or **contributing** (made it worse).

## Fault Tree

Top event → AND/OR gates → basic events.

```
                Service unavailable
                       |
                      OR
                  /        \
        DB unreachable    All replicas down
              |                 |
             OR                AND
           /    \           /        \
      Network  DB crash  Replica1   Replica2
       fault              down       down
```

Use when you need to ask: what would have to fail for this to recur? AND gates are your defenses; OR gates are your single points of failure.

## Causal Graph

For distributed systems with feedback loops, draw a graph where nodes are state changes and edges are "caused" relationships. Cycles indicate amplification (e.g. retries → load → timeouts → more retries).

## Bias Guards

- **Hindsight bias** — "Of course that would fail" is hindsight. Ask: with the information available at the time, was the decision reasonable?
- **Fundamental attribution error** — Don't blame individual judgement when most people in the same context would have made the same choice.
- **Single root cause fallacy** — Almost every real incident has multiple contributing factors. If you found exactly one cause, look harder.
- **Recency bias** — The most recent change isn't automatically the cause. Verify with evidence.
- **Outcome bias** — A bad outcome doesn't mean the decision was bad; a good outcome doesn't mean the process was good.

## Output Standard

Every RCA produces:

1. A timeline (machine-readable, with timestamps in UTC)
2. The technique(s) used
3. A list of causal factors and contributing factors, each with evidence
4. Action items: owner, due date, type (preventive / detective / response)
5. Confidence level (high / medium / low) for each finding

Hand the output to the postmortem skill for the canonical write-up.
