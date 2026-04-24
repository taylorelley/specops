import { useMemo, useState } from "react";
import Modal from "./Modal";
import ConfirmDialog from "./ConfirmDialog";
import ColumnEditorModal from "./ColumnEditorModal";
import { PencilIcon, TrashIcon } from "./ui";
import { useDeleteColumn, useUpdateColumn } from "../lib/queries";
import type { Plan, PlanColumn } from "../lib/types";

interface ManageColumnsModalProps {
  open: boolean;
  onClose: () => void;
  plan: Plan;
}

function ChevronUpIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path
        fillRule="evenodd"
        d="M14.71 12.79a1 1 0 0 1-1.42 0L10 9.5l-3.29 3.29a1 1 0 1 1-1.42-1.42l4-4a1 1 0 0 1 1.42 0l4 4a1 1 0 0 1 0 1.42z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ChevronDownIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path
        fillRule="evenodd"
        d="M5.29 7.21a1 1 0 0 1 1.42 0L10 10.5l3.29-3.29a1 1 0 1 1 1.42 1.42l-4 4a1 1 0 0 1-1.42 0l-4-4a1 1 0 0 1 0-1.42z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export default function ManageColumnsModal({ open, onClose, plan }: ManageColumnsModalProps) {
  const editable = plan.status === "draft" || plan.status === "paused";
  const updateColumn = useUpdateColumn(plan.id);
  const deleteColumn = useDeleteColumn(plan.id);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingColumn, setEditingColumn] = useState<PlanColumn | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlanColumn | null>(null);
  const [rowError, setRowError] = useState<{ columnId: string; message: string } | null>(null);

  const sortedColumns = useMemo(
    () => [...(plan.columns ?? [])].sort((a, b) => a.position - b.position),
    [plan.columns],
  );

  const taskCountByColumn = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const task of plan.tasks ?? []) {
      counts[task.column_id] = (counts[task.column_id] ?? 0) + 1;
    }
    return counts;
  }, [plan.tasks]);

  const isBusy = updateColumn.isPending || deleteColumn.isPending;

  async function handleMove(index: number, direction: -1 | 1) {
    if (!editable || isBusy) return;
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= sortedColumns.length) return;
    const current = sortedColumns[index];
    const other = sortedColumns[targetIndex];
    setRowError(null);

    // Use sentinel position to avoid intermediate duplicate positions
    const maxPosition = Math.max(...sortedColumns.map(col => col.position));
    const sentinelPosition = maxPosition + 1;
    const currentOriginalPosition = current.position;
    const otherOriginalPosition = other.position;

    let failedStep: "step1" | "step2" | "step3" | null = null;
    let failedColumnId = current.id;

    try {
      // Step 1: Move current to sentinel position
      failedStep = "step1";
      await updateColumn.mutateAsync({
        columnId: current.id,
        data: { position: sentinelPosition },
      });

      // Step 2: Move other to current's original position
      failedStep = "step2";
      failedColumnId = other.id;
      await updateColumn.mutateAsync({
        columnId: other.id,
        data: { position: currentOriginalPosition },
      });

      // Step 3: Move current from sentinel to other's original position
      failedStep = "step3";
      failedColumnId = current.id;
      await updateColumn.mutateAsync({
        columnId: current.id,
        data: { position: otherOriginalPosition },
      });
    } catch (err) {
      // Attempt best-effort rollback
      if (failedStep !== "step1") {
        try {
          await updateColumn.mutateAsync({
            columnId: current.id,
            data: { position: currentOriginalPosition },
          });
        } catch {
          // Rollback failed, but don't override the original error
        }
      }

      setRowError({
        columnId: failedColumnId,
        message: err instanceof Error ? err.message : "Failed to reorder column",
      });
    }
  }

  function openAdd() {
    if (!editable) return;
    setEditingColumn(null);
    setEditorOpen(true);
  }

  function openEdit(column: PlanColumn) {
    if (!editable) return;
    setEditingColumn(column);
    setEditorOpen(true);
  }

  function requestDelete(column: PlanColumn) {
    if (!editable) return;
    setRowError(null);
    setDeleteTarget(column);
  }

  function confirmDelete() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    deleteColumn.mutate(target.id, {
      onSuccess: () => setDeleteTarget(null),
      onError: (err) => {
        setDeleteTarget(null);
        setRowError({
          columnId: target.id,
          message: err instanceof Error ? err.message : "Failed to delete column",
        });
      },
    });
  }

  return (
    <>
      <Modal open={open} onClose={onClose} title="Manage columns" size="lg">
        {!editable && (
          <div className="mb-4 rounded-lg border border-amber-400/60 bg-amber-50/60 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
            Columns can only be modified while the plan is in <strong>draft</strong> or{" "}
            <strong>paused</strong>. Pause the plan to enable editing.
          </div>
        )}
        <div className="space-y-2">
          {sortedColumns.length === 0 && (
            <p className="text-sm text-claude-text-muted">This plan has no columns.</p>
          )}
          {sortedColumns.map((col, index) => {
            const taskCount = taskCountByColumn[col.id] ?? 0;
            const isReview = col.kind === "review";
            const isLast = sortedColumns.length <= 1;
            const deleteDisabledReason = !editable
              ? "Pause the plan to enable editing"
              : isLast
                ? "A plan must have at least one column"
                : taskCount > 0
                  ? "Move or delete tasks before removing this column"
                  : undefined;
            const moveUpDisabled = !editable || isBusy || index === 0;
            const moveDownDisabled =
              !editable || isBusy || index === sortedColumns.length - 1;
            return (
              <div
                key={col.id}
                className="flex flex-col rounded-lg border border-claude-border bg-claude-input px-3 py-2"
              >
                <div className="flex items-center gap-3">
                  <div className="flex flex-col">
                    <button
                      type="button"
                      onClick={() => handleMove(index, -1)}
                      disabled={moveUpDisabled}
                      className="rounded p-0.5 text-claude-text-muted hover:bg-claude-surface hover:text-claude-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title="Move up"
                      aria-label={`Move ${col.title} up`}
                    >
                      <ChevronUpIcon className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleMove(index, 1)}
                      disabled={moveDownDisabled}
                      className="rounded p-0.5 text-claude-text-muted hover:bg-claude-surface hover:text-claude-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title="Move down"
                      aria-label={`Move ${col.title} down`}
                    >
                      <ChevronDownIcon className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-claude-text-primary">
                        {col.title}
                      </span>
                      {isReview && (
                        <span className="rounded-full bg-amber-200/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">
                          Review gate
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-[11px] text-claude-text-muted">
                      {taskCount === 0
                        ? "No tasks"
                        : `${taskCount} task${taskCount !== 1 ? "s" : ""}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => openEdit(col)}
                      disabled={!editable}
                      className="rounded p-1 text-claude-text-secondary hover:bg-claude-surface hover:text-claude-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title={editable ? "Edit column" : "Pause the plan to enable editing"}
                      aria-label={`Edit ${col.title}`}
                    >
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => requestDelete(col)}
                      disabled={deleteDisabledReason !== undefined}
                      className="rounded p-1 text-claude-text-secondary hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title={deleteDisabledReason ?? "Delete column"}
                      aria-label={`Delete ${col.title}`}
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </div>
                {rowError?.columnId === col.id && (
                  <p className="mt-1 text-[11px] text-red-600">{rowError.message}</p>
                )}
              </div>
            );
          })}
        </div>
        <div className="mt-4 flex items-center justify-between">
          <button
            type="button"
            onClick={openAdd}
            disabled={!editable}
            className="inline-flex items-center gap-1 rounded-lg border border-dashed border-claude-border px-3 py-1.5 text-sm text-claude-text-secondary hover:border-claude-accent hover:text-claude-accent disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <span className="text-base leading-none">+</span>
            Add column
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-sm text-claude-text-muted hover:text-claude-text-secondary transition-colors"
          >
            Close
          </button>
        </div>
      </Modal>

      <ColumnEditorModal
        open={editorOpen}
        onClose={() => {
          setEditorOpen(false);
          setEditingColumn(null);
        }}
        planId={plan.id}
        column={editingColumn}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        title="Delete column"
        message={
          deleteTarget
            ? `Delete column "${deleteTarget.title}"? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        isPending={deleteColumn.isPending}
        variant="danger"
      />
    </>
  );
}
