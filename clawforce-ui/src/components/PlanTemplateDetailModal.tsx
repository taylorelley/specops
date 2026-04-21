import Modal from "./Modal";
import { PlanIcon } from "./ui";
import { usePlanTemplates } from "../lib/queries";
import type { PlanTemplate, PlanTemplateTask } from "../lib/types";

interface PlanTemplateDetailModalProps {
  open: boolean;
  templateId: string | null;
  onClose: () => void;
  onUseTemplate: (templateId: string) => void;
}

function resolveColumnTitle(template: PlanTemplate, column?: string): string {
  if (!column) return template.columns?.[0]?.title ?? "Todo";
  const byTitle = template.columns?.find(
    (c) => c.title.toLowerCase() === column.toLowerCase(),
  );
  if (byTitle) return byTitle.title;
  const bySlug = template.columns?.find(
    (c) => c.title.toLowerCase().replace(/\s+/g, "-") === column.toLowerCase(),
  );
  if (bySlug) return bySlug.title;
  // Default-columns short names
  const defaults: Record<string, string> = {
    todo: "Todo",
    "in-progress": "In Progress",
    blocked: "Blocked",
    done: "Done",
  };
  return defaults[column.toLowerCase()] ?? column;
}

function groupTasksByColumn(template: PlanTemplate): Array<{ title: string; tasks: PlanTemplateTask[] }> {
  const columns =
    template.columns && template.columns.length > 0
      ? template.columns.map((c) => c.title)
      : ["Todo", "In Progress", "Blocked", "Done"];
  const groups: Record<string, PlanTemplateTask[]> = Object.fromEntries(
    columns.map((t) => [t, [] as PlanTemplateTask[]]),
  );
  for (const task of template.tasks ?? []) {
    const col = resolveColumnTitle(template, task.column);
    if (!groups[col]) groups[col] = [];
    groups[col].push(task);
  }
  return columns.map((title) => ({ title, tasks: groups[title] ?? [] }));
}

export default function PlanTemplateDetailModal({
  open,
  templateId,
  onClose,
  onUseTemplate,
}: PlanTemplateDetailModalProps) {
  const { data: templates = [] } = usePlanTemplates();
  const template = templates.find((t) => t.id === templateId) ?? null;

  if (!template) {
    return (
      <Modal open={open} onClose={onClose} title="Plan Template" icon={<PlanIcon className="h-4 w-4" />} size="lg">
        <p className="text-sm text-claude-text-muted">Loading template…</p>
      </Modal>
    );
  }

  const grouped = groupTasksByColumn(template);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={template.name}
      icon={<PlanIcon className="h-4 w-4" />}
      size="lg"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs border border-claude-border bg-white hover:bg-claude-surface transition-colors"
          >
            Close
          </button>
          <button
            type="button"
            onClick={() => onUseTemplate(template.id)}
            className="rounded-lg px-3 py-1.5 text-xs font-medium bg-claude-accent text-white hover:bg-claude-accent-hover transition-colors"
          >
            Use this template
          </button>
        </>
      }
    >
      <div className="space-y-5">
        {template.description && (
          <p className="text-sm text-claude-text-secondary whitespace-pre-wrap">{template.description}</p>
        )}

        <div className="flex flex-wrap gap-3 text-xs text-claude-text-muted">
          {template.author && (
            <span>
              <span className="text-claude-text-muted">Author:</span>{" "}
              <span className="text-claude-text-primary">{template.author}</span>
            </span>
          )}
          <span>
            <span className="text-claude-text-muted">ID:</span>{" "}
            <code className="font-mono text-claude-text-primary">{template.id}</code>
          </span>
        </div>

        {template.categories && template.categories.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {template.categories.map((c) => (
              <span
                key={c}
                className="rounded-full px-2 py-0.5 text-[10px] bg-claude-surface text-claude-text-secondary"
              >
                {c}
              </span>
            ))}
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold text-claude-text-muted uppercase tracking-wide mb-2">
            Board preview
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {grouped.map((col) => (
              <div key={col.title} className="rounded-lg border border-claude-border bg-claude-surface/40 p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-claude-text-primary">{col.title}</span>
                  <span className="text-[10px] text-claude-text-muted">{col.tasks.length}</span>
                </div>
                {col.tasks.length === 0 ? (
                  <p className="text-[11px] text-claude-text-muted italic">No tasks</p>
                ) : (
                  <ul className="space-y-1.5">
                    {col.tasks.map((t, i) => (
                      <li
                        key={`${col.title}-${i}`}
                        className="rounded border border-claude-border bg-white px-2 py-1.5"
                      >
                        <div className="text-xs font-medium text-claude-text-primary">{t.title}</div>
                        {t.description && (
                          <div className="mt-0.5 text-[11px] text-claude-text-muted line-clamp-2">{t.description}</div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
