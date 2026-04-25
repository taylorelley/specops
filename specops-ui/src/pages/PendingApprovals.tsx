import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageContainer, PageHeader } from "../components/ui";
import { useExecutionsGlobal, useResolveExecution, useExecutionEvents } from "../lib/queries";
import type { Execution, ExecutionEvent } from "../lib/types";

const css = {
  btn: "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
};

export default function PendingApprovals() {
  const { data, isLoading, refetch } = useExecutionsGlobal("paused");
  const items = data?.executions ?? [];

  return (
    <PageContainer>
      <PageHeader
        title="Pending Approvals"
        description="Executions waiting for a human decision. Approving sends a resume signal to a fresh worker."
      />

      {isLoading && (
        <div className="text-sm text-claude-text-muted py-8 text-center">
          Loading pending approvals…
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="rounded-lg border border-claude-border bg-claude-surface px-4 py-8 text-center text-sm text-claude-text-muted">
          No executions are paused. When an agent hits an escalate guardrail, it will appear here.
        </div>
      )}

      {!isLoading && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((ex) => (
            <PendingRow key={ex.id} ex={ex} onResolved={() => refetch()} />
          ))}
        </ul>
      )}
    </PageContainer>
  );
}

function PendingRow({ ex, onResolved }: { ex: Execution; onResolved: () => void }) {
  const { data: events } = useExecutionEvents(ex.id);
  const resolve = useResolveExecution();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const waiting = useMemo(() => extractLastWaiting(events?.events ?? []), [events]);
  const tool = waiting?.tool_name || "(unknown tool)";
  const reason = waiting?.reason || "(no reason)";
  const guardrail = waiting?.guardrail || "";

  async function decide(decision: "approve" | "reject") {
    setBusy(decision);
    setError(null);
    try {
      await resolve.mutateAsync({ executionId: ex.id, decision, note });
      onResolved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className="rounded-lg border border-claude-border bg-claude-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              to={`/agents/${ex.agent_id}`}
              className="text-xs font-mono text-claude-accent hover:underline truncate"
            >
              {ex.agent_id}
            </Link>
            <span className="rounded px-1.5 py-px text-[10px] bg-claude-input text-claude-text-secondary">
              tool: {tool}
            </span>
            {guardrail && (
              <span className="rounded px-1.5 py-px text-[10px] bg-claude-input text-claude-text-secondary">
                guardrail: {guardrail}
              </span>
            )}
            {ex.channel && (
              <span className="rounded px-1.5 py-px text-[10px] bg-claude-input text-claude-text-secondary">
                {ex.channel}:{ex.chat_id}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-claude-text-primary line-clamp-3">{reason}</p>
          <p className="text-[10px] text-claude-text-muted mt-1">
            paused at {ex.paused_at || ex.updated_at} · execution {ex.id.slice(0, 12)}
          </p>
        </div>
        <div className="flex flex-col gap-1.5 shrink-0">
          <input
            placeholder="optional note"
            className="rounded border border-claude-border bg-claude-input px-2 py-1 text-xs"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={!!busy}
          />
          <div className="flex gap-1.5">
            <button
              onClick={() => decide("approve")}
              disabled={!!busy}
              className={`${css.btn} bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50`}
            >
              {busy === "approve" ? "Approving…" : "Approve"}
            </button>
            <button
              onClick={() => decide("reject")}
              disabled={!!busy}
              className={`${css.btn} bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50`}
            >
              {busy === "reject" ? "Rejecting…" : "Reject"}
            </button>
          </div>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
    </li>
  );
}

function extractLastWaiting(events: ExecutionEvent[]): {
  tool_name?: string;
  guardrail?: string;
  reason?: string;
} | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev.event_kind !== "hitl_waiting") continue;
    try {
      const payload = ev.payload_json ? JSON.parse(ev.payload_json) : {};
      return {
        tool_name: payload.tool_name ?? ev.tool_name ?? undefined,
        guardrail: payload.guardrail ?? undefined,
        reason: payload.reason ?? undefined,
      };
    } catch {
      return { tool_name: ev.tool_name ?? undefined };
    }
  }
  return null;
}
