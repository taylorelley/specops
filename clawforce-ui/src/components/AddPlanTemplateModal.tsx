import { useEffect, useMemo, useState } from "react";
import Modal from "./Modal";
import { PlanIcon, TrashIcon } from "./ui";
import { useAddCustomPlanTemplate, useClaws, useUpdateCustomPlanTemplate } from "../lib/queries";
import type { AddPlanTemplatePayload, PlanTemplate, PlanTemplateColumn, PlanTemplateTask } from "../lib/types";

interface AddPlanTemplateModalProps {
  open: boolean;
  onClose: () => void;
  entryToEdit?: PlanTemplate | null;
}

const DEFAULT_COLUMNS = ["Todo", "In Progress", "Blocked", "Done"];

function toSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Accept either a slug ("in-progress") or a human title ("In Progress") as input and
 * return the slug that matches one of the available columns, or "" if no match.
 * Makes the edit form tolerant of templates authored directly in YAML.
 */
function normalizeColumn(raw: string | undefined, availableTitles: string[]): string {
  if (!raw) return "";
  const slugs = availableTitles.map((t) => toSlug(t));
  const lower = raw.toLowerCase();
  // Already a matching slug
  const slugHit = slugs.find((s) => s === lower);
  if (slugHit) return slugHit;
  // Match by title (case-insensitive)
  const idx = availableTitles.findIndex((t) => t.toLowerCase() === lower);
  if (idx >= 0) return slugs[idx];
  return "";
}

function emptyTask(firstColumn: string): PlanTemplateTask {
  return { title: "", description: "", column: firstColumn, agent_id: "" };
}

type FormState = {
  name: string;
  description: string;
  author: string;
  categories: string;
  columns: PlanTemplateColumn[];
  tasks: PlanTemplateTask[];
  agentIds: string[];
};

const EMPTY_FORM: FormState = {
  name: "",
  description: "",
  author: "",
  categories: "",
  columns: [],
  tasks: [{ title: "", description: "", column: "todo", agent_id: "" }],
  agentIds: [],
};

const css = {
  label: "mb-1 block text-xs text-claude-text-muted font-medium",
  input:
    "w-full rounded-lg border border-claude-border bg-white px-3 py-1.5 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  select:
    "rounded-lg border border-claude-border bg-white px-2 py-1 text-xs text-claude-text-primary focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

export default function AddPlanTemplateModal({ open, onClose, entryToEdit }: AddPlanTemplateModalProps) {
  const addMutation = useAddCustomPlanTemplate();
  const updateMutation = useUpdateCustomPlanTemplate();
  const { data: claws = [] } = useClaws();

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [idOverride, setIdOverride] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    if (entryToEdit) {
      const editColumns = entryToEdit.columns ?? [];
      const editAvailableTitles =
        editColumns.length > 0 ? editColumns.map((c) => c.title) : DEFAULT_COLUMNS;
      setForm({
        name: entryToEdit.name ?? "",
        description: entryToEdit.description ?? "",
        author: entryToEdit.author ?? "",
        categories: (entryToEdit.categories ?? []).join(", "),
        columns: editColumns,
        tasks:
          entryToEdit.tasks && entryToEdit.tasks.length > 0
            ? entryToEdit.tasks.map((t) => ({
                title: t.title ?? "",
                description: t.description ?? "",
                column: normalizeColumn(t.column, editAvailableTitles),
                agent_id: t.agent_id ?? "",
              }))
            : [{ title: "", description: "", column: "todo", agent_id: "" }],
        agentIds: entryToEdit.agent_ids ?? [],
      });
      setIdOverride(entryToEdit.id ?? "");
    } else {
      setForm(EMPTY_FORM);
      setIdOverride("");
    }
    setError("");
  }, [open, entryToEdit]);

  const derivedId = idOverride || toSlug(form.name);

  // Columns available to reference from a task — template columns if provided, else defaults
  const availableColumns = useMemo(() => {
    if (form.columns.length > 0) return form.columns.map((c) => c.title);
    return DEFAULT_COLUMNS;
  }, [form.columns]);

  function addColumn() {
    setForm((f) => ({
      ...f,
      columns: [...f.columns, { title: "", position: f.columns.length }],
    }));
  }

  function removeColumn(idx: number) {
    setForm((f) => ({
      ...f,
      columns: f.columns.filter((_, i) => i !== idx).map((c, i) => ({ ...c, position: i })),
    }));
  }

  function updateColumn(idx: number, patch: Partial<PlanTemplateColumn>) {
    setForm((f) => ({
      ...f,
      columns: f.columns.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
    }));
  }

  function addTask() {
    setForm((f) => ({
      ...f,
      tasks: [...f.tasks, emptyTask(availableColumns[0] ? toSlug(availableColumns[0]) : "todo")],
    }));
  }

  function removeTask(idx: number) {
    setForm((f) => ({ ...f, tasks: f.tasks.filter((_, i) => i !== idx) }));
  }

  function updateTask(idx: number, patch: Partial<PlanTemplateTask>) {
    setForm((f) => ({ ...f, tasks: f.tasks.map((t, i) => (i === idx ? { ...t, ...patch } : t)) }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const id = derivedId;
    if (!id || !form.name.trim()) {
      setError("Name is required.");
      return;
    }
    const cleanedTasks = form.tasks
      .filter((t) => (t.title ?? "").trim())
      .map((t) => ({
        title: t.title.trim(),
        description: (t.description ?? "").trim(),
        column: (t.column ?? "").trim() || toSlug(availableColumns[0] ?? "todo"),
        agent_id: (t.agent_id ?? "").trim(),
      }));
    if (cleanedTasks.length === 0) {
      setError("Add at least one task.");
      return;
    }
    const cleanedColumns = form.columns
      .filter((c) => c.title.trim())
      .map((c, i) => ({ title: c.title.trim(), position: c.position ?? i }));

    const payload: AddPlanTemplatePayload = {
      id,
      name: form.name.trim(),
      description: form.description.trim(),
      author: form.author.trim(),
      categories: form.categories
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      columns: cleanedColumns,
      tasks: cleanedTasks,
      agent_ids: form.agentIds.filter(Boolean),
    };
    try {
      if (entryToEdit) {
        await updateMutation.mutateAsync({ templateId: entryToEdit.id, entry: payload });
      } else {
        await addMutation.mutateAsync(payload);
      }
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save plan template.");
    }
  }

  const pending = addMutation.isPending || updateMutation.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={entryToEdit ? "Edit Plan Template" : "Add Plan Template"}
      icon={<PlanIcon className="h-4 w-4" />}
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
            form="plan-template-form"
            disabled={pending || !form.name.trim()}
            className="rounded-lg px-3 py-1.5 text-xs font-medium bg-claude-accent text-white hover:bg-claude-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {pending ? "Saving…" : entryToEdit ? "Save changes" : "Add template"}
          </button>
        </>
      }
    >
      <form id="plan-template-form" onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}

        <div>
          <label className={css.label}>
            Name <span className="text-red-500">*</span>
          </label>
          <input
            className={css.input}
            placeholder="My plan template"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          {form.name && (
            <div className="mt-1 flex items-center gap-1.5">
              <span className="text-[10px] text-claude-text-muted">ID:</span>
              {idOverride ? (
                <input
                  className="text-[10px] font-mono text-claude-text-primary bg-transparent border-b border-claude-border focus:outline-none focus:border-claude-accent px-0.5 w-40"
                  value={idOverride}
                  onChange={(e) =>
                    setIdOverride(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))
                  }
                  disabled={!!entryToEdit}
                />
              ) : (
                <span className="text-[10px] font-mono text-claude-text-primary">{derivedId}</span>
              )}
              {!entryToEdit && (
                <button
                  type="button"
                  onClick={() => setIdOverride(idOverride ? "" : derivedId)}
                  className="text-[10px] text-claude-accent hover:underline"
                >
                  {idOverride ? "reset" : "edit"}
                </button>
              )}
            </div>
          )}
        </div>

        <div>
          <label className={css.label}>Description</label>
          <textarea
            className={`${css.input} resize-none`}
            rows={2}
            placeholder="What is this template for?"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={css.label}>Author</label>
            <input
              className={css.input}
              placeholder="Your team or name"
              value={form.author}
              onChange={(e) => setForm((f) => ({ ...f, author: e.target.value }))}
            />
          </div>
          <div>
            <label className={css.label}>Categories (comma-separated)</label>
            <input
              className={css.input}
              placeholder="product, engineering"
              value={form.categories}
              onChange={(e) => setForm((f) => ({ ...f, categories: e.target.value }))}
            />
          </div>
        </div>

        <div>
          <label className={css.label}>Preassigned agents</label>
          <p className="text-[11px] text-claude-text-muted mb-2">
            Agents to auto-assign to every plan created from this template. Missing agents are
            skipped at plan creation time.
          </p>
          {claws.length === 0 ? (
            <p className="text-[11px] text-claude-text-muted italic">
              No claws available yet. Create a claw first to preassign it here.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {claws.map((c) => {
                const selected = form.agentIds.includes(c.id);
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        agentIds: selected
                          ? f.agentIds.filter((a) => a !== c.id)
                          : [...f.agentIds, c.id],
                      }))
                    }
                    className={`rounded-full px-2.5 py-0.5 text-[11px] transition-colors ring-1 ${
                      selected
                        ? "bg-claude-accent/10 text-claude-accent ring-claude-accent/40"
                        : "bg-claude-surface text-claude-text-secondary ring-claude-border hover:text-claude-text-primary"
                    }`}
                    title={c.id}
                  >
                    {c.name || c.id}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className={css.label}>Columns</label>
            <button
              type="button"
              onClick={addColumn}
              className="text-[11px] text-claude-accent hover:underline"
            >
              + Add column
            </button>
          </div>
          <p className="text-[11px] text-claude-text-muted mb-2">
            Leave empty to use the defaults (Todo, In Progress, Blocked, Done).
          </p>
          {form.columns.length === 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {DEFAULT_COLUMNS.map((t) => (
                <span
                  key={t}
                  className="rounded-full px-2 py-0.5 text-[10px] bg-claude-surface text-claude-text-secondary"
                >
                  {t}
                </span>
              ))}
            </div>
          ) : (
            <ul className="space-y-1.5">
              {form.columns.map((col, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="w-6 text-right text-[10px] text-claude-text-muted">{i + 1}.</span>
                  <input
                    className={css.input}
                    placeholder={`Column ${i + 1} title`}
                    value={col.title}
                    onChange={(e) => updateColumn(i, { title: e.target.value })}
                  />
                  <button
                    type="button"
                    onClick={() => removeColumn(i)}
                    className="text-claude-border-strong hover:text-red-500"
                    title="Remove column"
                  >
                    <TrashIcon className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className={css.label}>Tasks</label>
            <button
              type="button"
              onClick={addTask}
              className="text-[11px] text-claude-accent hover:underline"
            >
              + Add task
            </button>
          </div>
          <ul className="space-y-2">
            {form.tasks.map((task, i) => (
              <li
                key={i}
                className="rounded-lg border border-claude-border bg-claude-surface/40 p-2.5 space-y-1.5"
              >
                <div className="flex items-start gap-2">
                  <input
                    className={css.input}
                    placeholder="Task title"
                    value={task.title}
                    onChange={(e) => updateTask(i, { title: e.target.value })}
                  />
                  <select
                    className={css.select}
                    value={task.column ?? ""}
                    onChange={(e) => updateTask(i, { column: e.target.value })}
                  >
                    {availableColumns.map((colTitle) => (
                      <option key={colTitle} value={toSlug(colTitle)}>
                        {colTitle}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => removeTask(i)}
                    className="text-claude-border-strong hover:text-red-500 mt-1.5"
                    title="Remove task"
                  >
                    <TrashIcon className="h-3.5 w-3.5" />
                  </button>
                </div>
                <textarea
                  className={`${css.input} resize-none`}
                  rows={2}
                  placeholder="Description (optional)"
                  value={task.description ?? ""}
                  onChange={(e) => updateTask(i, { description: e.target.value })}
                />
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-claude-text-muted">Assign to:</span>
                  <select
                    className={css.select}
                    value={task.agent_id ?? ""}
                    onChange={(e) => updateTask(i, { agent_id: e.target.value })}
                  >
                    <option value="">Unassigned</option>
                    {claws.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name || c.id}
                      </option>
                    ))}
                  </select>
                  {task.agent_id && !claws.some((c) => c.id === task.agent_id) && (
                    <span className="text-[10px] text-amber-600" title="Agent no longer exists">
                      stale: {task.agent_id}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </form>
    </Modal>
  );
}
