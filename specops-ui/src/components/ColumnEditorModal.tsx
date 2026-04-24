import { useEffect, useState } from "react";
import Modal from "./Modal";
import { useAddColumn, useUpdateColumn } from "../lib/queries";
import type { ColumnKind, PlanColumn } from "../lib/types";

const css = {
  label: "mb-1 block text-xs text-claude-text-muted font-medium",
  input:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  select:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm text-claude-text-primary focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

interface ColumnEditorModalProps {
  open: boolean;
  onClose: () => void;
  planId: string;
  /** When set the modal edits the given column; otherwise it creates a new one. */
  column?: PlanColumn | null;
}

export default function ColumnEditorModal({
  open,
  onClose,
  planId,
  column,
}: ColumnEditorModalProps) {
  const isEdit = !!column;
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<ColumnKind>("standard");
  const addColumn = useAddColumn(planId);
  const updateColumn = useUpdateColumn(planId);
  const mutation = isEdit ? updateColumn : addColumn;

  useEffect(() => {
    if (open) {
      setTitle(column?.title ?? "");
      setKind((column?.kind as ColumnKind | undefined) ?? "standard");
      addColumn.reset();
      updateColumn.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, column?.id]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    if (isEdit && column) {
      await updateColumn.mutateAsync({
        columnId: column.id,
        data: { title: trimmed, kind },
      });
    } else {
      await addColumn.mutateAsync({ title: trimmed, kind });
    }
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? "Edit column" : "Add column"}
      icon={
        <span className="flex h-4 w-4 items-center justify-center rounded bg-claude-accent/20 text-xs font-medium text-claude-accent">
          {isEdit ? "/" : "+"}
        </span>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className={css.label}>Title</label>
          <input
            type="text"
            placeholder="e.g. In Review"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoFocus
            className={css.input}
          />
        </div>
        <div>
          <label className={css.label}>Type</label>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as ColumnKind)}
            className={css.select}
          >
            <option value="standard">Standard</option>
            <option value="review">Review gate (requires human approval)</option>
          </select>
          <p className="mt-1 text-[11px] text-claude-text-muted">
            Review columns block tasks from moving forward until a human approves them.
          </p>
        </div>
        {mutation.isError && (
          <p className="text-[11px] text-red-600">
            {mutation.error instanceof Error ? mutation.error.message : "Save failed"}
          </p>
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
            disabled={!title.trim() || mutation.isPending}
            className="rounded-lg bg-claude-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-claude-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {mutation.isPending
              ? isEdit
                ? "Saving…"
                : "Adding…"
              : isEdit
                ? "Save"
                : "Add column"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
