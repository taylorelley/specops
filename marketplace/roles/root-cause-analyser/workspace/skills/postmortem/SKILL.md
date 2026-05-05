---
name: postmortem
description: "Authoring blameless postmortems: timeline, root cause, contributing factors, impact, action items. Use after any SEV1/SEV2 incident or recurring SEV3."
metadata: {"specialagent":{"emoji":"📝"}}
---

# Postmortem

The canonical write-up of an incident. Pairs with the SRE role's incident-response runbook and the rca-methodology skill.

## When to Write One

- Every SEV1 — within 48 hours
- Every SEV2 — within 5 business days
- Recurring SEV3 (3+ times in a rolling quarter) — at the third occurrence
- Any near-miss the team learned something material from

If you're unsure whether to write one, write one. The cost of writing is small.

## Cadence

| Step | Owner | When |
|------|-------|------|
| Draft v1 | Root Cause Analyser | T+24h (SEV1) / T+72h (SEV2) |
| Technical review | SRE + relevant engineers | T+48h / T+5d |
| Action items assigned | Root Cause Analyser | At review |
| Sign-off | CTO (or delegate) | T+72h / T+7d |
| Publish (internal) | Root Cause Analyser | After sign-off |
| Publish (external if customer-facing) | Communications Lead | After sign-off |

## Template

```markdown
# Postmortem: {Incident Name} — {YYYY-MM-DD}

**Severity:** SEV{1–4}
**Status:** Resolved
**Authors:** {names}
**Reviewers:** {names}
**Sign-off:** {name, date}

## Summary

{2–4 sentences: what happened, who was affected, how long, how it was resolved.}

## Impact

- **Duration:** {start UTC} → {end UTC} ({elapsed})
- **Users affected:** {number / percentage / segments}
- **Revenue impact:** {if known, with method}
- **Data impact:** {loss / corruption / exposure — none if none}
- **SLO impact:** {error budget consumed}

## Timeline (UTC)

| Time | Event | Source |
|------|-------|--------|
| {hh:mm} | {what happened} | {alert / dashboard / human report} |
| {hh:mm} | {action taken} | {actor} |

## Root Cause

{The systemic cause — process, design, or defaults. One paragraph, plain language.}

## Contributing Factors

- **{Factor}** — {how it contributed, evidence}
- **{Factor}** — {how it contributed, evidence}

## What Went Well

- {Detection / response / communication strength}
- {Tooling that worked}

## What Went Poorly

- {Gap in detection, response, communication}
- {Tooling that didn't help or hurt}

## Where We Got Lucky

- {Outcomes that could have been worse but weren't, with the lucky factor}

## Action Items

| ID | Action | Type | Owner | Due | Status |
|----|--------|------|-------|-----|--------|
| AI-1 | {action} | preventive | {owner} | {date} | open |
| AI-2 | {action} | detective | {owner} | {date} | open |
| AI-3 | {action} | response | {owner} | {date} | open |

Types: **preventive** (stops recurrence), **detective** (catches it earlier), **response** (reduces blast radius).

## Lessons Learned

- {Durable lesson — true beyond this incident}

## Supporting Material

- Incident channel: {link}
- Dashboards: {links}
- Related postmortems: {links}
```

## Action Item Discipline

- Every action item has a single owner and a real due date — no "team" owners, no "ASAP".
- Track action items in the same system the rest of engineering work lives in.
- Review open action items in a recurring meeting (weekly or fortnightly).
- An action item older than 90 days is itself a finding for the next RCA.

## Blameless Principles

- Use system / process language, not personal: "the deploy tool let through" not "Alex pushed".
- Quote what someone knew at the time, not what is now obvious.
- If a person's name appears, it should be neutral attribution, not assignment of fault.
- Reviewers who feel the need to defend themselves are a signal the document isn't blameless yet — rewrite.

## Anti-Patterns

- "Will be more careful" as an action item.
- Action items that just say "investigate" without a deliverable.
- Postmortems that conclude "human error" — see rca-methodology biases.
- Skipping the "what went well" section — it loses the protective culture.
- Locking the postmortem before action items are tracked elsewhere.
