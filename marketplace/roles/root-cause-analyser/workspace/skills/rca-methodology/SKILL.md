---
name: rca-methodology
description: "Structured root cause analysis techniques — 5 Whys, fishbone, fault-tree analysis. Use when investigating incidents, failures, or recurring problems."
metadata: {"specialagent":{"emoji":"🔍"}}
---

# RCA Methodology

Structured approaches to identify true root causes, not just symptoms.

## When to Use Each Method

| Method | Best For | Complexity |
|--------|----------|-----------|
| **5 Whys** | Linear cause chains, straightforward incidents | Low |
| **Fishbone (Ishikawa)** | Multi-factor problems, brainstorming contributing causes | Medium |
| **Fault-Tree Analysis (FTA)** | Complex system failures with multiple failure paths | High |
| **Change analysis** | Problems that appeared after a recent change | Low–Medium |

## 5 Whys

Iteratively ask "Why?" until the root cause is reached (typically 3–7 iterations).

**Rules:**
- Each answer becomes the next "why" question
- Stop when you reach a cause that is actionable and systemic
- Don't stop at human error — ask why the human could make that error

**Template:**

```
Problem: [Observable symptom]

Why 1: [First cause]
Why 2: [Cause of Why 1]
Why 3: [Cause of Why 2]
Why 4: [Cause of Why 3]
Why 5: [Root cause — systemic, actionable]

Root cause: [Summary]
Corrective action: [What will fix the root cause]
Preventive action: [What will prevent recurrence]
```

## Fishbone (Ishikawa) Diagram

Organises contributing causes into categories radiating from the problem.

**Standard categories (adapt as needed):**

```
                    PEOPLE          PROCESS
                      \               /
                       \             /
                        [PROBLEM]
                       /             \
                      /               \
                  TECHNOLOGY        ENVIRONMENT
```

**For each category, ask:**
- What in this category could have caused or contributed to the problem?
- Was there a change, gap, or failure in this area?

## Fault-Tree Analysis (FTA)

Top-down deductive analysis: start from the failure event and decompose into contributing conditions using AND/OR logic gates.

```
Top event: [System failure]
│
├── AND gate — all conditions must be true
│   ├── Condition A
│   └── Condition B
│
└── OR gate — any condition is sufficient
    ├── Condition C
    └── Condition D
```

**Steps:**
1. Define the top undesired event
2. Identify immediate causes (AND/OR)
3. Decompose each cause recursively
4. Continue until basic events (hardware faults, human errors, design flaws) are reached
5. Calculate probability if data is available

## Blameless Principles

- Focus on **system conditions** that allowed the failure, not individual mistakes
- Assume good intent — people operate within the systems and processes they are given
- Every finding should link to a **systemic corrective action**, not a personnel action
- Document what would need to change for a different person in the same situation to succeed

## Evidence Collection Checklist

Before starting analysis:

- [ ] Timeline of events (from logs, monitoring, witness accounts)
- [ ] System state at time of failure (configs, versions, recent changes)
- [ ] Alert and metric data bracketing the incident window
- [ ] Change log for the 48–72 hours before the incident
- [ ] Relevant runbooks, procedures, or documentation in effect at the time
- [ ] Statements from involved personnel (what they observed, what they did, what they expected)
