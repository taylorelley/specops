import { useState, useEffect } from "react";
import Modal from "./Modal";
import { PencilIcon } from "./ui";
import { useUpdateTask } from "../lib/queries";
import type { PlanTask as PlanTaskType, PlanColumn as PlanColumnType } from "../lib/types";

const css = {
  label: "mb-1 block text-xs text-claude-text-muted font-medium",
  input:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  select:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm text-claude-text-primary focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

interface EditTaskModalProps {
  open: boolean;
  onClose: () => void;
  planId: string;
  task: PlanTaskType | null;
  columns: PlanColumnType[];
  agents: { id: string; name: string }[];
}

export default function EditTaskModal({
  open,
  onClose,
  planId,
  task,
  columns,
  agents,
}: EditTaskModalProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [agentId, setAgentId] = useState("");
  const [columnId, setColumnId] = useState("");
  const [requiresReview, setRequiresReview] = useState(true);
  const updateTask = useUpdateTask(planId);

  const hasReviewColumn = columns.some((c) => c.kind === "review");

  useEffect(() => {
    if (task) {
      setTitle(task.title ?? "");
      setDescription(task.description ?? "");
      setAgentId(task.agent_id ?? "");
      setColumnId(task.column_id ?? "");
      setRequiresReview(task.requires_review !== false);
    }
  }, [task]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!task || !title.trim()) return;
    const payload: Partial<PlanTaskType> = {
      title: title.trim(),
      description: description.trim(),
      agent_id: agentId || undefined,
      column_id: columnId || task.column_id,
    };
    if (hasReviewColumn) {
      payload.requires_review = requiresReview;
    }
    await updateTask.mutateAsync({
      taskId: task.id,
      data: payload,
    });
    onClose();
  }

  if (!task) return null;

  const sortedColumns = [...columns].sort((a, b) => a.position - b.position);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Edit task"
      icon={<PencilIcon className="h-4 w-4" />}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className={css.label}>Title</label>
          <input
            type="text"
            placeholder="e.g. Review pull request"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoFocus
            className={css.input}
          />
        </div>
        <div>
          <label className={css.label}>Description (optional)</label>
          <textarea
            placeholder="Add details or acceptance criteria…"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={12}
            className={`${css.input} min-h-[12rem] resize-y`}
          />
        </div>
        <div>
          <label className={css.label}>Status</label>
          <select
            value={columnId}
            onChange={(e) => setColumnId(e.target.value)}
            className={css.select}
          >
            {sortedColumns.map((col) => (
              <option key={col.id} value={col.id}>
                {col.title}
              </option>
            ))}
          </select>
        </div>
        {agents.length > 0 && (
          <div>
            <label className={css.label}>Assignee</label>
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className={css.select}
            >
              <option value="">Unassigned</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
        )}
        {hasReviewColumn && (
          <label className="flex items-start gap-2 text-sm text-claude-text-secondary">
            <input
              type="checkbox"
              checked={requiresReview}
              onChange={(e) => setRequiresReview(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Require human review before this task can leave a review column.
              <span className="block text-xs text-claude-text-muted">
                Uncheck to let this specific task bypass the review gate.
              </span>
            </span>
          </label>
        )}
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
            disabled={!title.trim() || updateTask.isPending}
            className="rounded-lg bg-claude-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-claude-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {updateTask.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
