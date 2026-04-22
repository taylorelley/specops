import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui";
import type { Share, SharePermission } from "../lib/types";

type ResourceType = "agent" | "plan";

const PERMISSIONS: SharePermission[] = ["viewer", "editor", "manager"];

type Props = {
  resourceType: ResourceType;
  resourceId: string;
  ownerUserId?: string;
  /** When true, the panel hides mutation controls (user lacks manage). */
  readOnly?: boolean;
};

export default function SharesPanel({
  resourceType,
  resourceId,
  ownerUserId,
  readOnly,
}: Props) {
  const [shares, setShares] = useState<Share[]>([]);
  const [users, setUsers] = useState<{ id: string; username: string }[]>([]);
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedPermission, setSelectedPermission] =
    useState<SharePermission>("viewer");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  // Serialise per-user writes so rapid clicks cannot race each other.
  const [pendingByUser, setPendingByUser] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, userList] = await Promise.all([
        resourceType === "agent"
          ? api.shares.listForAgent(resourceId)
          : api.shares.listForPlan(resourceId),
        api.users.list(),
      ]);
      setShares(
        list.map((s) => ({
          user_id: s.user_id,
          username: s.username,
          permission: s.permission as SharePermission,
        })),
      );
      setUsers(userList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load shares");
    } finally {
      setLoading(false);
    }
  }, [resourceId, resourceType]);

  useEffect(() => {
    load();
  }, [load]);

  const sharedUserIds = new Set(shares.map((s) => s.user_id));
  const availableUsers = users.filter(
    (u) => u.id !== ownerUserId && !sharedUserIds.has(u.id),
  );

  function markPending(userId: string, pending: boolean) {
    setPendingByUser((prev) => {
      const next = { ...prev };
      if (pending) next[userId] = true;
      else delete next[userId];
      return next;
    });
  }

  async function handleAdd() {
    if (!selectedUser) return;
    if (pendingByUser[selectedUser]) return;
    setError("");
    markPending(selectedUser, true);
    try {
      if (resourceType === "agent") {
        await api.shares.setForAgent(resourceId, selectedUser, selectedPermission);
      } else {
        await api.shares.setForPlan(resourceId, selectedUser, selectedPermission);
      }
      setSelectedUser("");
      setSelectedPermission("viewer");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add share");
    } finally {
      markPending(selectedUser, false);
    }
  }

  async function handleUpdate(userId: string, permission: SharePermission) {
    if (pendingByUser[userId]) return;
    setError("");
    markPending(userId, true);
    try {
      if (resourceType === "agent") {
        await api.shares.setForAgent(resourceId, userId, permission);
      } else {
        await api.shares.setForPlan(resourceId, userId, permission);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update share");
    } finally {
      markPending(userId, false);
    }
  }

  async function handleRemove(userId: string) {
    if (pendingByUser[userId]) return;
    setError("");
    markPending(userId, true);
    try {
      if (resourceType === "agent") {
        await api.shares.removeForAgent(resourceId, userId);
      } else {
        await api.shares.removeForPlan(resourceId, userId);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove share");
    } finally {
      markPending(userId, false);
    }
  }

  if (readOnly) {
    return (
      <div className="rounded-lg border border-claude-border bg-claude-surface px-3 py-2 text-xs text-claude-text-muted">
        You don't have permission to manage sharing for this {resourceType}.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
      {loading ? (
        <p className="text-xs text-claude-text-muted">Loading shares…</p>
      ) : (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-claude-text-muted">
                <th className="pb-2 font-medium">User</th>
                <th className="pb-2 font-medium">Permission</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {shares.length === 0 ? (
                <tr>
                  <td
                    colSpan={3}
                    className="py-2 text-xs text-claude-text-muted"
                  >
                    Not shared with anyone.
                  </td>
                </tr>
              ) : (
                shares.map((s) => {
                  const pending = !!pendingByUser[s.user_id];
                  return (
                    <tr key={s.user_id} className="border-t border-claude-border">
                      <td className="py-2 text-claude-text-primary">
                        {s.username || s.user_id}
                      </td>
                      <td className="py-2">
                        <select
                          value={s.permission}
                          onChange={(e) =>
                            handleUpdate(s.user_id, e.target.value as SharePermission)
                          }
                          disabled={pending}
                          className="rounded border border-claude-border bg-claude-bg px-2 py-1 text-xs disabled:opacity-50"
                        >
                          {PERMISSIONS.map((p) => (
                            <option key={p} value={p}>
                              {p}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-2 text-right">
                        <button
                          type="button"
                          onClick={() => handleRemove(s.user_id)}
                          disabled={pending}
                          className="text-xs text-red-600 hover:underline disabled:opacity-40 disabled:no-underline"
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>

          <div className="flex items-end gap-2 pt-2 border-t border-claude-border">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-claude-text-muted">
                Add user
              </label>
              <select
                value={selectedUser}
                onChange={(e) => setSelectedUser(e.target.value)}
                className="w-full rounded border border-claude-border bg-claude-bg px-2 py-1 text-xs"
              >
                <option value="">Select a user…</option>
                {availableUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-claude-text-muted">
                Permission
              </label>
              <select
                value={selectedPermission}
                onChange={(e) =>
                  setSelectedPermission(e.target.value as SharePermission)
                }
                className="rounded border border-claude-border bg-claude-bg px-2 py-1 text-xs"
              >
                {PERMISSIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <Button
              onClick={handleAdd}
              disabled={!selectedUser || !!pendingByUser[selectedUser]}
            >
              Share
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
