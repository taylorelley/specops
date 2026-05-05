"""Shared utility for building per-agent plan context messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from specops.core.domain.plan import PlanDef


def build_plan_context_message(plan: PlanDef, agent_id: str = "") -> str:
    """Build a per-agent text message describing the plan and the agent's specific tasks."""
    my_tasks = [t for t in plan.tasks if t.agent_id == agent_id] if agent_id else []

    lines = [
        f"# Plan: {plan.name}",
        f"Plan ID: `{plan.id}`",
        f"Status: {plan.status}",
        "",
        plan.description or "(No description)",
        "",
        "## Plan-scoped conversation",
        "This thread is for this plan. Full history is here. Use get_plan(plan_id) for full board if needed.",
        "",
    ]

    if agent_id:
        lines.extend(
            [
                "## Your assigned tasks",
                f"You have **{len(my_tasks)}** task(s) assigned to you on this plan.",
                "**Work ONLY on tasks assigned to you.** Do not pick up or execute tasks assigned to other agents.",
                "",
            ]
        )
        if my_tasks:
            for t in sorted(my_tasks, key=lambda t: t.position):
                col_label = (
                    "Todo"
                    if t.column_id.endswith("col-todo")
                    else "In Progress"
                    if t.column_id.endswith("col-in-progress")
                    else "Done"
                    if t.column_id.endswith("col-done")
                    else "Blocked"
                    if t.column_id.endswith("col-blocked")
                    else t.column_id
                )
                lines.append(f"- **[{t.id}]** {t.title} (status: {col_label})")
                if t.description:
                    lines.append(f"  {t.description}")
            lines.append("")
        else:
            lines.append(
                "No tasks are currently assigned to you. Check back after the plan creator assigns work."
            )
            lines.append("")

    lines.append("## Full plan board")
    for col in sorted(plan.columns, key=lambda c: c.position):
        lines.append(f"\n### {col.title}")
        tasks_in_col = [t for t in plan.tasks if t.column_id == col.id]
        for t in sorted(tasks_in_col, key=lambda t: t.position):
            assigned_marker = " ← **YOUR TASK**" if t.agent_id == agent_id and agent_id else ""
            agent_label = f" (agent: {t.agent_id})" if t.agent_id else " (unassigned)"
            desc = (
                f": {t.description[:80]}..."
                if t.description and len(t.description) > 80
                else (f": {t.description}" if t.description else "")
            )
            lines.append(f"- Task ID `{t.id}`: {t.title}{agent_label}{assigned_marker}{desc}")

    lines.extend(
        [
            "",
            "## Your role",
            "You are one of the agents assigned to this plan.",
            "",
            "**You CAN:** update your own tasks (move between columns, edit title/description), assign tasks to yourself, add and read artifacts, add comments, activate plans you are assigned to.",
            "",
            "**You CANNOT:** move tasks that are assigned to other agents, pause or deactivate plans (admin only), add or remove agents from the plan (admin only), delete plans or tasks or artifacts.",
            "",
            "## Communication",
            "Use `add_task_comment` for all updates — status, blockers, handoffs. Use @agent_name to notify. Call `list_task_comments` before starting. Use `a2a_call` only for urgent real-time coordination.",
            "",
            "## Artifacts",
            "Task deliverable: `add_plan_artifact(plan_id, name, content, task_id=task_id)`. Shared report: omit task_id. Use clear filenames (e.g. report.md).",
            "",
        ]
    )
    if plan.status == "paused":
        lines.extend(
            [
                "**This plan is currently PAUSED by admin.** Do not create or update tasks on it. Wait for admin to re-activate the plan.",
                "",
            ]
        )
    elif plan.status == "active" and my_tasks:
        lines.extend(
            [
                "## 🚀 Action required",
                "The plan is **active**. You have tasks assigned to you — **start working on them now.**",
                "Tasks follow: Context, Requirements, Definition of Done, Output. Report per the Output section (add_task_comment, add_plan_artifact).",
                "1. Move your task(s) to **In Progress** using `update_plan_task(plan_id, task_id, column_id='col-in-progress')`.",
                "2. Do the actual work described in each task.",
                "3. Save any output using `add_plan_artifact(plan_id, name, content, task_id=task_id)`. Use a `.md` filename (e.g. `report.md`) for text outputs so they render as Markdown in the browser.",
                "4. When done, move the task to **Done** using `update_plan_task(plan_id, task_id, column_id='col-done')`.",
                "5. Add a completion comment with `add_task_comment(plan_id, task_id, content)` summarising what you produced.",
                "",
                "Do NOT wait for further instructions. Start immediately.",
                "",
            ]
        )
    lines.extend(
        [
            "## Plan tools",
            "- list_plan_assignees(plan_id) — list ALL available agents for task assignment (always call this before assigning)",
            "- list_plans() — list all plans (shows status; respect paused plans)",
            "- get_plan(plan_id) — get full plan details with tasks and assignments",
            "- plan_query(plan_id?, assigned_to_me=True) — see only your assigned tasks",
            "- create_plan(name, description?) — create a new plan (you are auto-assigned as coordinator)",
            "- activate_plan(plan_id) — activate plan ONLY after user confirms 'start'; sends tasks to all assigned agents",
            "- create_plan_task(plan_id, title, description) — create an UNASSIGNED task on the plan board",
            "- assign_plan_task(plan_id, task_id, agent_id) — assign a task to any agent, including yourself (use list_plan_assignees first to get valid IDs)",
            "- update_plan_task(plan_id, task_id, column_id?, title?, description?) — update a task's status or content (column_id changes only allowed on tasks assigned to you)",
            "- add_plan_artifact(plan_id, name, content, task_id?) — save outputs or summaries to the plan",
            "- list_plan_artifacts(plan_id, task_id?) — list all artifacts in a plan (optionally filtered by task)",
            "- get_plan_artifact(plan_id, artifact_id) — download and read artifact content",
            "- add_task_comment(plan_id, task_id, content) — PRIMARY way to communicate; use @agent_name to notify specific agents",
            "- list_task_comments(plan_id, task_id) — read comments on a task (check this before starting work)",
            "- a2a_discover() — list agents in your team for direct messaging (requires same team; may return empty)",
            "- a2a_call(target_agent_id, message) — send direct real-time message to another agent (use comments for async)",
        ]
    )
    return "\n".join(lines)
