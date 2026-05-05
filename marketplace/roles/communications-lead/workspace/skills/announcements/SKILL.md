---
name: announcements
description: "Playbook for planning and shipping internal and external announcements. Use for product launches, milestone updates, executive changes, and embargoed news."
metadata: {"specialagent":{"emoji":"📣"}}
---

# Announcements

Framework for planning, drafting, and releasing announcements with the right audience, channel, and timing.

## Audience Tiering

Decide who hears what, and in which order, before drafting a single line.

| Tier | Audience | Lead Time | Channel |
|------|----------|-----------|---------|
| **T0** | Founders / exec team | T-7 days | Direct briefing |
| **T1** | Internal staff | T-1 day | All-hands or internal post |
| **T2** | Investors / board | T-1 hour | Email / investor portal |
| **T3** | Customers (selected) | T+0 | Email / in-app banner |
| **T4** | Press & analysts | T+0 to T+1h | Press release, briefings |
| **T5** | General public | T+0 to T+1d | Blog, social, website |

Earlier tiers must always know first. Skipping a tier creates trust debt.

## Channel Selection

- **Email** — Long-form, investor / customer communications, anything that needs to be referenced later.
- **Blog post** — Public narrative, SEO-relevant launches, anchor link for social.
- **Social (X / LinkedIn)** — Short headline + link to anchor content.
- **In-app banner / notification** — Customer-facing product changes that need acknowledgement.
- **Press release** — Material news, partnerships, funding, regulatory.
- **All-hands / internal post** — Anything an employee should not learn from outside first.

## Message Templates

### Product launch

```
Subject: Introducing {Product/Feature} — {one-line value prop}

Today we launched {Product/Feature}.

What it is: {1–2 sentence description}
Why it matters: {customer outcome / pain it removes}
Who it's for: {primary persona}
How to try it: {link / CTA}

For questions: {owner}
```

### Milestone update

```
Subject: {Milestone} — by the numbers

{Headline metric}.

What happened: {short narrative}
What's next: {next 30/60/90 days}
Thanks to: {team / partners}
```

### Executive change

```
Subject: {Name} — {transition}

{Name} is {joining / leaving / moving into} {role}, effective {date}.

Background: {short bio / contribution}
What changes operationally: {who covers what during transition}
Q&A: {forum / owner}
```

## Embargo Handling

- State the embargo time and timezone explicitly (`08:00 PT, 2026-05-12`).
- Share the embargoed material only with parties who have agreed to it.
- Track every recipient and when they were briefed.
- Have a break-glass plan if the embargo leaks: pre-written statement + acceleration of public release.

## Sign-off Checklist

Before any public announcement goes out:

- [ ] Facts and metrics verified by source owner
- [ ] Legal review for material claims (Legal Counsel)
- [ ] Technical accuracy reviewed (CTO / SRE / engineer-on-record)
- [ ] Brand voice and terminology check
- [ ] All audience tiers scheduled in correct order
- [ ] Owner identified for incoming questions
- [ ] Rollback / correction plan drafted

## Anti-Patterns

- Drafting the public post first and reverse-engineering the internal note from it.
- Over-promising future capability ("coming soon", "by end of quarter") without commitment.
- Letting customers learn material news from press before in-app channels.
- Embargo lists with more than ~10 external parties — leakage risk grows fast.
