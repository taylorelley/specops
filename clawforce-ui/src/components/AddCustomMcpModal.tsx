import { useEffect, useState } from "react";
import Modal from "./Modal";
import { useAddCustomMcpServer, useUpdateCustomMcpServer } from "../lib/queries";
import type { AddCustomMcpPayload, CustomMcpEntry } from "../lib/types";

interface AddCustomMcpModalProps {
  open: boolean;
  onClose: () => void;
  entryToEdit?: CustomMcpEntry | null;
}

type Transport = "stdio" | "http";

function toSlug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

type FormState = {
  slug: string;
  name: string;
  description: string;
  author: string;
  version: string;
  categories: string;
  homepage: string;
  repository: string;
  requiredEnv: string;
  transport: Transport;
  command: string;
  args: string;
  url: string;
};

const EMPTY_FORM: FormState = {
  slug: "",
  name: "",
  description: "",
  author: "",
  version: "",
  categories: "",
  homepage: "",
  repository: "",
  requiredEnv: "",
  transport: "stdio",
  command: "npx",
  args: "-y\n@org/your-mcp",
  url: "",
};

const css = {
  label: "mb-1 block text-xs text-claude-text-muted font-medium",
  input:
    "w-full rounded-lg border border-claude-border bg-white px-3 py-1.5 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  textarea:
    "w-full rounded-lg border border-claude-border bg-white px-3 py-2 text-xs font-mono text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

function deriveTransport(entry: CustomMcpEntry | null | undefined): Transport {
  if (!entry) return "stdio";
  return "url" in entry.install_config ? "http" : "stdio";
}

export default function AddCustomMcpModal({ open, onClose, entryToEdit }: AddCustomMcpModalProps) {
  const addMutation = useAddCustomMcpServer();
  const updateMutation = useUpdateCustomMcpServer();

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [slugOverride, setSlugOverride] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    if (entryToEdit) {
      const transport = deriveTransport(entryToEdit);
      const cfg = entryToEdit.install_config;
      setForm({
        slug: entryToEdit.slug,
        name: entryToEdit.name ?? "",
        description: entryToEdit.description ?? "",
        author: entryToEdit.author ?? "",
        version: entryToEdit.version ?? "",
        categories: (entryToEdit.categories ?? []).join(", "),
        homepage: entryToEdit.homepage ?? "",
        repository: entryToEdit.repository ?? "",
        requiredEnv: (entryToEdit.required_env ?? []).join("\n"),
        transport,
        command: transport === "stdio" && "command" in cfg ? cfg.command : "",
        args: transport === "stdio" && "args" in cfg ? cfg.args.join("\n") : "",
        url: transport === "http" && "url" in cfg ? cfg.url : "",
      });
      setSlugOverride(entryToEdit.slug);
    } else {
      setForm(EMPTY_FORM);
      setSlugOverride("");
    }
    setError("");
  }, [open, entryToEdit]);

  const derivedSlug = slugOverride || toSlug(form.name);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const slug = derivedSlug;
    const name = form.name.trim();
    if (!name) {
      setError("Name is required.");
      return;
    }
    if (!slug) {
      setError("Slug is required.");
      return;
    }
    if (!/^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$/.test(slug)) {
      setError("Slug must be lowercase letters, digits, dashes or underscores.");
      return;
    }

    let install_config: AddCustomMcpPayload["install_config"];
    if (form.transport === "stdio") {
      const command = form.command.trim();
      if (!command) {
        setError("Command is required for stdio transport.");
        return;
      }
      const args = form.args
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      install_config = { command, args };
    } else {
      const url = form.url.trim();
      if (!url) {
        setError("URL is required for http transport.");
        return;
      }
      if (!/^https?:\/\//i.test(url)) {
        setError("URL must start with http:// or https://");
        return;
      }
      install_config = { url };
    }

    const payload: AddCustomMcpPayload = {
      slug,
      name,
      description: form.description.trim(),
      author: form.author.trim(),
      version: form.version.trim(),
      categories: form.categories
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      homepage: form.homepage.trim(),
      repository: form.repository.trim(),
      required_env: form.requiredEnv
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean),
      install_config,
    };

    try {
      if (entryToEdit) {
        await updateMutation.mutateAsync({ slug: entryToEdit.slug, entry: payload });
      } else {
        await addMutation.mutateAsync(payload);
      }
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save MCP server.");
    }
  }

  const pending = addMutation.isPending || updateMutation.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={entryToEdit ? "Edit Self-Hosted MCP Server" : "Add Self-Hosted MCP Server"}
      size="lg"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs border border-claude-border bg-white hover:bg-claude-surface transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="custom-mcp-form"
            disabled={pending || !form.name.trim()}
            className="rounded-lg px-3 py-1.5 text-xs font-medium bg-claude-accent text-white hover:bg-claude-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {pending ? "Saving…" : entryToEdit ? "Save changes" : "Add MCP server"}
          </button>
        </>
      }
    >
      <form id="custom-mcp-form" onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className={css.label}>Name *</label>
            <input
              className={css.input}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Internal Postgres MCP"
              autoFocus
            />
          </div>
          <div>
            <label className={css.label}>Slug *</label>
            <input
              className={css.input}
              value={derivedSlug}
              onChange={(e) => setSlugOverride(e.target.value)}
              placeholder="internal-postgres-mcp"
              disabled={!!entryToEdit}
            />
            <p className="mt-1 text-[10px] text-claude-text-muted">
              Lowercase letters, digits, dashes, or underscores.
            </p>
          </div>
        </div>

        <div>
          <label className={css.label}>Description</label>
          <input
            className={css.input}
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="Short summary shown in the marketplace."
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className={css.label}>Author</label>
            <input
              className={css.input}
              value={form.author}
              onChange={(e) => setForm((f) => ({ ...f, author: e.target.value }))}
              placeholder="Platform Team"
            />
          </div>
          <div>
            <label className={css.label}>Version</label>
            <input
              className={css.input}
              value={form.version}
              onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))}
              placeholder="1.0.0"
            />
          </div>
          <div>
            <label className={css.label}>Categories</label>
            <input
              className={css.input}
              value={form.categories}
              onChange={(e) => setForm((f) => ({ ...f, categories: e.target.value }))}
              placeholder="data, internal"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className={css.label}>Homepage</label>
            <input
              className={css.input}
              value={form.homepage}
              onChange={(e) => setForm((f) => ({ ...f, homepage: e.target.value }))}
              placeholder="https://…"
            />
          </div>
          <div>
            <label className={css.label}>Repository</label>
            <input
              className={css.input}
              value={form.repository}
              onChange={(e) => setForm((f) => ({ ...f, repository: e.target.value }))}
              placeholder="https://github.com/…"
            />
          </div>
        </div>

        <div>
          <label className={css.label}>Transport *</label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setForm((f) => ({ ...f, transport: "stdio" }))}
              className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${
                form.transport === "stdio"
                  ? "border-claude-accent bg-claude-accent/5 text-claude-text-primary"
                  : "border-claude-border bg-white text-claude-text-secondary hover:bg-claude-surface"
              }`}
            >
              stdio (command)
            </button>
            <button
              type="button"
              onClick={() => setForm((f) => ({ ...f, transport: "http" }))}
              className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${
                form.transport === "http"
                  ? "border-claude-accent bg-claude-accent/5 text-claude-text-primary"
                  : "border-claude-border bg-white text-claude-text-secondary hover:bg-claude-surface"
              }`}
            >
              http (URL)
            </button>
          </div>
        </div>

        {form.transport === "stdio" ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className={css.label}>Command *</label>
              <input
                className={css.input}
                value={form.command}
                onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                placeholder="npx"
              />
            </div>
            <div className="md:col-span-2">
              <label className={css.label}>Arguments (one per line)</label>
              <textarea
                className={css.textarea}
                rows={4}
                value={form.args}
                onChange={(e) => setForm((f) => ({ ...f, args: e.target.value }))}
                placeholder={"-y\n@org/your-mcp"}
                spellCheck={false}
              />
            </div>
          </div>
        ) : (
          <div>
            <label className={css.label}>URL *</label>
            <input
              className={css.input}
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              placeholder="https://mcp.example.com/sse"
            />
          </div>
        )}

        <div>
          <label className={css.label}>Required env vars (one per line)</label>
          <textarea
            className={css.textarea}
            rows={3}
            value={form.requiredEnv}
            onChange={(e) => setForm((f) => ({ ...f, requiredEnv: e.target.value }))}
            placeholder="DATABASE_URL"
          />
          <p className="mt-1 text-[10px] text-claude-text-muted">
            These are prompted when a user installs the server to an agent.
          </p>
        </div>
      </form>
    </Modal>
  );
}
