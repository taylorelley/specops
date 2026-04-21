import { useEffect, useMemo, useState } from "react";
import Modal from "./Modal";
import { PlanIcon } from "./ui";
import { useCreatePlan, usePlanTemplates } from "../lib/queries";
import type { PlanTemplate } from "../lib/types";

interface CreatePlanModalProps {
  open: boolean;
  onClose: () => void;
  /** Pre-select this template and switch the modal into "From Template" mode. */
  initialTemplateId?: string;
  /** Called with the new plan id after successful creation. Defaults to just closing. */
  onPlanCreated?: (planId: string) => void;
}

type Mode = "blank" | "template";

const css = {
  label: "mb-1 block text-xs text-claude-text-muted font-medium",
  input:
    "w-full rounded-lg border border-claude-border bg-white px-3 py-2 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  select:
    "w-full rounded-lg border border-claude-border bg-white px-3 py-2 text-sm text-claude-text-primary focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

function pillClass(active: boolean): string {
  return `flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
    active
      ? "bg-white text-claude-text-primary shadow-sm"
      : "text-claude-text-muted hover:text-claude-text-secondary"
  }`;
}

export default function CreatePlanModal({ open, onClose, initialTemplateId, onPlanCreated }: CreatePlanModalProps) {
  const [mode, setMode] = useState<Mode>("blank");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [templateId, setTemplateId] = useState<string>("");
  const [nameTouched, setNameTouched] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const createPlan = useCreatePlan();
  const { data: templates = [] } = usePlanTemplates();

  useEffect(() => {
    if (!open) return;
    if (initialTemplateId) {
      setMode("template");
      setTemplateId(initialTemplateId);
    } else {
      setMode("blank");
      setTemplateId("");
    }
    setName("");
    setDescription("");
    setNameTouched(false);
    setSubmitError("");
  }, [open, initialTemplateId]);

  const selectedTemplate = useMemo<PlanTemplate | null>(
    () => templates.find((t) => t.id === templateId) ?? null,
    [templates, templateId],
  );

  // Auto-fill name from template if the user hasn't customised it.
  useEffect(() => {
    if (mode !== "template") return;
    if (nameTouched) return;
    if (selectedTemplate) setName(selectedTemplate.name);
  }, [mode, selectedTemplate, nameTouched]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError("");
    const trimmed = name.trim();
    if (!trimmed) return;
    const payload: { name: string; description?: string; template_id?: string } = {
      name: trimmed,
      description: description.trim(),
    };
    if (mode === "template" && templateId) payload.template_id = templateId;
    try {
      const plan = await createPlan.mutateAsync(payload);
      onClose();
      if (onPlanCreated) onPlanCreated(plan.id);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create plan.");
    }
  }

  const taskCount = selectedTemplate?.tasks?.length ?? 0;
  const colCount = selectedTemplate?.columns?.length ?? 0;

  return (
    <Modal open={open} onClose={onClose} title="Create Plan" icon={<PlanIcon className="h-4 w-4" />} size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        {submitError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {submitError}
          </div>
        )}
        <div className="flex rounded-lg border border-claude-border bg-claude-surface p-0.5">
          <button
            type="button"
            className={pillClass(mode === "blank")}
            onClick={() => {
              setMode("blank");
              setTemplateId("");
            }}
          >
            Blank Plan
          </button>
          <button
            type="button"
            className={pillClass(mode === "template")}
            onClick={() => setMode("template")}
          >
            From Template
          </button>
        </div>

        {mode === "template" && (
          <div>
            <label className={css.label}>Template</label>
            <select
              className={css.select}
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
            >
              <option value="">Select a template…</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            {selectedTemplate && (
              <div className="mt-2 rounded-lg border border-claude-border bg-claude-surface/50 p-3 text-xs text-claude-text-secondary space-y-1.5">
                {selectedTemplate.description && (
                  <p className="line-clamp-2">{selectedTemplate.description}</p>
                )}
                <p className="text-[11px] text-claude-text-muted">
                  {colCount > 0 ? `${colCount} columns` : "Default 4 columns"} · {taskCount} tasks
                </p>
              </div>
            )}
          </div>
        )}

        <div>
          <label className={css.label}>Plan Name</label>
          <input
            type="text"
            placeholder="e.g. Q1 launch"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setNameTouched(true);
            }}
            autoFocus
            className={css.input}
          />
        </div>
        <div>
          <label className={css.label}>Description</label>
          <textarea
            placeholder="What is this plan for?"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className={`${css.input} resize-none`}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-sm text-claude-text-muted hover:text-claude-text-secondary transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={
              !name.trim() ||
              createPlan.isPending ||
              (mode === "template" && !templateId)
            }
            className="rounded-lg bg-claude-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-claude-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {createPlan.isPending ? "Creating…" : "Create Plan"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
