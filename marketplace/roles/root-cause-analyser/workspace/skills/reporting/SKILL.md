---
name: reporting
description: "Templates and standards for producing clear, actionable RCA reports and incident summaries."
metadata: {"specialagent":{"emoji":"📝"}}
---

# RCA Reporting

Standards and templates for producing root cause analysis documents.

## RCA Report Template

```markdown
# RCA: [Incident Title] — [Date]

## Summary

| Field | Value |
|-------|-------|
| Severity | SEV[1–4] |
| Duration | [Start] → [End] ([total duration]) |
| Impact | [Users / services / data affected] |
| Status | [Resolved / Monitoring / Action items pending] |

## Timeline

| Time (UTC) | Event | Source |
|-----------|-------|--------|
| [Time] | [What happened] | [Log / alert / witness] |
| [Time] | [What happened] | [Log / alert / witness] |

## Root Cause

[One clear paragraph identifying the fundamental cause. Use "The root cause was..." to be explicit.]

## Contributing Factors

- [Factor 1] — [How it contributed]
- [Factor 2] — [How it contributed]

## What Went Well

- [Detection was fast / runbook was followed / communication was clear]

## What Went Poorly

- [Detection was slow / alert was misconfigured / runbook was missing a step]

## Action Items

| Action | Owner | Due Date | Type |
|--------|-------|----------|------|
| [Action] | [Team/Agent] | [Date] | Corrective / Preventive |
| [Action] | [Team/Agent] | [Date] | Corrective / Preventive |

## Appendix

[Links to logs, dashboards, monitoring screenshots, or supporting data]
```

## Writing Standards

- **Plain language** — Write for an audience unfamiliar with the system
- **Past tense** — Describe what happened, not what happens
- **Active voice** — "The service rejected requests" not "Requests were rejected"
- **No blame** — Name systems and processes, not individuals
- **Distinguish facts from inferences** — Mark inferences clearly ("We believe...", "Evidence suggests...")
- **Quantify impact** — Use numbers (users affected, revenue impact, downtime in minutes) not vague terms like "significant"

## Action Item Quality Checklist

Each action item must be:

- [ ] **Specific** — Describes exactly what will be done, not a vague intention
- [ ] **Assigned** — Has a named owner (team or agent)
- [ ] **Time-bound** — Has a due date
- [ ] **Typed** — Classified as Corrective (fixes this specific failure) or Preventive (reduces future risk)
- [ ] **Trackable** — Can be verified as complete or incomplete

## Distribution

| Audience | Content | Timing |
|----------|---------|--------|
| Internal (all staff) | Full RCA | Within 48 hours of resolution |
| Leadership | Executive summary (1 page) | Within 24 hours of resolution |
| Customers (SEV1/SEV2) | Sanitised summary (no internal detail) | Within 48 hours; coordinated with Communications Lead |
| Partners (if affected) | Impact summary + resolution confirmation | Within 48 hours; coordinated with Communications Lead |

## Action Item Follow-Up

Track open action items in `memory/MEMORY.md`. At the start of each week:
1. Review all open items
2. Confirm owners are on track
3. Escalate overdue items to the relevant team lead
4. Mark completed items with the completion date
