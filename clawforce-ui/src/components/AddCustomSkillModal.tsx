import { useEffect, useState } from "react";
import Modal from "./Modal";
import { useAddCustomSkill, useUpdateCustomSkill } from "../lib/queries";
import type { AddCustomSkillPayload, CustomSkillEntry } from "../lib/types";

interface AddCustomSkillModalProps {
  open: boolean;
  onClose: () => void;
  entryToEdit?: CustomSkillEntry | null;
}

const SAMPLE_SKILL_MD = `---
name: my-skill
description: Short description shown in the agent's skill list
metadata: {"clawbot":{"emoji":"🛠️"}}
---

# My Skill

Describe what this skill does and how the agent should use it.

## Usage

Explain the trigger, inputs, and expected outputs.
`;

function toSlug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Verify the content starts with a `---` frontmatter block, contains a closing
 * `---` delimiter, and declares at least `name:` and `description:` inside it.
 * Returns a human-readable error string, or "" when the content passes.
 */
function validateFrontmatter(content: string): string {
  const lines = content.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") {
    return "SKILL.md must begin with a '---' YAML frontmatter block.";
  }
  const closingIdx = lines.findIndex((line, i) => i > 0 && line.trim() === "---");
  if (closingIdx === -1) {
    return "SKILL.md frontmatter is missing its closing '---' delimiter.";
  }
  const body = lines.slice(1, closingIdx);
  const keys = new Set<string>();
  for (const line of body) {
    const match = /^([A-Za-z0-9_-]+)\s*:/.exec(line);
    if (match) keys.add(match[1].toLowerCase());
  }
  if (!keys.has("name")) {
    return "SKILL.md frontmatter must include a 'name:' field.";
  }
  if (!keys.has("description")) {
    return "SKILL.md frontmatter must include a 'description:' field.";
  }
  return "";
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
  skillContent: string;
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
  skillContent: "",
};

const css = {
  label: "mb-1 block text-xs text-claude-text-muted font-medium",
  input:
    "w-full rounded-lg border border-claude-border bg-white px-3 py-1.5 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  textarea:
    "w-full rounded-lg border border-claude-border bg-white px-3 py-2 text-xs font-mono text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

export default function AddCustomSkillModal({ open, onClose, entryToEdit }: AddCustomSkillModalProps) {
  const addMutation = useAddCustomSkill();
  const updateMutation = useUpdateCustomSkill();

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [slugOverride, setSlugOverride] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    if (entryToEdit) {
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
        skillContent: entryToEdit.skill_content ?? "",
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
    const description = form.description.trim();
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
    const content = form.skillContent.trim();
    if (!content) {
      setError("SKILL.md content is required.");
      return;
    }
    const frontmatterError = validateFrontmatter(content);
    if (frontmatterError) {
      setError(frontmatterError);
      return;
    }

    const payload: AddCustomSkillPayload = {
      slug,
      name,
      description,
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
      skill_content: content,
    };

    try {
      if (entryToEdit) {
        await updateMutation.mutateAsync({ slug: entryToEdit.slug, entry: payload });
      } else {
        await addMutation.mutateAsync(payload);
      }
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save skill.");
    }
  }

  const pending = addMutation.isPending || updateMutation.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={entryToEdit ? "Edit Self-Hosted Skill" : "Add Self-Hosted Skill"}
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
            form="custom-skill-form"
            disabled={pending || !form.name.trim() || !form.skillContent.trim()}
            className="rounded-lg px-3 py-1.5 text-xs font-medium bg-claude-accent text-white hover:bg-claude-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {pending ? "Saving…" : entryToEdit ? "Save changes" : "Add skill"}
          </button>
        </>
      }
    >
      <form id="custom-skill-form" onSubmit={handleSubmit} className="space-y-4">
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
              placeholder="PDF Helper"
              autoFocus
            />
          </div>
          <div>
            <label className={css.label}>Slug *</label>
            <input
              className={css.input}
              value={derivedSlug}
              onChange={(e) => setSlugOverride(e.target.value)}
              placeholder="pdf-helper"
              disabled={!!entryToEdit}
            />
            <p className="mt-1 text-[10px] text-claude-text-muted">
              Used as the skill directory name under
              <code className="mx-1">.agents/skills/</code>.
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
              placeholder="docs, internal"
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
          <label className={css.label}>Required env vars (one per line)</label>
          <textarea
            className={css.textarea}
            rows={3}
            value={form.requiredEnv}
            onChange={(e) => setForm((f) => ({ ...f, requiredEnv: e.target.value }))}
            placeholder="OPENAI_API_KEY"
          />
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label className={css.label}>SKILL.md content *</label>
            {!form.skillContent && (
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, skillContent: SAMPLE_SKILL_MD }))}
                className="text-[10px] text-claude-accent hover:underline"
              >
                Insert template
              </button>
            )}
          </div>
          <textarea
            className={css.textarea}
            rows={14}
            value={form.skillContent}
            onChange={(e) => setForm((f) => ({ ...f, skillContent: e.target.value }))}
            placeholder={SAMPLE_SKILL_MD}
            spellCheck={false}
          />
          <p className="mt-1 text-[10px] text-claude-text-muted">
            Must begin with a <code>---</code> YAML frontmatter block containing at least
            <code className="mx-1">name</code> and <code>description</code>.
          </p>
        </div>
      </form>
    </Modal>
  );
}
