import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { IoHomeOutline } from "react-icons/io5";
import { useAuth } from "../contexts/AuthContext";
import { useSpecialAgents, usePlans } from "../lib/queries";
import {
  PageHeader,
  PageContainer,
  Card,
  Badge,
  Button,
  ListCard,
  ListItem,
  ChevronRightIcon,
  PlanIcon,
  MarketplaceIcon,
} from "../components/ui";
import { SpecialAgentIcon } from "../components/SpecialAgentIcon";
import CreateSpecialAgentModal from "../components/CreateSpecialAgentModal";
import CreatePlanModal from "../components/CreatePlanModal";

const TOP_N = 5;

function StatTile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card>
      <p className="text-xs text-claude-text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-claude-text-primary">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-claude-text-tertiary">{sub}</p>}
    </Card>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const {
    data: agents = [],
    isLoading: agentsLoading,
    isError: agentsError,
  } = useSpecialAgents();
  const {
    data: plans = [],
    isLoading: plansLoading,
    isError: plansError,
  } = usePlans();
  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [planModalOpen, setPlanModalOpen] = useState(false);

  const userId = user?.id;

  const { stats, topAgents, topPlans } = useMemo(() => {
    const emptyStats = {
      agentsTotal: agents.length,
      agentsRunning: agents.filter((a) => a.status === "running").length,
      plansTotal: plans.length,
      plansActive: plans.filter((p) => p.status === "active").length,
      ownedCount: 0,
      sharedCount: agents.length + plans.length,
    };

    if (!userId) {
      return {
        stats: emptyStats,
        topAgents: agents.slice(0, TOP_N),
        topPlans: plans.slice(0, TOP_N),
      };
    }

    const ownedAgents = agents.filter((a) => a.owner_user_id === userId);
    const sharedAgents = agents.filter((a) => a.owner_user_id !== userId);
    const runningAgents = agents.filter((a) => a.status === "running");

    const ownedPlans = plans.filter((p) => p.owner_user_id === userId);
    const sharedPlans = plans.filter((p) => p.owner_user_id !== userId);
    const activePlans = plans.filter((p) => p.status === "active");

    return {
      stats: {
        agentsTotal: agents.length,
        agentsRunning: runningAgents.length,
        plansTotal: plans.length,
        plansActive: activePlans.length,
        ownedCount: ownedAgents.length + ownedPlans.length,
        sharedCount: sharedAgents.length + sharedPlans.length,
      },
      topAgents: [...ownedAgents, ...sharedAgents].slice(0, TOP_N),
      topPlans: [...ownedPlans, ...sharedPlans].slice(0, TOP_N),
    };
  }, [agents, plans, userId]);

  const agentsPlaceholder = agentsLoading && agents.length === 0;
  const plansPlaceholder = plansLoading && plans.length === 0;
  const showError = agentsError || plansError;

  return (
    <PageContainer>
      <PageHeader
        title={`Welcome back, ${user?.username ?? "there"}`}
        icon={<IoHomeOutline className="h-5 w-5" />}
        description="Your agents and plans at a glance."
      />

      {showError && (
        <Card className="mb-4 text-sm text-red-600 dark:text-red-400">
          Failed to load dashboard data. Try refreshing.
        </Card>
      )}

      <div className="mb-5 flex flex-wrap gap-2">
        <Button onClick={() => setAgentModalOpen(true)}>
          <SpecialAgentIcon className="mr-1.5 h-4 w-4" color="white" />
          New Agent
        </Button>
        <Button variant="secondary" onClick={() => setPlanModalOpen(true)}>
          <PlanIcon className="mr-1.5 h-4 w-4" />
          New Plan
        </Button>
        <Link
          to="/marketplace"
          className="inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium bg-claude-surface text-claude-text-secondary ring-1 ring-claude-border hover:bg-claude-hover transition-colors"
        >
          <MarketplaceIcon className="mr-1.5 h-4 w-4" />
          Browse Marketplace
        </Link>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile
          label="Agents"
          value={agentsPlaceholder ? "—" : stats.agentsTotal}
          sub={agentsPlaceholder ? undefined : `${stats.agentsRunning} running`}
        />
        <StatTile
          label="Plans"
          value={plansPlaceholder ? "—" : stats.plansTotal}
          sub={plansPlaceholder ? undefined : `${stats.plansActive} active`}
        />
        <StatTile
          label="Owned"
          value={agentsPlaceholder || plansPlaceholder ? "—" : stats.ownedCount}
          sub="agents + plans"
        />
        <StatTile
          label="Shared with you"
          value={agentsPlaceholder || plansPlaceholder ? "—" : stats.sharedCount}
          sub="agents + plans"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section>
          <header className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-claude-text-primary">My Agents</h2>
            <Link
              to="/specialagents"
              className="text-xs text-claude-accent hover:underline"
            >
              View all
            </Link>
          </header>
          <ListCard emptyMessage="No agents yet. Create your first agent.">
            {topAgents.map((agent) => {
              const isShared = !!userId && !!agent.owner_user_id && agent.owner_user_id !== userId;
              return (
                <ListItem
                  key={agent.id}
                  actions={
                    <Link
                      to={`/agents/${agent.id}`}
                      className="rounded p-1 text-claude-border-strong transition-all hover:bg-claude-surface hover:text-claude-accent"
                    >
                      <ChevronRightIcon className="h-3.5 w-3.5" />
                    </Link>
                  }
                >
                  <div
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors"
                    style={{
                      backgroundColor: agent.color ? `${agent.color}18` : undefined,
                    }}
                  >
                    <SpecialAgentIcon className="h-3.5 w-3.5" color={agent.color || undefined} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <Link
                        to={`/agents/${agent.id}`}
                        className="truncate text-sm font-medium text-claude-text-primary transition-colors hover:text-claude-accent"
                      >
                        {agent.name}
                      </Link>
                      <Badge status={agent.status} />
                      {isShared && (
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
        </section>

        <section>
          <header className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-claude-text-primary">My Plans</h2>
            <Link to="/plans" className="text-xs text-claude-accent hover:underline">
              View all
            </Link>
          </header>
          <ListCard emptyMessage="No plans yet. Create your first plan.">
            {topPlans.map((plan) => {
              const isShared = !!userId && !!plan.owner_user_id && plan.owner_user_id !== userId;
              return (
                <ListItem
                  key={plan.id}
                  actions={
                    <Link
                      to={`/plans/${plan.id}`}
                      className="rounded p-1 text-claude-border-strong transition-all hover:bg-claude-surface hover:text-claude-accent"
                    >
                      <ChevronRightIcon className="h-3.5 w-3.5" />
                    </Link>
                  }
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-claude-accent/10 text-claude-accent">
                    <PlanIcon className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <Link
                        to={`/plans/${plan.id}`}
                        className="truncate text-sm font-medium text-claude-text-primary transition-colors hover:text-claude-accent"
                      >
                        {plan.name}
                      </Link>
                      <Badge status={plan.status} />
                      {isShared && (
                        <span className="rounded px-1.5 py-px text-[10px] font-medium bg-claude-surface text-claude-text-muted ring-1 ring-claude-border">
                          Shared
                        </span>
                      )}
                    </div>
                    {plan.description ? (
                      <p className="mt-0.5 line-clamp-2 text-xs text-claude-text-muted">
                        {plan.description}
                      </p>
                    ) : null}
                  </div>
                </ListItem>
              );
            })}
          </ListCard>
        </section>
      </div>

      <CreateSpecialAgentModal open={agentModalOpen} onClose={() => setAgentModalOpen(false)} />
      <CreatePlanModal open={planModalOpen} onClose={() => setPlanModalOpen(false)} />
    </PageContainer>
  );
}
