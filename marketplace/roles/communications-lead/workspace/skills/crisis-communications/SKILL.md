---
name: crisis-communications
description: "Framework for responding to incidents, outages, security events, and reputational crises. Use when something has gone visibly wrong and external communication is required."
metadata: {"specialagent":{"emoji":"🆘"}}
---

# Crisis Communications

Coordinate the company's voice during incidents, outages, security events, and reputational crises. Pair with the SRE and Root Cause Analyser roles for technical truth.

## Crisis Tiers

| Tier | Trigger | First public statement | Owner |
|------|---------|-------------------------|-------|
| **C1 — Existential** | Data breach, fatality, regulator action, financial fraud | < 1 hour | CEO + Comms Lead + Legal |
| **C2 — Major** | SEV1 outage > 30 min, executive misconduct, viral negative story | < 2 hours | Comms Lead + relevant exec |
| **C3 — Contained** | SEV2 outage, customer data anomaly (not breach), single negative post | < 4 hours | Comms Lead |
| **C4 — Minor** | SEV3, isolated customer complaint, minor factual error | < 1 business day | Owning function |

## First-30-Minutes Checklist

- [ ] Convene crisis room: CEO (if C1/C2), Comms Lead, Legal, technical lead, owning exec
- [ ] Confirm facts: what is actually true vs assumed
- [ ] Identify affected parties and rough scale
- [ ] Lock down who speaks publicly (designate one spokesperson)
- [ ] Draft holding statement
- [ ] Pause scheduled marketing / social posts
- [ ] Brief frontline (support, sales) with approved talking points
- [ ] Open status page entry if applicable

## Holding Statement Template

```
We're aware of {situation in plain language}.

We're investigating and {what we're doing right now}.

{If known: scope of impact and who is affected.}

We will share an update by {time}.

For the latest information: {status page / channel}.
```

Rules: do not speculate on cause, do not name a fix you haven't shipped, do not minimize.

## Spokesperson Rotation

- One designated spokesperson per channel (press / social / customer email).
- Backup spokesperson named in case the primary is unavailable or compromised.
- Everyone else routes inquiries to the spokesperson — no freelancing.
- Briefing pack updated before each public touchpoint with current facts.

## Update Cadence

- C1/C2: minimum every 60 minutes until resolved or downgraded
- C3: every 2–4 hours
- C4: at start, at fix, at postmortem

Silence reads as guilt or chaos. If there's nothing new, say so.

## Do / Don't

**Do:**
- Lead with what affected users care about (impact, what they should do)
- Acknowledge what you don't yet know
- Use short, calm, factual sentences
- Coordinate with Legal Counsel before any statement on liability or cause
- Pair with Customer Support Lead for direct customer outreach

**Don't:**
- Speculate on root cause before Root Cause Analyser confirms
- Blame third parties prematurely
- Promise dates or compensation without owner sign-off
- Delete posts or revise statements without a public correction note
- Let Marketing campaigns run as if nothing is happening

## Post-Crisis Review

Within 5 business days of resolution:

- Timeline of communications (what we said, when, on which channel)
- Audiences reached vs intended
- What we got right
- What we got wrong (factual errors, missed audiences, late updates)
- Trust impact (customer churn, press sentiment, investor reaction)
- Action items: process changes, template fixes, training needs

Pair this with the technical postmortem from the Root Cause Analyser so technical and reputational learning land together.
