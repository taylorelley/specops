import { useState } from "react";
import { Link } from "react-router-dom";
import { SpecialAgentIcon } from "../components/SpecialAgentIcon";
import { CHANNEL_DEFS } from "../components/agent-detail/constants";
import { PageHeader, PageContainer, Badge, Button, ListCard, ListItem, PlayIcon, StopIcon, ChevronRightIcon } from "../components/ui";
import { useSpecialAgents, useStartAgent, useStopAgent } from "../lib/queries";
import CreateSpecialAgentModal from "../components/CreateSpecialAgentModal";
import { useAuth } from "../contexts/AuthContext";

const CHANNEL_LABEL_MAP: Record<string, string> = Object.fromEntries(
  CHANNEL_DEFS.map((c) => [c.key, c.label])
);

export default function SpecialAgentsList() {
  const { data: specialagents = [] } = useSpecialAgents();
  const { user } = useAuth();
  const [modalOpen, setModalOpen] = useState(false);
  const startAgent = useStartAgent();
  const stopAgent = useStopAgent();

  return (
    <PageContainer>
      <PageHeader
        title="Special Agents"
        icon={<SpecialAgentIcon className="h-5 w-5" />}
        description="Create and manage your agents."
        action={
          <Button onClick={() => setModalOpen(true)}>
            <SpecialAgentIcon className="mr-1.5 h-4 w-4" color="white" />
            Add Agent
          </Button>
        }
      />

      <ListCard emptyMessage='No agents yet. Click "Add Agent" to create one.'>
        {specialagents.map((specialagent) => {
          const isRunning = specialagent.status === "running";
          const isTransitioning = specialagent.status === "provisioning" || specialagent.status === "connecting";
          const canControl =
            user?.role === "admin" ||
            specialagent.effective_permission === "owner" ||
            specialagent.effective_permission === "manager" ||
            specialagent.effective_permission === "editor";
          return (
            <ListItem
              key={specialagent.id}
              actions={
                <>
                  {specialagent.channels_enabled && specialagent.channels_enabled.length > 0 && (
                    <div className="flex items-center gap-1.5 mr-2">
                      {specialagent.channels_enabled.slice(0, 3).map((ch) => {
                        const label = CHANNEL_LABEL_MAP[ch] || ch;
                        return (
                          <span
                            key={ch}
                            className="rounded px-1.5 py-px text-[10px] font-medium bg-claude-surface text-claude-text-secondary ring-1 ring-claude-border"
                          >
                            {label}
                          </span>
                        );
                      })}
                      {specialagent.channels_enabled.length > 3 && (
                        <span className="text-[10px] text-claude-text-muted">…</span>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-1.5">
                {canControl && isRunning ? (
                  <button
                    onClick={() => stopAgent.mutate(specialagent.id)}
                    disabled={stopAgent.isPending}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-red-600 bg-red-50 dark:bg-red-950/40 ring-1 ring-red-600/20 hover:bg-red-100 dark:bg-red-950/50 transition-colors disabled:opacity-50"
                  >
                    <StopIcon className="h-2.5 w-2.5" />
                    Stop
                  </button>
                ) : isTransitioning ? (
                  <span className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-amber-600 bg-amber-50 dark:bg-amber-950/40 ring-1 ring-amber-600/20 opacity-75">
                    <svg className="h-2.5 w-2.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Starting
                  </span>
                ) : canControl ? (
                  <button
                    onClick={() => startAgent.mutate(specialagent.id)}
                    disabled={startAgent.isPending}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-green-700 bg-green-50 dark:bg-green-950/40 ring-1 ring-green-600/20 hover:bg-green-100 dark:bg-green-950/50 transition-colors disabled:opacity-50"
                  >
                    <PlayIcon className="h-2.5 w-2.5" />
                    Start
                  </button>
                ) : null}
                    <Link
                      to={`/agents/${specialagent.id}`}
                      className="rounded p-1 text-claude-border-strong hover:text-claude-accent hover:bg-claude-surface transition-all"
                    >
                      <ChevronRightIcon className="h-3.5 w-3.5" />
                    </Link>
                  </div>
                </>
              }
            >
              <div
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors"
                style={{
                  backgroundColor: specialagent.color ? `${specialagent.color}18` : undefined,
                }}
              >
                <SpecialAgentIcon className="h-3.5 w-3.5" color={specialagent.color || undefined} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <Link
                    to={`/agents/${specialagent.id}`}
                    className="text-sm font-medium text-claude-text-primary hover:text-claude-accent transition-colors truncate"
                  >
                    {specialagent.name}
                  </Link>
                  <Badge status={specialagent.status} />
                  {specialagent.owner_user_id && user?.id && specialagent.owner_user_id !== user.id && (
                    <span className="rounded px-1.5 py-px text-[10px] font-medium bg-claude-surface text-claude-text-muted ring-1 ring-claude-border">
                      Shared
                    </span>
                  )}
                </div>
              </div>
            </ListItem>
          );
        })}
      </ListCard>

      <CreateSpecialAgentModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </PageContainer>
  );
}
