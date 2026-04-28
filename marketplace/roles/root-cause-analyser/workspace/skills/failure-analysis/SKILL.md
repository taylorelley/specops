---
name: failure-analysis
description: "Techniques for analysing failure patterns, recurring incidents, and systemic weaknesses across the organisation."
metadata: {"specialagent":{"emoji":"📊"}}
---

# Failure Analysis

Methods for identifying patterns, systemic weaknesses, and recurring failure modes across incidents.

## Failure Taxonomy

Classify each contributing factor to enable trend analysis:

| Category | Examples |
|----------|---------|
| **Configuration** | Misconfiguration, wrong default, missing parameter |
| **Code defect** | Logic error, race condition, off-by-one, unhandled exception |
| **Dependency** | Third-party outage, API change, library bug |
| **Capacity** | Resource exhaustion (CPU, memory, disk, connections) |
| **Operational** | Incomplete runbook, missed alert, incorrect procedure followed |
| **Change management** | Insufficient testing, missing rollback plan, poor deployment window |
| **Design** | Architectural flaw, missing redundancy, single point of failure |
| **Human factors** | Ambiguous interface, cognitive overload, unclear ownership |

## Trend Analysis Process

Run after every 5 incidents or monthly (whichever comes first):

1. **Aggregate** — Collect all RCA reports from the period
2. **Classify** — Tag each root cause and contributing factor by category
3. **Count** — Identify the most frequent categories and specific failure modes
4. **Rank** — Sort by frequency × severity (use a simple 1–5 scale for each)
5. **Surface** — Write a trend summary with the top 3 systemic risks
6. **Recommend** — Propose cross-cutting corrective actions (not incident-specific ones)

## Failure Mode and Effects Analysis (FMEA)

Proactive technique to identify what could go wrong before it does.

```
| Component | Failure Mode | Effect | Severity (1-10) | Likelihood (1-10) | Detectability (1-10) | RPN | Action |
|-----------|-------------|--------|-----------------|-------------------|---------------------|-----|--------|
| [Component] | [How it fails] | [Impact] | [S] | [L] | [D] | S×L×D | [Mitigation] |
```

**RPN (Risk Priority Number)** = Severity × Likelihood × Detectability  
Focus corrective actions on items with RPN > 100 or Severity ≥ 8.

## Common Failure Patterns to Watch For

- **Alert fatigue** — Too many low-quality alerts causing real ones to be missed
- **Cascade failures** — One component's failure overloading others
- **Toil accumulation** — Manual workarounds masking underlying defects
- **Knowledge silos** — Only one person understands a critical system
- **Deferred risk** — Known issues tracked but never prioritised
- **Normalization of deviance** — Accepting degraded state as normal over time

## Evidence Quality Assessment

Rate the reliability of each piece of evidence:

| Quality | Description |
|---------|-------------|
| **High** | Automated logs, metrics, or monitoring data with timestamps |
| **Medium** | Human accounts corroborated by at least one other source |
| **Low** | Single-source human account or reconstructed from memory |

Always note evidence quality in the RCA report and distinguish between confirmed facts and inferences.
