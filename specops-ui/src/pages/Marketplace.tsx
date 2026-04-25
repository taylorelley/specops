import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { PageContainer, PageHeader, PlanIcon, TrashIcon } from "../components/ui";
import { useTemplates, useSearchSkills, useSearchMcpServers, useSoftwareCatalog, useCustomSoftware, useAddCustomSoftware, useUpdateCustomSoftware, useDeleteCustomSoftware, usePlanTemplates, useCustomPlanTemplates, useDeleteCustomPlanTemplate, useCustomSkills, useDeleteCustomSkill, useCustomMcpServers, useDeleteCustomMcpServer, useApiToolsCatalog, useDeleteCustomApiTool } from "../lib/queries";
import CreateSpecialAgentModal from "../components/CreateSpecialAgentModal";
import CreatePlanModal from "../components/CreatePlanModal";
import TemplateDetailModal from "../components/TemplateDetailModal";
import PlanTemplateDetailModal from "../components/PlanTemplateDetailModal";
import AddPlanTemplateModal from "../components/AddPlanTemplateModal";
import AddCustomSkillModal from "../components/AddCustomSkillModal";
import AddCustomMcpModal from "../components/AddCustomMcpModal";
import AddCustomApiToolModal from "../components/AddCustomApiToolModal";
import InstallSkillModal from "../components/InstallSkillModal";
import InstallMcpModal from "../components/InstallMcpModal";
import InstallSoftwareModal from "../components/InstallSoftwareModal";
import InstallApiToolModal from "../components/InstallApiToolModal";
import type { MarketplaceSkill, MCPRegistryServer, SoftwareCatalogEntry, AddCustomSoftwarePayload, PlanTemplate, CustomSkillEntry, CustomMcpEntry, ApiToolEntry } from "../lib/types";
import {
  HiOutlineCommandLine,
  HiOutlineCodeBracket,
  HiOutlineServerStack,
  HiOutlinePresentationChartBar,
  HiOutlineBanknotes,
  HiOutlineUserGroup,
  HiOutlineMegaphone,
  HiOutlineScale,
  HiOutlineChartBar,
  HiOutlineSparkles,
  HiOutlineTrophy,
} from "react-icons/hi2";

type Tab = "templates" | "plan-templates" | "skills" | "mcp" | "software" | "api-tools";

const css = {
  input: "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  btn: "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
};

const TAB_FROM_HASH: Record<string, Tab> = {
  templates: "templates",
  "plan-templates": "plan-templates",
  skills: "skills",
  mcp: "mcp",
  software: "software",
  "api-tools": "api-tools",
};

export default function Marketplace() {
  const [tab, setTab] = useState<Tab>(() => {
    const hash = typeof window !== "undefined" ? window.location.hash.slice(1) : "";
    return TAB_FROM_HASH[hash] ?? "templates";
  });
  const { data: templates = [], isLoading: templatesLoading } = useTemplates();

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.slice(1);
      if (TAB_FROM_HASH[hash]) setTab(TAB_FROM_HASH[hash]);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (window.location.hash.slice(1) !== tab) {
      window.location.hash = tab;
    }
  }, [tab]);

  const tabClass = (t: Tab) =>
    `px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
      tab === t
        ? "bg-claude-input text-claude-text-primary shadow-sm"
        : "text-claude-text-muted hover:text-claude-text-secondary"
    }`;

  return (
    <PageContainer>
      <PageHeader title="Marketplace" description="Browse agent templates, plan templates, skills, MCP servers, and software" />

      <div className="flex rounded-lg border border-claude-border bg-claude-surface p-0.5 w-fit mb-6">
        <button className={tabClass("templates")} onClick={() => setTab("templates")}>
          Agent Templates
        </button>
        <button className={tabClass("plan-templates")} onClick={() => setTab("plan-templates")}>
          Plan Templates
        </button>
        <button className={tabClass("skills")} onClick={() => setTab("skills")}>
          Skills
        </button>
        <button className={tabClass("mcp")} onClick={() => setTab("mcp")}>
          MCP Servers
        </button>
        <button className={tabClass("api-tools")} onClick={() => setTab("api-tools")}>
          API Tools
        </button>
        <button className={tabClass("software")} onClick={() => setTab("software")}>
          Software
        </button>
      </div>

      {tab === "templates" && (
        <TemplatesTab templates={templates} isLoading={templatesLoading} />
      )}

      {tab === "plan-templates" && <PlanTemplatesTab />}

      {tab === "skills" && <SkillsTab />}

      {tab === "mcp" && <McpTab />}

      {tab === "api-tools" && <ApiToolsTab />}

      {tab === "software" && <SoftwareTab />}
    </PageContainer>
  );
}

function ApiToolsTab() {
  const { data: catalog = [], isLoading } = useApiToolsCatalog();
  const deleteCustom = useDeleteCustomApiTool();
  const [installEntry, setInstallEntry] = useState<ApiToolEntry | null>(null);
  const [showAddCustom, setShowAddCustom] = useState(false);

  const handleDelete = (entry: ApiToolEntry) => {
    if (window.confirm(`Remove "${entry.name}" from the API-tool catalog?`)) {
      deleteCustom.mutate(entry.id);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-claude-text-secondary">
          API Tools turn an OpenAPI / Swagger / Postman spec into agent-callable
          tools. Headers carry <code>${"${VAR}"}</code> placeholders resolved at
          runtime from the agent vault.
        </p>
        <button
          onClick={() => setShowAddCustom(true)}
          className={`${css.btn} flex items-center gap-1.5 border border-claude-border bg-claude-input hover:bg-claude-surface text-claude-text-primary text-xs shrink-0`}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add Custom
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12 text-sm text-claude-text-muted">
          Loading API-tool catalog…
        </div>
      )}

      {!isLoading && catalog.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-claude-text-muted">
          <p className="text-sm">No API tools available. Add a custom entry above.</p>
        </div>
      )}

      {!isLoading && catalog.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {catalog.map((entry: ApiToolEntry) => (
            <ApiToolCard
              key={entry.id}
              entry={entry}
              onInstall={() => setInstallEntry(entry)}
              onDelete={
                entry.source === "self-hosted" ? () => handleDelete(entry) : undefined
              }
            />
          ))}
        </div>
      )}

      <InstallApiToolModal
        open={!!installEntry}
        onClose={() => setInstallEntry(null)}
        entry={installEntry}
      />

      <AddCustomApiToolModal
        open={showAddCustom}
        onClose={() => setShowAddCustom(false)}
      />
    </div>
  );
}

function ApiToolCard({
  entry,
  onInstall,
  onDelete,
}: {
  entry: ApiToolEntry;
  onInstall: () => void;
  onDelete?: () => void;
}) {
  return (
    <div className="rounded-lg border border-claude-border bg-claude-surface p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-claude-text-primary">
              {entry.name}
            </h3>
            {entry.source === "self-hosted" && (
              <span className="text-[10px] uppercase tracking-wide rounded px-1.5 py-0.5 bg-claude-accent/10 text-claude-accent">
                custom
              </span>
            )}
          </div>
          {entry.author && (
            <p className="text-xs text-claude-text-muted">{entry.author}</p>
          )}
        </div>
        {onDelete && (
          <button
            onClick={onDelete}
            className="text-claude-text-muted hover:text-red-500 transition-colors"
            aria-label="Remove"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        )}
      </div>
      {entry.description && (
        <p className="text-xs text-claude-text-secondary line-clamp-3">
          {entry.description}
        </p>
      )}
      <div className="flex flex-wrap gap-1">
        {(entry.categories ?? []).map((c) => (
          <span
            key={c}
            className="text-[10px] rounded px-1.5 py-0.5 bg-claude-input text-claude-text-secondary"
          >
            {c}
          </span>
        ))}
      </div>
      {entry.required_env && entry.required_env.length > 0 && (
        <p className="text-[11px] text-claude-text-muted">
          Required: {entry.required_env.join(", ")}
        </p>
      )}
      <div className="mt-auto pt-2 flex justify-end">
        <button
          onClick={onInstall}
          className={`${css.btn} bg-claude-accent text-white hover:opacity-90 text-xs`}
        >
          Install on agent…
        </button>
      </div>
    </div>
  );
}

function PlanTemplatesTab() {
  const navigate = useNavigate();
  const { data: templates = [], isLoading } = usePlanTemplates();
  const { data: customEntries = [] } = useCustomPlanTemplates();
  const deleteMutation = useDeleteCustomPlanTemplate();
  const customIds = new Set(customEntries.map((e) => e.id));

  const [detailId, setDetailId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editEntry, setEditEntry] = useState<PlanTemplate | null>(null);
  const [createFromTemplate, setCreateFromTemplate] = useState<string | null>(null);

  function handleDelete(entry: PlanTemplate) {
    if (window.confirm(`Remove "${entry.name}" from plan templates?`)) {
      deleteMutation.mutate(entry.id);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-claude-text-secondary">
          Pre-built Kanban plans. Pick one when creating a plan to seed the board with columns and tasks.
        </p>
        <button
          onClick={() => setShowAdd(true)}
          className={`${css.btn} flex items-center gap-1.5 border border-claude-border bg-claude-input hover:bg-claude-surface text-claude-text-primary text-xs shrink-0`}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add Custom
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12 text-sm text-claude-text-muted">
          Loading plan templates…
        </div>
      )}

      {!isLoading && templates.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {templates.map((entry) => {
            const isCustom = customIds.has(entry.id);
            const taskCount = (entry.tasks ?? []).length;
            const colCount = (entry.columns ?? []).length || 4;
            return (
              <div
                key={entry.id}
                className="rounded-xl border border-claude-border bg-claude-input p-4 hover:border-claude-accent/30 transition-colors flex flex-col"
              >
                <button
                  onClick={() => setDetailId(entry.id)}
                  className="flex items-start gap-3 min-w-0 text-left"
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500/20 to-indigo-500/20 shrink-0">
                    <PlanIcon className="h-5 w-5 text-sky-600" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-claude-text-primary truncate">{entry.name}</span>
                      {isCustom && (
                        <span className="rounded px-1.5 py-px text-[10px] font-medium bg-claude-surface text-claude-text-muted ring-1 ring-claude-border">
                          Custom
                        </span>
                      )}
                    </div>
                    {entry.author && (
                      <p className="text-[10px] text-claude-text-muted mt-0.5">by {entry.author}</p>
                    )}
                  </div>
                </button>
                <button onClick={() => setDetailId(entry.id)} className="text-left">
                  {entry.description && (
                    <p className="mt-2 text-xs text-claude-text-secondary line-clamp-2">{entry.description}</p>
                  )}
                </button>
                <div className="mt-auto pt-3 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-[10px] text-claude-text-muted">
                    <span>{colCount} columns</span>
                    <span>·</span>
                    <span>{taskCount} tasks</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {isCustom && (
                      <>
                        <button
                          onClick={() => setEditEntry(entry)}
                          className="rounded-md px-2 py-1 text-[11px] text-claude-text-secondary hover:text-claude-text-primary hover:bg-claude-surface transition-colors"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(entry)}
                          className="rounded-md p-1 text-claude-border-strong hover:text-red-500 hover:bg-red-50 dark:bg-red-950/40 transition-all"
                          title="Delete custom template"
                        >
                          <TrashIcon className="h-3.5 w-3.5" />
                        </button>
                      </>
                    )}
                    <button
                      onClick={() => setCreateFromTemplate(entry.id)}
                      className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover text-xs px-3 py-1.5`}
                    >
                      Use template
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!isLoading && templates.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-claude-text-muted">
          <PlanIcon className="h-8 w-8 mb-2" />
          <p className="text-sm">No plan templates yet. Click "Add Custom" to create one.</p>
        </div>
      )}

      <PlanTemplateDetailModal
        open={!!detailId}
        templateId={detailId}
        onClose={() => setDetailId(null)}
        onUseTemplate={(id) => {
          setDetailId(null);
          setCreateFromTemplate(id);
        }}
      />

      <AddPlanTemplateModal
        open={showAdd || !!editEntry}
        onClose={() => {
          setShowAdd(false);
          setEditEntry(null);
        }}
        entryToEdit={editEntry}
      />

      <CreatePlanModal
        open={!!createFromTemplate}
        onClose={() => setCreateFromTemplate(null)}
        initialTemplateId={createFromTemplate ?? undefined}
        onPlanCreated={(planId) => {
          setCreateFromTemplate(null);
          navigate(`/plans/${planId}`);
        }}
      />
    </div>
  );
}

function TemplatesTab({ templates, isLoading }: { templates: { value: string; label: string }[]; isLoading: boolean }) {
  const [detailTemplate, setDetailTemplate] = useState<string | null>(null);
  const [createTemplate, setCreateTemplate] = useState<string | null>(null);

  if (isLoading) {
    return <p className="text-claude-text-muted text-sm">Loading templates...</p>;
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {templates.map((t) => (
          <button
            key={t.value}
            onClick={() => setDetailTemplate(t.value)}
            className="rounded-xl border border-claude-border bg-claude-input p-4 hover:border-claude-accent/50 hover:shadow-sm transition-all text-left group"
          >
            <div className="flex items-center gap-3 mb-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-claude-accent/10 group-hover:bg-claude-accent/20 transition-colors">
                <RoleIcon role={t.value} />
              </div>
              <div>
                <h3 className="font-medium text-claude-text-primary">{t.label}</h3>
              </div>
            </div>
            <p className="text-sm text-claude-text-secondary">
              Pre-configured with {t.label.toLowerCase()} skills and settings.
            </p>
            <div className="mt-3 flex justify-end">
              <span className="text-xs text-claude-accent opacity-0 group-hover:opacity-100 transition-opacity font-medium">
                Create Agent →
              </span>
            </div>
          </button>
        ))}
      </div>

      <TemplateDetailModal
        open={!!detailTemplate}
        templateId={detailTemplate}
        onClose={() => setDetailTemplate(null)}
        onCreateSpecialAgent={(id) => setCreateTemplate(id)}
      />

      <CreateSpecialAgentModal
        open={!!createTemplate}
        onClose={() => setCreateTemplate(null)}
        initialTemplate={createTemplate ?? undefined}
      />
    </>
  );
}

type SourceFilter = "all" | "agentskill.sh" | "self-hosted";
type McpSourceFilter = "all" | "official" | "self-hosted";

function SkillsTab() {
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const { data: skills, isLoading, error } = useSearchSkills(searchQuery, true);
  const { data: customEntries = [] } = useCustomSkills();
  const deleteCustomMutation = useDeleteCustomSkill();
  const [installSkill, setInstallSkill] = useState<MarketplaceSkill | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<MarketplaceSkill | null>(null);
  const [showAddCustom, setShowAddCustom] = useState(false);
  const [editCustom, setEditCustom] = useState<CustomSkillEntry | null>(null);

  useEffect(() => {
    setSearchQuery("");
  }, []);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearchQuery(searchInput.trim() || "");
  }

  const customBySlug = new Map(customEntries.map((e) => [e.slug, e]));
  const filteredSkills = (() => {
    const seen = new Set<string>();
    const out: MarketplaceSkill[] = [];
    for (const s of skills ?? []) {
      if (sourceFilter !== "all" && s.source !== sourceFilter) continue;
      const key = `${s.source ?? "?"}:${s.slug}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
    }
    return out;
  })();

  function handleDeleteCustom(slug: string, name: string) {
    if (window.confirm(`Remove "${name}" from self-hosted skills?`)) {
      deleteCustomMutation.mutate(slug);
    }
  }

  const filterBtn = (f: SourceFilter, label: string) => (
    <button
      type="button"
      onClick={() => setSourceFilter(f)}
      className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
        sourceFilter === f
          ? "bg-claude-input text-claude-text-primary shadow-sm"
          : "text-claude-text-muted hover:text-claude-text-secondary"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2 text-sm text-claude-text-secondary max-w-2xl">
          <span>Skills extend your agents with specialized capabilities. Powered by</span>
          <a
            href="https://agentskill.sh"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-claude-accent hover:underline font-medium"
          >
            agentskill.sh
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
          <span>or add self-hosted entries.</span>
        </div>
        <button
          onClick={() => setShowAddCustom(true)}
          className={`${css.btn} flex items-center gap-1.5 border border-claude-border bg-claude-input hover:bg-claude-surface text-claude-text-primary text-xs shrink-0`}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add Custom
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={handleSearch} className="flex gap-2 flex-1 min-w-[240px] max-w-2xl">
          <div className="relative flex-1">
            <svg className="absolute left-2.5 top-2.5 h-4 w-4 text-claude-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              className={`${css.input} pl-8`}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search skills... (e.g. web scraping, calendar, github)"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover disabled:opacity-40 shrink-0 min-w-[80px]`}
          >
            {isLoading ? (
              <span className="inline-flex items-center gap-1">
                <span className="h-1 w-1 rounded-full bg-claude-input animate-pulse" />
                <span className="h-1 w-1 rounded-full bg-claude-input animate-pulse [animation-delay:150ms]" />
                <span className="h-1 w-1 rounded-full bg-claude-input animate-pulse [animation-delay:300ms]" />
              </span>
            ) : "Search"}
          </button>
        </form>

        <div className="flex rounded-lg border border-claude-border bg-claude-surface p-0.5 shrink-0">
          {filterBtn("all", "All")}
          {filterBtn("agentskill.sh", "agentskill.sh")}
          {filterBtn("self-hosted", "Self-hosted")}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700">
          Search failed: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="flex items-center gap-2 text-sm text-claude-text-muted">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Searching skills...
          </div>
        </div>
      )}

      {!isLoading && filteredSkills.length > 0 && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filteredSkills.map((skill: MarketplaceSkill) => (
              <SkillCard
                key={`${skill.source ?? "?"}:${skill.slug}`}
                skill={skill}
                onSelect={() => setSelectedSkill(skill)}
                onInstall={() => setInstallSkill(skill)}
                onEdit={
                  skill.source === "self-hosted" && customBySlug.has(skill.slug)
                    ? () => setEditCustom(customBySlug.get(skill.slug) ?? null)
                    : undefined
                }
                onDelete={
                  skill.source === "self-hosted" && customBySlug.has(skill.slug)
                    ? () => handleDeleteCustom(skill.slug, skill.name)
                    : undefined
                }
              />
            ))}
          </div>
        </div>
      )}

      {!isLoading && filteredSkills.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-claude-text-muted">
          <svg className="h-8 w-8 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm">
            {sourceFilter === "self-hosted"
              ? 'No self-hosted skills yet. Click "Add Custom" to create one.'
              : searchQuery
              ? `No skills found for "${searchQuery}"`
              : "No skills found."}
          </p>
          {sourceFilter !== "self-hosted" && (
            <p className="text-xs mt-1">
              Try different keywords or browse{" "}
              <a
                href="https://agentskill.sh"
                target="_blank"
                rel="noreferrer"
                className="text-claude-accent hover:underline"
              >
                agentskill.sh
              </a>
            </p>
          )}
        </div>
      )}

      <InstallSkillModal
        open={!!installSkill}
        onClose={() => setInstallSkill(null)}
        skill={installSkill}
      />

      <SkillDetailModal
        skill={selectedSkill}
        onClose={() => setSelectedSkill(null)}
        onInstall={() => {
          setSelectedSkill(null);
          if (selectedSkill) setInstallSkill(selectedSkill);
        }}
      />

      <AddCustomSkillModal
        open={showAddCustom || !!editCustom}
        onClose={() => {
          setShowAddCustom(false);
          setEditCustom(null);
        }}
        entryToEdit={editCustom}
      />
    </div>
  );
}

function isLikelyAuthor(value: string | undefined): boolean {
  if (!value) return false;
  if (/^\d+\.?\d*$/.test(value)) return false;
  if (/^v?\d+(\.\d+)*$/.test(value)) return false;
  if (value.length > 40) return false;
  if ((value.match(/\s/g) || []).length > 3) return false;
  return true;
}

function isLikelyVersion(value: string | undefined): boolean {
  return !!value && /^v?\d+(\.\d+)*$/.test(value);
}

function SkillCard({
  skill,
  onSelect,
  onInstall,
  onEdit,
  onDelete,
}: {
  skill: MarketplaceSkill;
  onSelect: () => void;
  onInstall: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const author = isLikelyAuthor(skill.author) ? skill.author : undefined;
  const descFromAuthor = !isLikelyAuthor(skill.author) && skill.author && !isLikelyVersion(skill.author) ? skill.author : undefined;
  const description = (skill.description && !isLikelyVersion(skill.description)) ? skill.description : descFromAuthor;
  const version = skill.version || (isLikelyVersion(skill.description) ? skill.description?.replace(/^v/, "") : undefined);
  const isSelfHosted = skill.source === "self-hosted";

  return (
    <div className="rounded-xl border border-claude-border bg-claude-input p-4 hover:border-claude-accent/30 transition-colors flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <button onClick={onSelect} className="flex items-center gap-3 min-w-0 text-left">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500/20 to-orange-500/20 shrink-0">
            <svg className="h-5 w-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium text-claude-text-primary truncate">{skill.name}</span>
              {isSelfHosted && (
                <span
                  className="rounded px-1.5 py-px text-[10px] font-medium bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 ring-1 ring-indigo-200 shrink-0"
                  title="Stored in this deployment's admin catalog"
                >
                  Self-hosted
                </span>
              )}
            </div>
            {author && (
              <p className="text-[10px] text-claude-text-muted mt-0.5">by {author}</p>
            )}
          </div>
        </button>
      </div>
      <button onClick={onSelect} className="text-left w-full">
        {description && (
          <p className="mt-2 text-xs text-claude-text-secondary line-clamp-2">{description}</p>
        )}
      </button>
      <div className="mt-auto pt-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {version && (
            <span className="rounded px-1.5 py-px text-[10px] font-mono text-claude-text-muted ring-1 ring-claude-border">
              v{version}
            </span>
          )}
          {skill.homepage && (
            <a
              href={skill.homepage}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="Setup guide / homepage"
              className="inline-flex items-center gap-0.5 text-[10px] text-claude-text-muted hover:text-claude-accent transition-colors"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Docs
            </a>
          )}
          {!skill.homepage && !isSelfHosted && (
            <a
              href={`https://agentskill.sh/skills/${skill.slug}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="View on agentskill.sh"
              className="inline-flex items-center gap-0.5 text-[10px] text-claude-text-muted hover:text-claude-accent transition-colors"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Docs
            </a>
          )}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1.5">
          {onEdit && (
            <button
              onClick={onEdit}
              className="rounded-md px-2 py-1 text-[11px] text-claude-text-secondary hover:text-claude-text-primary hover:bg-claude-surface transition-colors"
            >
              Edit
            </button>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              className="rounded-md p-1 text-claude-border-strong hover:text-red-500 hover:bg-red-50 dark:bg-red-950/40 transition-all"
              title="Delete self-hosted skill"
            >
              <TrashIcon className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onInstall}
            className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover text-xs px-3 py-1.5`}
          >
            Install
          </button>
        </div>
      </div>
    </div>
  );
}

function McpTab() {
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<McpSourceFilter>("all");
  const { data: servers, isLoading, error } = useSearchMcpServers(searchQuery);
  const { data: customEntries = [] } = useCustomMcpServers();
  const deleteCustomMutation = useDeleteCustomMcpServer();
  const [selectedServer, setSelectedServer] = useState<MCPRegistryServer | null>(null);
  const [installServer, setInstallServer] = useState<MCPRegistryServer | null>(null);
  const [showAddCustom, setShowAddCustom] = useState(false);
  const [editCustom, setEditCustom] = useState<CustomMcpEntry | null>(null);

  const customBySlug = new Map(customEntries.map((e) => [e.slug, e]));

  const filteredServers = (() => {
    const seen = new Set<string>();
    const out: MCPRegistryServer[] = [];
    for (const s of servers ?? []) {
      if (sourceFilter !== "all" && s.source !== sourceFilter) continue;
      const key = `${s.source ?? "?"}:${s.id || s.slug}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
    }
    // Self-hosted first, then by downloads desc.
    out.sort((a, b) => {
      const aKey = a.source === "self-hosted" ? 0 : 1;
      const bKey = b.source === "self-hosted" ? 0 : 1;
      if (aKey !== bKey) return aKey - bKey;
      return (b.downloads || 0) - (a.downloads || 0);
    });
    return out;
  })();

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearchQuery(searchInput.trim());
  }

  function handleDeleteCustom(slug: string, name: string) {
    if (window.confirm(`Remove "${name}" from self-hosted MCP servers?`)) {
      deleteCustomMutation.mutate(slug);
    }
  }

  const filterBtn = (f: McpSourceFilter, label: string) => (
    <button
      type="button"
      onClick={() => setSourceFilter(f)}
      className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
        sourceFilter === f
          ? "bg-claude-input text-claude-text-primary shadow-sm"
          : "text-claude-text-muted hover:text-claude-text-secondary"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2 text-sm text-claude-text-secondary max-w-2xl">
          <span>MCP servers extend your agents with external tools. Powered by</span>
          <a
            href="https://registry.modelcontextprotocol.io"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-claude-accent hover:underline font-medium"
          >
            registry.modelcontextprotocol.io
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
          <span>or add self-hosted entries.</span>
        </div>
        <button
          onClick={() => setShowAddCustom(true)}
          className={`${css.btn} flex items-center gap-1.5 border border-claude-border bg-claude-input hover:bg-claude-surface text-claude-text-primary text-xs shrink-0`}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add Custom
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={handleSearch} className="flex gap-2 flex-1 min-w-[240px] max-w-2xl">
          <div className="relative flex-1">
            <svg className="absolute left-2.5 top-2.5 h-4 w-4 text-claude-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              className={`${css.input} pl-8`}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search MCP servers... (e.g. filesystem, github, postgres)"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover disabled:opacity-40 shrink-0 min-w-[80px]`}
          >
            {isLoading ? (
              <span className="inline-flex items-center gap-1">
                <span className="h-1 w-1 rounded-full bg-claude-input animate-pulse" />
                <span className="h-1 w-1 rounded-full bg-claude-input animate-pulse [animation-delay:150ms]" />
                <span className="h-1 w-1 rounded-full bg-claude-input animate-pulse [animation-delay:300ms]" />
              </span>
            ) : "Search"}
          </button>
        </form>

        <div className="flex rounded-lg border border-claude-border bg-claude-surface p-0.5 shrink-0">
          {filterBtn("all", "All")}
          {filterBtn("official", "Official")}
          {filterBtn("self-hosted", "Self-hosted")}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700">
          Search failed: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="flex items-center gap-2 text-sm text-claude-text-muted">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Searching MCP registry...
          </div>
        </div>
      )}

      {!isLoading && filteredServers.length > 0 && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filteredServers.map((server: MCPRegistryServer) => {
              const serverId = server.id || server.slug;
              const isSelfHosted = server.source === "self-hosted";
              return (
                <McpServerCard
                  key={`${server.source ?? "?"}:${serverId}`}
                  server={server}
                  onSelect={() => setSelectedServer(server)}
                  onInstall={() => setInstallServer(server)}
                  onEdit={
                    isSelfHosted && customBySlug.has(server.slug)
                      ? () => setEditCustom(customBySlug.get(server.slug) ?? null)
                      : undefined
                  }
                  onDelete={
                    isSelfHosted && customBySlug.has(server.slug)
                      ? () => handleDeleteCustom(server.slug, server.name)
                      : undefined
                  }
                />
              );
            })}
          </div>
        </div>
      )}

      {!isLoading && filteredServers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-claude-text-muted">
          <svg className="h-8 w-8 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm">
            {sourceFilter === "self-hosted"
              ? 'No self-hosted MCP servers yet. Click "Add Custom" to create one.'
              : searchQuery
              ? `No MCP servers found for "${searchQuery}"`
              : "No MCP servers available."}
          </p>
          {sourceFilter !== "self-hosted" && (
            <p className="text-xs mt-1">
              Try different keywords or browse{" "}
              <a
                href="https://registry.modelcontextprotocol.io"
                target="_blank"
                rel="noreferrer"
                className="text-claude-accent hover:underline"
              >
                registry.modelcontextprotocol.io
              </a>
            </p>
          )}
        </div>
      )}

      <McpServerDetailModal
        server={selectedServer}
        onClose={() => setSelectedServer(null)}
        onInstall={() => {
          setInstallServer(selectedServer);
          setSelectedServer(null);
        }}
      />

      <InstallMcpModal
        open={!!installServer}
        onClose={() => setInstallServer(null)}
        server={installServer}
      />

      <AddCustomMcpModal
        open={showAddCustom || !!editCustom}
        onClose={() => {
          setShowAddCustom(false);
          setEditCustom(null);
        }}
        entryToEdit={editCustom}
      />
    </div>
  );
}

function formatDownloads(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function McpServerCard({
  server,
  onSelect,
  onInstall,
  onEdit,
  onDelete,
}: {
  server: MCPRegistryServer;
  onSelect: () => void;
  onInstall: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const isVerified = server.verified || server.is_verified;
  const isSelfHosted = server.source === "self-hosted";
  const downloads = server.downloads || 0;
  return (
    <div className="rounded-xl border border-claude-border bg-claude-input p-4 hover:border-claude-accent/30 transition-colors flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <button onClick={onSelect} className="flex items-center gap-3 min-w-0 text-left">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500/20 to-indigo-500/20 shrink-0">
            <svg className="h-5 w-5 text-violet-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-sm font-medium text-claude-text-primary">{server.name}</span>
              {isSelfHosted && (
                <span
                  className="rounded px-1.5 py-px text-[10px] font-medium bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 ring-1 ring-indigo-200 shrink-0"
                  title="Stored in this deployment's admin catalog"
                >
                  Self-hosted
                </span>
              )}
            </div>
            {server.author && !/^\d+\.?\d*$/.test(server.author) && (
              <p className="text-[10px] text-claude-text-muted mt-0.5">by {server.author}</p>
            )}
          </div>
        </button>
        {downloads > 0 && (
          <span className="inline-flex items-center gap-1 text-[10px] text-claude-text-muted shrink-0" title={`${downloads.toLocaleString()} downloads`}>
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            {formatDownloads(downloads)}
          </span>
        )}
      </div>
      <button onClick={onSelect} className="text-left w-full">
        <p className="mt-2 text-xs text-claude-text-secondary line-clamp-2">{server.description}</p>
      </button>
      <div className="mt-auto pt-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {server.version && (
            <span className="rounded px-1.5 py-px text-[10px] font-mono text-claude-text-muted ring-1 ring-claude-border">
              v{server.version}
            </span>
          )}
          {isVerified && (
            <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-px text-[10px] font-medium bg-green-50 dark:bg-green-950/40 text-green-700 ring-1 ring-green-200">
              <svg className="h-2.5 w-2.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              Verified
            </span>
          )}
          {(server.homepage || server.repository) && (
            <a
              href={server.homepage || server.repository}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="Setup guide / documentation"
              className="inline-flex items-center gap-0.5 text-[10px] text-claude-text-muted hover:text-claude-accent transition-colors"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Docs
            </a>
          )}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1.5">
          {onEdit && (
            <button
              onClick={onEdit}
              className="rounded-md px-2 py-1 text-[11px] text-claude-text-secondary hover:text-claude-text-primary hover:bg-claude-surface transition-colors"
            >
              Edit
            </button>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              className="rounded-md p-1 text-claude-border-strong hover:text-red-500 hover:bg-red-50 dark:bg-red-950/40 transition-all"
              title="Delete self-hosted MCP server"
            >
              <TrashIcon className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onInstall}
            className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover text-xs px-3 py-1.5`}
          >
            Install
          </button>
        </div>
      </div>
    </div>
  );
}

function McpServerDetailModal({
  server,
  onClose,
  onInstall,
}: {
  server: MCPRegistryServer | null;
  onClose: () => void;
  onInstall: () => void;
}) {
  if (!server) return null;

  const isVerified = server.verified || server.is_verified;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
      <div
        className="bg-claude-input rounded-2xl shadow-xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-claude-border flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500/20 to-indigo-500/20 shrink-0">
              <svg className="h-4 w-4 text-violet-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
              </svg>
            </div>
            <h2 className="text-base font-semibold text-claude-text-primary truncate">{server.name}</h2>
            {isVerified && (
              <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-px text-[10px] font-medium bg-green-50 dark:bg-green-950/40 text-green-700 ring-1 ring-green-200 shrink-0">
                <svg className="h-2.5 w-2.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                Verified
              </span>
            )}
            {server.version && (
              <span className="text-[10px] font-mono text-claude-text-muted shrink-0">v{server.version}</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-claude-surface transition-colors shrink-0"
          >
            <svg className="h-4 w-4 text-claude-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          <p className="text-sm text-claude-text-secondary">{server.description}</p>

          {server.categories && server.categories.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-claude-text-muted uppercase tracking-wide mb-2">Categories</h3>
              <div className="flex flex-wrap gap-2">
                {server.categories.map((cat) => (
                  <span
                    key={cat}
                    className="rounded-full px-3 py-1 text-xs bg-claude-surface text-claude-text-secondary"
                  >
                    {cat}
                  </span>
                ))}
              </div>
            </div>
          )}

          {server.capabilities && server.capabilities.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-claude-text-muted uppercase tracking-wide mb-2">Capabilities</h3>
              <div className="flex flex-wrap gap-2">
                {server.capabilities.map((cap) => (
                  <span
                    key={cap}
                    className="rounded px-2 py-1 text-xs bg-green-50 dark:bg-green-950/40 text-green-700 ring-1 ring-green-200"
                  >
                    {cap}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-4 text-sm">
            {server.repository && (
              <a
                href={server.repository}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-claude-text-secondary hover:text-claude-accent transition-colors"
              >
                <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>
                Repository
              </a>
            )}
            {server.homepage && (
              <a
                href={server.homepage}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-claude-text-secondary hover:text-claude-accent transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                </svg>
                Homepage
              </a>
            )}
            {server.license && (
              <span className="inline-flex items-center gap-1.5 text-claude-text-muted">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                {server.license}
              </span>
            )}
            {server.downloads > 0 && (
              <span className="inline-flex items-center gap-1.5 text-claude-text-muted">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                {server.downloads.toLocaleString()} installs
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-sm">
            <span className="text-claude-text-muted">Server ID:</span>
            <code className="rounded bg-slate-900 text-slate-100 px-2 py-1 text-xs font-mono">
              {server.id || server.slug}
            </code>
          </div>
        </div>

        <div className="px-4 py-2 border-t border-claude-border bg-claude-surface/30 flex justify-end gap-2">
          <button
            onClick={onClose}
            className={`${css.btn} border border-claude-border bg-claude-input hover:bg-claude-surface text-xs px-3 py-1.5`}
          >
            Close
          </button>
          <button
            onClick={onInstall}
            className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover text-xs px-3 py-1.5`}
          >
            Install
          </button>
        </div>
      </div>
    </div>
  );
}

function SkillDetailModal({
  skill,
  onClose,
  onInstall,
}: {
  skill: MarketplaceSkill | null;
  onClose: () => void;
  onInstall: () => void;
}) {
  if (!skill) return null;

  const author = isLikelyAuthor(skill.author) ? skill.author : undefined;
  const descFromAuthor = !isLikelyAuthor(skill.author) && skill.author && !isLikelyVersion(skill.author) ? skill.author : undefined;
  const description = (skill.description && !isLikelyVersion(skill.description)) ? skill.description : descFromAuthor;
  const version = skill.version || (isLikelyVersion(skill.description) ? skill.description?.replace(/^v/, "") : undefined);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
      <div
        className="bg-claude-input rounded-2xl shadow-xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-claude-border flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500/20 to-orange-500/20 shrink-0">
              <svg className="h-4 w-4 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
              </svg>
            </div>
            <h2 className="text-base font-semibold text-claude-text-primary truncate">{skill.name}</h2>
            {version && (
              <span className="text-[10px] font-mono text-claude-text-muted shrink-0">v{version}</span>
            )}
            {skill.source === "self-hosted" && (
              <span className="rounded px-1.5 py-px text-[10px] font-medium bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 ring-1 ring-indigo-200 shrink-0">
                Self-hosted
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-claude-surface transition-colors shrink-0"
          >
            <svg className="h-4 w-4 text-claude-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {description && (
            <p className="text-sm text-claude-text-secondary">{description}</p>
          )}

          {author && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-claude-text-muted">Author:</span>
              <span className="text-claude-text-primary">{author}</span>
            </div>
          )}

          <div className="flex items-center gap-2 text-sm">
            <span className="text-claude-text-muted">Skill ID:</span>
            <code className="rounded bg-slate-900 text-slate-100 px-2 py-1 text-xs font-mono">
              {skill.slug}
            </code>
          </div>

          <div className="flex flex-wrap gap-3 text-sm">
            {skill.homepage && (
              <a
                href={skill.homepage}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-claude-text-secondary hover:text-claude-accent transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                </svg>
                Setup Guide
              </a>
            )}
            {skill.repository && (
              <a
                href={skill.repository}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-claude-text-secondary hover:text-claude-accent transition-colors"
              >
                <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>
                Repository
              </a>
            )}
            {!skill.homepage && !skill.repository && skill.source !== "self-hosted" && (
              <a
                href={`https://agentskill.sh/skills/${skill.slug}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-claude-text-secondary hover:text-claude-accent transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
                View on agentskill.sh
              </a>
            )}
          </div>
        </div>

        <div className="px-4 py-2 border-t border-claude-border bg-claude-surface/30 flex justify-end gap-2">
          <button
            onClick={onClose}
            className={`${css.btn} border border-claude-border bg-claude-input hover:bg-claude-surface text-xs px-3 py-1.5`}
          >
            Close
          </button>
          <button
            onClick={onInstall}
            className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover text-xs px-3 py-1.5`}
          >
            Install
          </button>
        </div>
      </div>
    </div>
  );
}

function SoftwareTab() {
  const { data: catalog = [], isLoading } = useSoftwareCatalog();
  const { data: customEntries = [] } = useCustomSoftware();
  const deleteMutation = useDeleteCustomSoftware();
  const customIds = new Set((customEntries as { id?: string }[]).map((e) => e.id).filter(Boolean));
  const [installEntry, setInstallEntry] = useState<SoftwareCatalogEntry | null>(null);
  const [showAddCustom, setShowAddCustom] = useState(false);
  const [editEntry, setEditEntry] = useState<SoftwareCatalogEntry | null>(null);

  const handleDeleteCustom = (entry: SoftwareCatalogEntry) => {
    if (window.confirm(`Remove "${entry.name}" from custom catalog?`)) {
      deleteMutation.mutate(entry.id);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-claude-text-secondary">
          Software extends your specialagents with CLI tools that can be installed into Docker containers.
        </p>
        <button
          onClick={() => setShowAddCustom(true)}
          className={`${css.btn} flex items-center gap-1.5 border border-claude-border bg-claude-input hover:bg-claude-surface text-claude-text-primary text-xs shrink-0`}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add Custom
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="flex items-center gap-2 text-sm text-claude-text-muted">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading software catalog...
          </div>
        </div>
      )}

      {!isLoading && catalog.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {catalog.map((entry: SoftwareCatalogEntry) => (
            <SoftwareCard
              key={entry.id}
              entry={entry}
              isCustom={customIds.has(entry.id)}
              onInstall={() => setInstallEntry(entry)}
              onEdit={customIds.has(entry.id) ? () => setEditEntry(entry) : undefined}
              onDelete={customIds.has(entry.id) ? () => handleDeleteCustom(entry) : undefined}
            />
          ))}
        </div>
      )}

      {!isLoading && catalog.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-claude-text-muted">
          <svg className="h-8 w-8 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm">No software available in the catalog yet.</p>
        </div>
      )}

      <InstallSoftwareModal
        open={!!installEntry}
        onClose={() => setInstallEntry(null)}
        entry={installEntry}
      />

      <AddCustomSoftwareModal
        open={showAddCustom || !!editEntry}
        onClose={() => {
          setShowAddCustom(false);
          setEditEntry(null);
        }}
        entryToEdit={editEntry}
      />
    </div>
  );
}

/** Convert a display name to a slug id, e.g. "Google Cal MCP" → "google-cal-mcp" */
function toSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Parse a GitHub release URL into pre-filled form fields.
 *
 * Handles patterns like:
 *   https://github.com/owner/repo/releases/tag/v1.2.3
 *   https://github.com/owner/repo/releases/download/v1.2.3/pkg.tgz
 *   https://github.com/owner/repo  (just the repo)
 *
 * For release tag URLs the npm package becomes the tarball URL pointing to the
 * GitHub release assets (npm can install directly from a .tgz URL).
 */
function parseGithubUrl(raw: string): Partial<{
  name: string; author: string; version: string;
  installType: string; package: string; command: string;
}> | null {
  const url = raw.trim();
  // Must look like a github.com URL
  const m = url.match(/github\.com\/([^/]+)\/([^/?#]+)/);
  if (!m) return null;

  const owner = m[1];
  const repo = m[2].replace(/\.git$/, "");

  // Derive a friendly name from the repo slug
  const name = repo
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  // Try to extract a version tag
  const tagMatch = url.match(/\/releases\/(?:tag|download)\/([^/]+)/);
  const version = tagMatch ? tagMatch[1].replace(/^v/, "") : "latest";

  // If it's a direct .tgz download link, use it verbatim as the npm package
  if (url.endsWith(".tgz") || url.endsWith(".tar.gz")) {
    return { name, author: owner, version, installType: "npm", package: url, command: toSlug(repo) };
  }

  // For a release tag URL, construct the likely tarball URL.
  // GitHub publishes source tarballs at /archive/refs/tags/<tag>.tar.gz
  // but npm packages are usually published as assets. We use the tag URL
  // directly — npm supports `npm install <git-url>#semver:...` or tarball URLs.
  // Best we can do without fetching the page is point to the source archive.
  if (tagMatch) {
    const tag = tagMatch[1];
    const tgzUrl = `https://github.com/${owner}/${repo}/archive/refs/tags/${tag}.tar.gz`;
    return { name, author: owner, version: version, installType: "npm", package: tgzUrl, command: toSlug(repo) };
  }

  // Plain repo URL — use npm's git shorthand
  return { name, author: owner, version: "latest", installType: "npm", package: `github:${owner}/${repo}`, command: toSlug(repo) };
}

const EMPTY_FORM = {
  githubUrl: "",
  name: "",
  description: "",
  author: "",
  version: "",
  installType: "npm",
  package: "",
  command: "",
  args: "",
  autoRun: false,
  postInstallCommand: "",
  postInstallArgs: "",
  postInstallDaemon: true,
  postInstallEnv: "",
};

function AddCustomSoftwareModal({ open, onClose, entryToEdit }: { open: boolean; onClose: () => void; entryToEdit?: SoftwareCatalogEntry | null }) {
  const addMutation = useAddCustomSoftware();
  const updateMutation = useUpdateCustomSoftware();

  const [form, setForm] = useState(EMPTY_FORM);
  const [idOverride, setIdOverride] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (open && entryToEdit) {
      const install = (entryToEdit as { install?: { type?: string; package?: string } }).install || {};
      const run = (entryToEdit as { run?: { command?: string; args?: string[] } }).run || {};
      const pi = (entryToEdit as { post_install?: { command?: string; args?: string[]; daemon?: boolean; env?: Record<string, string> } }).post_install;
      setForm({
        githubUrl: "",
        name: entryToEdit.name || "",
        description: entryToEdit.description || "",
        author: entryToEdit.author || "",
        version: entryToEdit.version || "latest",
        installType: install.type || "npm",
        package: install.package || "",
        command: run.command || "",
        args: Array.isArray(run.args) ? run.args.join(" ") : "",
        autoRun: !!pi,
        postInstallCommand: pi?.command || run.command || "",
        postInstallArgs: Array.isArray(pi?.args) ? pi.args.join(" ") : "",
        postInstallDaemon: pi?.daemon ?? true,
        postInstallEnv: pi?.env ? Object.entries(pi.env).map(([k, v]) => `${k}=${v}`).join("\n") : "",
      });
      setIdOverride(entryToEdit.id || "");
    } else if (open && !entryToEdit) {
      setForm(EMPTY_FORM);
      setIdOverride("");
    }
  }, [open, entryToEdit]);

  const derivedId = idOverride || toSlug(form.name);

  function reset() {
    setForm(EMPTY_FORM);
    setIdOverride("");
    setError("");
    setSuccess("");
  }

  function handleClose() {
    reset();
    onClose();
  }

  function handleGithubUrl(raw: string) {
    setForm((f) => ({ ...f, githubUrl: raw }));
    const parsed = parseGithubUrl(raw);
    if (!parsed) return;
    setForm((f) => ({
      ...f,
      githubUrl: raw,
      name: parsed.name ?? f.name,
      author: parsed.author ?? f.author,
      version: parsed.version ?? f.version,
      installType: parsed.installType ?? f.installType,
      package: parsed.package ?? f.package,
      command: parsed.command ?? f.command,
    }));
    setIdOverride("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess("");
    const id = derivedId;
    if (!id || !form.name.trim() || !form.package.trim() || !form.command.trim()) {
      setError("Name, Package, and Command are required.");
      return;
    }
    const payload: AddCustomSoftwarePayload = {
      id,
      name: form.name.trim(),
      description: form.description.trim(),
      author: form.author.trim(),
      version: form.version.trim() || "latest",
      install: { type: form.installType, package: form.package.trim() },
      run: {
        command: form.command.trim(),
        args: form.args.trim() ? form.args.trim().split(/\s+/) : [],
      },
      ...(form.autoRun && {
        post_install: {
          command: (form.postInstallCommand || form.command).trim(),
          args: form.postInstallArgs.trim() ? form.postInstallArgs.trim().split(/\s+/) : [],
          daemon: form.postInstallDaemon,
          ...(form.postInstallEnv.trim() && {
            env: Object.fromEntries(
              form.postInstallEnv.trim().split("\n").filter(Boolean).map((line) => {
                const [k, ...rest] = line.split("=");
                return [k.trim(), rest.join("=").trim()];
              })
            ),
          }),
        },
      }),
    };
    try {
      if (entryToEdit) {
        await updateMutation.mutateAsync({ softwareId: entryToEdit.id, entry: payload });
        setSuccess(`"${payload.name}" updated.`);
      } else {
        await addMutation.mutateAsync(payload);
        setSuccess(`"${payload.name}" added to catalog.`);
      }
      reset();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save software.");
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={handleClose}>
      <div
        className="bg-claude-input rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-claude-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-claude-text-primary">
            {entryToEdit ? "Edit Custom Software" : "Add Custom Software"}
          </h2>
          <button onClick={handleClose} className="p-1 rounded-lg hover:bg-claude-surface transition-colors">
            <svg className="h-4 w-4 text-claude-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 overflow-y-auto flex-1 space-y-4">
          <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2.5 space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-claude-text-secondary">
              <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              Import from GitHub URL (optional)
            </label>
            <input
              className={css.input + " bg-claude-input"}
              placeholder="https://github.com/owner/repo/releases/tag/v1.2.3"
              value={form.githubUrl}
              onChange={(e) => handleGithubUrl(e.target.value)}
            />
            {form.githubUrl && !parseGithubUrl(form.githubUrl) && (
              <p className="text-[10px] text-amber-600">Not a recognized GitHub URL — fill in the fields below manually.</p>
            )}
            {form.githubUrl && parseGithubUrl(form.githubUrl) && (
              <p className="text-[10px] text-emerald-600">Fields pre-filled. Review and adjust below.</p>
            )}
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            {/* Name + auto ID */}
            <div>
              <label className="block text-xs font-medium text-claude-text-secondary mb-1">
                Name <span className="text-red-500">*</span>
              </label>
              <input
                className={css.input}
                placeholder="My Tool"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
              {form.name && (
                <div className="mt-1 flex items-center gap-1.5">
                  <span className="text-[10px] text-claude-text-muted">ID:</span>
                  {idOverride ? (
                    <input
                      className="text-[10px] font-mono text-claude-text-primary bg-transparent border-b border-claude-border focus:outline-none focus:border-claude-accent px-0.5 w-32"
                      value={idOverride}
                      onChange={(e) => setIdOverride(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
                    />
                  ) : (
                    <span className="text-[10px] font-mono text-claude-text-primary">{derivedId}</span>
                  )}
                  <button
                    type="button"
                    onClick={() => setIdOverride(idOverride ? "" : derivedId)}
                    className="text-[10px] text-claude-accent hover:underline"
                  >
                    {idOverride ? "reset" : "edit"}
                  </button>
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-claude-text-secondary mb-1">Description</label>
              <input
                className={css.input}
                placeholder="What does this tool do?"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-claude-text-secondary mb-1">Author</label>
                <input
                  className={css.input}
                  placeholder="GitHub owner"
                  value={form.author}
                  onChange={(e) => setForm((f) => ({ ...f, author: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-claude-text-secondary mb-1">Version</label>
                <input
                  className={css.input}
                  placeholder="latest"
                  value={form.version}
                  onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))}
                />
              </div>
            </div>

            <div className="border-t border-claude-border pt-3">
              <p className="text-xs font-medium text-claude-text-secondary mb-2">Install</p>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-claude-text-muted mb-1">Type</label>
                  <select
                    className={css.input}
                    value={form.installType}
                    onChange={(e) => setForm((f) => ({ ...f, installType: e.target.value }))}
                  >
                    <option value="npm">npm</option>
                    <option value="pip">pip</option>
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-claude-text-muted mb-1">Package <span className="text-red-500">*</span></label>
                  <input
                    className={css.input}
                    placeholder="@scope/package@latest or github:owner/repo"
                    value={form.package}
                    onChange={(e) => setForm((f) => ({ ...f, package: e.target.value }))}
                  />
                </div>
              </div>
            </div>

            <div className="border-t border-claude-border pt-3">
              <p className="text-xs font-medium text-claude-text-secondary mb-2">Run</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-claude-text-muted mb-1">Command <span className="text-red-500">*</span></label>
                  <input
                    className={css.input}
                    placeholder="my-tool"
                    value={form.command}
                    onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-xs text-claude-text-muted mb-1">Args (space-separated)</label>
                  <input
                    className={css.input}
                    placeholder="-p --flag"
                    value={form.args}
                    onChange={(e) => setForm((f) => ({ ...f, args: e.target.value }))}
                  />
                </div>
              </div>
            </div>

            <div className="border-t border-claude-border pt-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.autoRun}
                  onChange={(e) => setForm((f) => ({ ...f, autoRun: e.target.checked }))}
                  className="rounded border-claude-border accent-claude-accent"
                />
                <span className="text-xs font-medium text-claude-text-secondary">Auto-run after install/reinstall</span>
              </label>
              {form.autoRun && (
                <div className="mt-3 space-y-2 pl-5 border-l-2 border-claude-border">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-claude-text-muted mb-1">Command (default: Run command)</label>
                      <input
                        className={css.input}
                        placeholder={form.command || "my-tool"}
                        value={form.postInstallCommand}
                        onChange={(e) => setForm((f) => ({ ...f, postInstallCommand: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-claude-text-muted mb-1">Args (space-separated)</label>
                      <input
                        className={css.input}
                        placeholder="--port 3000"
                        value={form.postInstallArgs}
                        onChange={(e) => setForm((f) => ({ ...f, postInstallArgs: e.target.value }))}
                      />
                    </div>
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.postInstallDaemon}
                      onChange={(e) => setForm((f) => ({ ...f, postInstallDaemon: e.target.checked }))}
                      className="rounded border-claude-border accent-claude-accent"
                    />
                    <span className="text-xs text-claude-text-muted">Run as daemon (background)</span>
                  </label>
                  <div>
                    <label className="block text-xs text-claude-text-muted mb-1">Env (KEY=VALUE, one per line)</label>
                    <textarea
                      className={`${css.input} resize-none font-mono text-xs`}
                      rows={2}
                      placeholder="MCP_TRANSPORT=http"
                      value={form.postInstallEnv}
                      onChange={(e) => setForm((f) => ({ ...f, postInstallEnv: e.target.value }))}
                    />
                  </div>
                </div>
              )}
            </div>

            {error && <p className="text-xs text-red-500">{error}</p>}
            {success && <p className="text-xs text-emerald-600">{success}</p>}

            <button
              type="submit"
              disabled={addMutation.isPending || updateMutation.isPending}
              className={`${css.btn} w-full bg-claude-accent text-white hover:bg-claude-accent-hover text-xs disabled:opacity-50`}
            >
              {updateMutation.isPending ? "Saving..." : addMutation.isPending ? "Adding..." : entryToEdit ? "Save Changes" : "Add to Catalog"}
            </button>
          </form>

        </div>
      </div>
    </div>
  );
}

function SoftwareCard({
  entry,
  isCustom,
  onInstall,
  onEdit,
  onDelete,
}: {
  entry: SoftwareCatalogEntry;
  isCustom?: boolean;
  onInstall: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  return (
    <div className="rounded-xl border border-claude-border bg-claude-input p-4 hover:border-claude-accent/30 transition-colors flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500/20 to-teal-500/20 shrink-0">
            <svg className="h-5 w-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
            </svg>
          </div>
          <div className="min-w-0">
            <span className="text-sm font-medium text-claude-text-primary">{entry.name}</span>
            {entry.author && (
              <p className="text-[10px] text-claude-text-muted mt-0.5">by {entry.author}</p>
            )}
          </div>
        </div>
        {isCustom && (onEdit || onDelete) && (
          <div className="flex items-center gap-0.5 shrink-0">
            {onEdit && (
              <button
                onClick={(e) => { e.stopPropagation(); onEdit(); }}
                className="p-1.5 rounded hover:bg-claude-surface text-claude-text-muted hover:text-claude-accent transition-colors"
                title="Edit"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125" />
                </svg>
              </button>
            )}
            {onDelete && (
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(); }}
                className="p-1.5 rounded hover:bg-red-50 dark:bg-red-950/40 text-claude-text-muted hover:text-red-500 transition-colors"
                title="Delete"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
              </button>
            )}
          </div>
        )}
      </div>
      {entry.description && (
        <p className="mt-2 text-xs text-claude-text-secondary line-clamp-2">{entry.description}</p>
      )}
      <div className="mt-auto pt-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {entry.version && (
            <span className="rounded px-1.5 py-px text-[10px] font-mono text-claude-text-muted ring-1 ring-claude-border">
              v{entry.version}
            </span>
          )}
          {entry.categories && entry.categories.length > 0 && (
            <span className="rounded px-1.5 py-px text-[10px] text-claude-text-muted ring-1 ring-claude-border">
              {entry.categories[0]}
            </span>
          )}
        </div>
        <div className="flex-1" />
        <button
          onClick={onInstall}
          className={`${css.btn} bg-claude-accent text-white hover:bg-claude-accent-hover text-xs px-3 py-1.5`}
        >
          Install
        </button>
      </div>
    </div>
  );
}

function RoleIcon({ role }: { role: string }) {
  const cls = "h-5 w-5 text-claude-accent";
  const icons: Record<string, React.ReactNode> = {
    ceo: <HiOutlineTrophy className={cls} />,
    cto: <HiOutlineCommandLine className={cls} />,
    sre: <HiOutlineServerStack className={cls} />,
    "software-engineer": <HiOutlineCodeBracket className={cls} />,
    "product-manager": <HiOutlinePresentationChartBar className={cls} />,
    "finance-controller": <HiOutlineBanknotes className={cls} />,
    "hr-manager": <HiOutlineUserGroup className={cls} />,
    "marketing-lead": <HiOutlineMegaphone className={cls} />,
    "legal-counsel": <HiOutlineScale className={cls} />,
    "data-analyst": <HiOutlineChartBar className={cls} />,
  };
  return <>{icons[role] || <HiOutlineSparkles className={cls} />}</>;
}
