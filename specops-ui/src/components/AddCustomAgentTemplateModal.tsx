import { useEffect, useMemo, useState } from "react";
import Modal from "./Modal";
import { TrashIcon } from "./ui";
import {
  useAddCustomAgentTemplate,
  useSearchMcpServers,
  useSearchSkills,
  useUpdateCustomAgentTemplate,
} from "../lib/queries";
import type {
  CustomAgentTemplate,
  CustomAgentTemplatePayload,
  MarketplaceSkill,
  MCPRegistryServer,
} from "../lib/types";

interface AddCustomAgentTemplateModalProps {
  open: boolean;
  onClose: () => void;
  entryToEdit?: CustomAgentTemplate | null;
}

const DEFAULT_MODELS = [
  "anthropic/claude-opus-4-5",
  "anthropic/claude-sonnet-4-5",
  "anthropic/claude-haiku-4-5",
  "openai/gpt-5",
  "openai/gpt-5-mini",
];

const ALL_CHANNELS = [
  "telegram",
  "slack",
  "discord",
  "feishu",
  "email",
  "teams",
  "whatsapp",
  "zalo",
] as const;

type ChannelKey = (typeof ALL_CHANNELS)[number];

const SHELL_POLICY_MODES = [
  { value: "allow_all", label: "Allow all (use with care)" },
  { value: "allowlist", label: "Allowlist only" },
  { value: "deny_all", label: "Deny all" },
];

const WEB_PROVIDERS = [
  { value: "duckduckgo", label: "DuckDuckGo" },
  { value: "brave", label: "Brave Search (requires API key per agent)" },
  { value: "serpapi", label: "SerpAPI (requires API key per agent)" },
];

function toIdSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

type FormState = {
  idTail: string; // the part after `custom-`
  name: string;
  description: string;
  categories: string;
  model: string;
  temperature: number;
  maxTokens: number;
  maxToolIterations: number;
  memoryWindow: number;
  agentsMd: string;
  soulMd: string;
  skillIds: string[];
  mcpServerIds: string[];
  restrictToWorkspace: boolean;
  webProvider: "duckduckgo" | "brave" | "serpapi";
  shellPolicyMode: "allow_all" | "allowlist" | "deny_all";
  enabledChannels: ChannelKey[];
};

const EMPTY_FORM: FormState = {
  idTail: "",
  name: "",
  description: "",
  categories: "",
  model: "anthropic/claude-opus-4-5",
  temperature: 0.7,
  maxTokens: 8192,
  maxToolIterations: 25,
  memoryWindow: 50,
  agentsMd:
    "# Agent Instructions\n\nYou are a helpful assistant. Replace this with your agent's role, responsibilities, and guidelines.\n",
  soulMd: "",
  skillIds: [],
  mcpServerIds: [],
  restrictToWorkspace: true,
  webProvider: "duckduckgo",
  shellPolicyMode: "allow_all",
  enabledChannels: [],
};

const css = {
  label: "mb-1 block text-xs text-claude-text-muted font-medium",
  input:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-1.5 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  textarea:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 font-mono text-xs text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  select:
    "w-full rounded-lg border border-claude-border bg-claude-input px-2 py-1.5 text-sm text-claude-text-primary focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  chip: (selected: boolean) =>
    `rounded-full px-2.5 py-0.5 text-[11px] transition-colors ring-1 ${
      selected
        ? "bg-claude-accent/10 text-claude-accent ring-claude-accent/40"
        : "bg-claude-surface text-claude-text-secondary ring-claude-border hover:text-claude-text-primary"
    }`,
};

export default function AddCustomAgentTemplateModal({
  open,
  onClose,
  entryToEdit,
}: AddCustomAgentTemplateModalProps) {
  const addMutation = useAddCustomAgentTemplate();
  const updateMutation = useUpdateCustomAgentTemplate();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState("");
  const [skillQuery, setSkillQuery] = useState("");
  const [mcpQuery, setMcpQuery] = useState("");

  // Self-hosted skills only — they have local SKILL.md content. Filter to source=self-hosted.
  const { data: skillResults = [] } = useSearchSkills(skillQuery, open);
  const { data: mcpResults = [] } = useSearchMcpServers(mcpQuery, open);

  const editing = !!entryToEdit;

  useEffect(() => {
    if (!open) return;
    if (entryToEdit) {
      const idTail = entryToEdit.id.replace(/^custom-/, "");
      const defaults = entryToEdit.defaults ?? {};
      const tools = (entryToEdit.tools ?? {}) as Record<string, unknown>;
      const channels = (entryToEdit.channels ?? {}) as Record<string, unknown>;
      const enabledChannels = ALL_CHANNELS.filter((c) => {
        const cfg = channels[c];
        if (!cfg || typeof cfg !== "object") return false;
        return (cfg as { enabled?: boolean }).enabled === true;
      });
      const web = ((tools as Record<string, unknown>).web ?? {}) as {
        search?: { provider?: FormState["webProvider"] };
      };
      const exec = ((tools as Record<string, unknown>).exec ?? {}) as {
        policy?: { mode?: FormState["shellPolicyMode"] };
      };
      setForm({
        idTail,
        name: entryToEdit.name ?? "",
        description: entryToEdit.description ?? "",
        categories: (entryToEdit.categories ?? []).join(", "),
        model: defaults.model ?? "anthropic/claude-opus-4-5",
        temperature: defaults.temperature ?? 0.7,
        maxTokens: defaults.maxTokens ?? 8192,
        maxToolIterations: defaults.maxToolIterations ?? 25,
        memoryWindow: defaults.memoryWindow ?? 50,
        agentsMd: entryToEdit.agents_md ?? "",
        soulMd: entryToEdit.soul_md ?? "",
        skillIds: entryToEdit.skill_ids ?? [],
        mcpServerIds: Object.keys(entryToEdit.mcp_servers ?? {}),
        restrictToWorkspace:
          (tools as { restrict_to_workspace?: boolean }).restrict_to_workspace ?? true,
        webProvider: web.search?.provider ?? "duckduckgo",
        shellPolicyMode: exec.policy?.mode ?? "allow_all",
        enabledChannels,
      });
    } else {
      setForm(EMPTY_FORM);
    }
    setError("");
    setSkillQuery("");
    setMcpQuery("");
  }, [open, entryToEdit]);

  const derivedId = useMemo(() => {
    const tail = form.idTail || toIdSlug(form.name);
    return tail ? `custom-${tail}` : "";
  }, [form.idTail, form.name]);

  function toggleSkill(slug: string) {
    setForm((f) => ({
      ...f,
      skillIds: f.skillIds.includes(slug)
        ? f.skillIds.filter((s) => s !== slug)
        : [...f.skillIds, slug],
    }));
  }

  function toggleMcp(id: string) {
    setForm((f) => ({
      ...f,
      mcpServerIds: f.mcpServerIds.includes(id)
        ? f.mcpServerIds.filter((s) => s !== id)
        : [...f.mcpServerIds, id],
    }));
  }

  function toggleChannel(channel: ChannelKey) {
    setForm((f) => ({
      ...f,
      enabledChannels: f.enabledChannels.includes(channel)
        ? f.enabledChannels.filter((c) => c !== channel)
        : [...f.enabledChannels, channel],
    }));
  }

  function buildPayload(): CustomAgentTemplatePayload | null {
    if (!form.name.trim()) {
      setError("Name is required.");
      return null;
    }
    if (!derivedId || !/^custom-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(derivedId)) {
      setError("ID must look like `custom-<slug>` (lowercase letters, digits, dashes).");
      return null;
    }
    if (!form.agentsMd.trim()) {
      setError("Agent system prompt (AGENTS.md) is required.");
      return null;
    }

    // Build mcp_servers — preserve existing config when editing, otherwise stub from registry results.
    const mcpServers: Record<string, { command: string; args: string[]; env: Record<string, string>; url: string; headers: Record<string, string> }> = {};
    for (const id of form.mcpServerIds) {
      const existing = entryToEdit?.mcp_servers?.[id];
      if (existing) {
        mcpServers[id] = {
          command: existing.command ?? "",
          args: existing.args ?? [],
          env: existing.env ?? {},
          url: existing.url ?? "",
          headers: existing.headers ?? {},
        };
        continue;
      }
      const registryEntry = mcpResults.find((s) => s.slug === id || s.id === id);
      const installCfg = (
        Array.isArray(registryEntry?.install_config)
          ? registryEntry?.install_config?.[0]
          : registryEntry?.install_config
      ) as Record<string, unknown> | undefined;
      mcpServers[id] = {
        command: typeof installCfg?.command === "string" ? installCfg.command : "",
        args: Array.isArray(installCfg?.args) ? (installCfg!.args as string[]) : [],
        env: {},
        url: typeof installCfg?.url === "string" ? installCfg.url : "",
        headers: {},
      };
    }

    const channels: Record<string, { enabled: boolean }> = {};
    for (const c of form.enabledChannels) {
      channels[c] = { enabled: true };
    }

    return {
      id: derivedId,
      name: form.name.trim(),
      description: form.description.trim(),
      categories: form.categories
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      defaults: {
        model: form.model,
        temperature: Number(form.temperature),
        maxTokens: Number(form.maxTokens),
        maxToolIterations: Number(form.maxToolIterations),
        memoryWindow: Number(form.memoryWindow),
      },
      tools: {
        restrict_to_workspace: form.restrictToWorkspace,
        web: { search: { provider: form.webProvider } },
        exec: { policy: { mode: form.shellPolicyMode } },
      },
      channels,
      mcp_servers: mcpServers,
      skill_ids: form.skillIds,
      agents_md: form.agentsMd,
      soul_md: form.soulMd.trim() ? form.soulMd : null,
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const payload = buildPayload();
    if (!payload) return;
    try {
      if (editing && entryToEdit) {
        await updateMutation.mutateAsync({ templateId: entryToEdit.id, entry: payload });
      } else {
        await addMutation.mutateAsync(payload);
      }
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save template.");
    }
  }

  const pending = addMutation.isPending || updateMutation.isPending;

  // Self-hosted skills: only these have local SKILL.md content the backend can bake in.
  const selfHostedSkills = skillResults.filter(
    (s: MarketplaceSkill) => s.source === "self-hosted",
  );
  const selectedSkillsNotInResults = form.skillIds.filter(
    (slug) => !skillResults.some((s) => s.slug === slug),
  );
  const selectedMcpNotInResults = form.mcpServerIds.filter(
    (id) => !mcpResults.some((s: MCPRegistryServer) => s.slug === id || s.id === id),
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? "Edit Agent Template" : "Add Agent Template"}
      size="lg"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs border border-claude-border bg-claude-input hover:bg-claude-surface transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="custom-agent-template-form"
            disabled={pending || !form.name.trim() || !form.agentsMd.trim()}
            className="rounded-lg px-3 py-1.5 text-xs font-medium bg-claude-accent text-white hover:bg-claude-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {pending ? "Saving…" : editing ? "Save changes" : "Add template"}
          </button>
        </>
      }
    >
      <form id="custom-agent-template-form" onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}

        {/* Identity ------------------------------------------------------ */}
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            Identity
          </h3>
          <div>
            <label className={css.label}>
              Name <span className="text-red-500">*</span>
            </label>
            <input
              className={css.input}
              placeholder="Data Scientist"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            {derivedId && (
              <div className="mt-1 flex items-center gap-1.5">
                <span className="text-[10px] text-claude-text-muted">ID:</span>
                <span className="text-[10px] text-claude-text-muted font-mono">custom-</span>
                <input
                  className="text-[10px] font-mono text-claude-text-primary bg-transparent border-b border-claude-border focus:outline-none focus:border-claude-accent px-0.5 w-48"
                  value={form.idTail}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      idTail: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"),
                    }))
                  }
                  placeholder={toIdSlug(form.name) || "slug"}
                  disabled={editing}
                />
              </div>
            )}
          </div>
          <div>
            <label className={css.label}>Description</label>
            <textarea
              className={`${css.input} resize-none`}
              rows={2}
              placeholder="What this agent template is for"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div>
            <label className={css.label}>Categories (comma-separated)</label>
            <input
              className={css.input}
              placeholder="analytics, research"
              value={form.categories}
              onChange={(e) => setForm((f) => ({ ...f, categories: e.target.value }))}
            />
          </div>
        </section>

        {/* Defaults ------------------------------------------------------ */}
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            Agent Defaults
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={css.label}>Default model</label>
              <input
                list="custom-template-models"
                className={css.input}
                value={form.model}
                onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
              />
              <datalist id="custom-template-models">
                {DEFAULT_MODELS.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </div>
            <div>
              <label className={css.label}>Temperature</label>
              <input
                type="number"
                step={0.1}
                min={0}
                max={2}
                className={css.input}
                value={form.temperature}
                onChange={(e) =>
                  setForm((f) => ({ ...f, temperature: parseFloat(e.target.value) }))
                }
              />
            </div>
            <div>
              <label className={css.label}>Max tokens</label>
              <input
                type="number"
                min={1}
                className={css.input}
                value={form.maxTokens}
                onChange={(e) =>
                  setForm((f) => ({ ...f, maxTokens: parseInt(e.target.value, 10) || 0 }))
                }
              />
            </div>
            <div>
              <label className={css.label}>Max tool iterations</label>
              <input
                type="number"
                min={1}
                className={css.input}
                value={form.maxToolIterations}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    maxToolIterations: parseInt(e.target.value, 10) || 0,
                  }))
                }
              />
            </div>
            <div>
              <label className={css.label}>Memory window</label>
              <input
                type="number"
                min={1}
                className={css.input}
                value={form.memoryWindow}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    memoryWindow: parseInt(e.target.value, 10) || 0,
                  }))
                }
              />
            </div>
          </div>
        </section>

        {/* System prompt ------------------------------------------------ */}
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            System Prompt (AGENTS.md) <span className="text-red-500">*</span>
          </h3>
          <textarea
            className={`${css.textarea} resize-y`}
            rows={8}
            value={form.agentsMd}
            onChange={(e) => setForm((f) => ({ ...f, agentsMd: e.target.value }))}
            placeholder="# Agent Instructions"
          />
        </section>

        {/* Personality (optional) -------------------------------------- */}
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            Personality (SOUL.md, optional)
          </h3>
          <textarea
            className={`${css.textarea} resize-y`}
            rows={4}
            value={form.soulMd}
            placeholder="Optional: tone, voice, values"
            onChange={(e) => setForm((f) => ({ ...f, soulMd: e.target.value }))}
          />
        </section>

        {/* Default skills ----------------------------------------------- */}
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            Default Skills
          </h3>
          <p className="text-[11px] text-claude-text-muted">
            Self-hosted skills baked into every agent created from this template. Search the
            registry below; only self-hosted entries can be added (they have local SKILL.md
            content).
          </p>
          <input
            className={css.input}
            placeholder="Search self-hosted skills…"
            value={skillQuery}
            onChange={(e) => setSkillQuery(e.target.value)}
          />
          <div className="flex flex-wrap gap-1.5">
            {selfHostedSkills.map((s) => (
              <button
                key={s.slug}
                type="button"
                onClick={() => toggleSkill(s.slug)}
                className={css.chip(form.skillIds.includes(s.slug))}
                title={s.description}
              >
                {s.name || s.slug}
              </button>
            ))}
            {selfHostedSkills.length === 0 && skillQuery && (
              <span className="text-[11px] text-claude-text-muted italic">
                No self-hosted skills matched. Add one in the Skills tab first.
              </span>
            )}
          </div>
          {selectedSkillsNotInResults.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {selectedSkillsNotInResults.map((slug) => (
                <button
                  key={slug}
                  type="button"
                  onClick={() => toggleSkill(slug)}
                  className={css.chip(true)}
                  title="Currently selected (not in current search results)"
                >
                  {slug} ✕
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Default MCP servers ----------------------------------------- */}
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            Default MCP Servers
          </h3>
          <input
            className={css.input}
            placeholder="Search MCP registry…"
            value={mcpQuery}
            onChange={(e) => setMcpQuery(e.target.value)}
          />
          <div className="flex flex-wrap gap-1.5">
            {mcpResults.map((s) => {
              const id = s.slug || s.id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggleMcp(id)}
                  className={css.chip(form.mcpServerIds.includes(id))}
                  title={s.description}
                >
                  {s.name || id}
                </button>
              );
            })}
          </div>
          {selectedMcpNotInResults.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {selectedMcpNotInResults.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggleMcp(id)}
                  className={css.chip(true)}
                >
                  {id} ✕
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Tools --------------------------------------------------------- */}
        <section className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            Tools
          </h3>
          <label className="flex items-center gap-2 text-xs text-claude-text-secondary">
            <input
              type="checkbox"
              checked={form.restrictToWorkspace}
              onChange={(e) =>
                setForm((f) => ({ ...f, restrictToWorkspace: e.target.checked }))
              }
            />
            Restrict filesystem tools to workspace
          </label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={css.label}>Web search provider</label>
              <select
                className={css.select}
                value={form.webProvider}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    webProvider: e.target.value as FormState["webProvider"],
                  }))
                }
              >
                {WEB_PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={css.label}>Shell exec policy</label>
              <select
                className={css.select}
                value={form.shellPolicyMode}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    shellPolicyMode: e.target.value as FormState["shellPolicyMode"],
                  }))
                }
              >
                {SHELL_POLICY_MODES.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {/* Channels ------------------------------------------------------ */}
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-claude-text-muted">
            Channels
          </h3>
          <p className="text-[11px] text-claude-text-muted">
            Toggle which messaging channels are enabled by default. Credentials must still be
            filled in per-agent after creation.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {ALL_CHANNELS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => toggleChannel(c)}
                className={css.chip(form.enabledChannels.includes(c))}
              >
                {c}
              </button>
            ))}
          </div>
        </section>

        <div className="flex items-center justify-end gap-2 pt-2">
          {editing && (
            <span className="text-[11px] text-claude-text-muted">
              <TrashIcon className="inline h-3 w-3 mr-1 align-middle" />
              Delete from the templates tab
            </span>
          )}
        </div>
      </form>
    </Modal>
  );
}
