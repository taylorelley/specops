import { useState, useEffect, useCallback } from "react";
import {
  api,
  type RuntimeInfo,
} from "../lib/api";
import { Card, PageHeader, PageContainer, Button, Input } from "../components/ui";
import Modal from "../components/Modal";
import { useAuth } from "../contexts/AuthContext";

type TabType = "general" | "password" | "users" | "providers";

type AdminLLMProvider = {
  id: string;
  name: string;
  type: string;
  api_key: string;
  api_base: string;
  extra_headers: Record<string, string> | null;
  created_at: string;
  updated_at: string;
};

type LLMProviderType = {
  name: string;
  display_name: string;
  is_gateway: boolean;
  is_local: boolean;
  requires_api_base: boolean;
};

function ProviderFormModal({
  title,
  initial,
  types,
  onClose,
  onSubmit,
}: {
  title: string;
  initial?: AdminLLMProvider;
  types: LLMProviderType[];
  onClose: () => void;
  onSubmit: (data: {
    name: string;
    type: string;
    api_key: string;
    api_base: string;
    extra_headers: Record<string, string> | null;
  }) => Promise<void>;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [type, setType] = useState(initial?.type ?? (types[0]?.name ?? ""));
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState(initial?.api_base ?? "");
  const [extraHeadersRaw, setExtraHeadersRaw] = useState(
    initial?.extra_headers ? JSON.stringify(initial.extra_headers, null, 2) : "",
  );
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const selectedType = types.find((t) => t.name === type);
  const needsApiBase = !!(selectedType?.requires_api_base);
  const showApiBase = needsApiBase;

  // Clear apiBase whenever the selected type no longer exposes the field so a
  // stale URL can't leak into the payload after switching types.
  useEffect(() => {
    if (!showApiBase) setApiBase("");
  }, [showApiBase]);

  async function handleSubmit() {
    setErr("");
    if (!name.trim()) {
      setErr("Name is required");
      return;
    }
    if (!type) {
      setErr("Type is required");
      return;
    }
    let extraHeaders: Record<string, string> | null = null;
    if (extraHeadersRaw.trim()) {
      try {
        const parsed = JSON.parse(extraHeadersRaw);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          setErr("Extra headers must be a JSON object");
          return;
        }
        const entries = Object.entries(parsed as Record<string, unknown>);
        if (entries.some(([, v]) => typeof v !== "string")) {
          setErr("Extra headers values must be strings");
          return;
        }
        extraHeaders = Object.fromEntries(entries) as Record<string, string>;
      } catch {
        setErr("Extra headers is not valid JSON");
        return;
      }
    }
    setBusy(true);
    try {
      await onSubmit({
        name: name.trim(),
        type,
        api_key: apiKey,
        api_base: showApiBase ? apiBase.trim() : "",
        extra_headers: extraHeaders,
      });
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={true} onClose={onClose} title={title}>
      <div className="space-y-3">
        {err && (
          <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700">
            {err}
          </div>
        )}
        <div>
          <label className="mb-1 block text-xs font-medium text-claude-text-muted">Name</label>
          <Input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. OpenAI-prod"
            disabled={busy}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-claude-text-muted">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            disabled={busy}
            className="w-full rounded-lg border border-claude-border bg-claude-bg px-3 py-2 text-sm"
          >
            {types.map((t) => (
              <option key={t.name} value={t.name}>
                {t.display_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-claude-text-muted">
            API Key {initial ? "(leave blank to keep existing)" : ""}
          </label>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={initial ? "•••" : "sk-..."}
            disabled={busy}
          />
        </div>
        {showApiBase && (
          <div>
            <label className="mb-1 block text-xs font-medium text-claude-text-muted">Base URL</label>
            <Input
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="https://api.example.com/v1"
              disabled={busy}
            />
          </div>
        )}
        <details>
          <summary className="cursor-pointer text-xs font-medium text-claude-text-muted">
            Advanced
          </summary>
          <div className="mt-2">
            <label className="mb-1 block text-xs font-medium text-claude-text-muted">
              Extra headers (JSON)
            </label>
            <textarea
              value={extraHeadersRaw}
              onChange={(e) => setExtraHeadersRaw(e.target.value)}
              placeholder='{"X-Example": "value"}'
              disabled={busy}
              rows={3}
              className="w-full rounded-lg border border-claude-border bg-claude-bg px-3 py-2 font-mono text-xs"
            />
          </div>
        </details>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function ProvidersTab() {
  const [providers, setProviders] = useState<AdminLLMProvider[]>([]);
  const [types, setTypes] = useState<LLMProviderType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AdminLLMProvider | null>(null);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const [list, typeList] = await Promise.all([
        api.admin.llmProviders.list(),
        api.admin.llmProviders.listTypes(),
      ]);
      setProviders(list);
      setTypes(typeList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load providers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDelete(p: AdminLLMProvider) {
    if (!window.confirm(`Delete provider "${p.name}"? This cannot be undone.`)) return;
    setError("");
    try {
      await api.admin.llmProviders.delete(p.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <Card>
      <SectionHeader
        icon={<LockIcon className="h-4 w-4 text-claude-text-muted" />}
        title="LLM providers"
        description="Configure API keys once. Agents pick from this list when selecting a model."
      />

      {error && <ErrorBanner message={error} />}

      <div className="mb-4 flex justify-end">
        <Button onClick={() => setCreating(true)}>Add provider</Button>
      </div>

      {loading ? (
        <p className="text-xs text-claude-text-muted">Loading providers…</p>
      ) : providers.length === 0 ? (
        <p className="text-xs text-claude-text-muted">
          No providers configured. Click <span className="font-medium">Add provider</span> to create the first one.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-claude-text-muted">
              <th className="pb-2 font-medium">Name</th>
              <th className="pb-2 font-medium">Type</th>
              <th className="pb-2 font-medium">API Key</th>
              <th className="pb-2 font-medium">Updated</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id} className="border-t border-claude-border">
                <td className="py-2 text-claude-text-primary">{p.name}</td>
                <td className="py-2 text-xs text-claude-text-muted">{p.type}</td>
                <td className="py-2 font-mono text-xs text-claude-text-muted">
                  {p.api_key || "—"}
                </td>
                <td className="py-2 text-xs text-claude-text-muted">
                  {p.updated_at?.slice(0, 10)}
                </td>
                <td className="py-2 text-right space-x-3">
                  <button
                    type="button"
                    onClick={() => setEditing(p)}
                    className="text-xs text-claude-accent hover:underline"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(p)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {creating && (
        <ProviderFormModal
          title="Add provider"
          types={types}
          onClose={() => setCreating(false)}
          onSubmit={async (data) => {
            await api.admin.llmProviders.create(data);
            await load();
          }}
        />
      )}
      {editing && (
        <ProviderFormModal
          title={`Edit — ${editing.name}`}
          initial={editing}
          types={types}
          onClose={() => setEditing(null)}
          onSubmit={async (data) => {
            const patch: Parameters<typeof api.admin.llmProviders.update>[1] = {
              name: data.name,
              type: data.type,
              api_base: data.api_base,
              extra_headers: data.extra_headers,
            };
            if (data.api_key) patch.api_key = data.api_key;
            await api.admin.llmProviders.update(editing.id, patch);
            await load();
          }}
        />
      )}
    </Card>
  );
}

function ResetPasswordModal({
  username,
  onClose,
  onSubmit,
}: {
  username: string;
  onClose: () => void;
  onSubmit: (newPassword: string) => Promise<void> | void;
}) {
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    setErr("");
    if (!pw) {
      setErr("Password cannot be empty");
      return;
    }
    if (pw !== confirm) {
      setErr("Passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await onSubmit(pw);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to reset password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={true} onClose={onClose} title={`Reset password — ${username}`}>
      <div className="space-y-3">
        {err && (
          <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700">
            {err}
          </div>
        )}
        <div>
          <label className="mb-1 block text-xs font-medium text-claude-text-muted">
            New password
          </label>
          <Input
            type="password"
            autoFocus
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            disabled={busy}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-claude-text-muted">
            Confirm new password
          </label>
          <Input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            disabled={busy}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={busy}>
            {busy ? "Saving…" : "Set password"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

type AdminUser = {
  id: string;
  username: string;
  role: string;
  created_at: string;
};

function UsersTab() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [creating, setCreating] = useState(false);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const list = await api.users.listAdmin();
      setUsers(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate() {
    setError("");
    if (!newUsername || !newPassword) {
      setError("Username and password are required");
      return;
    }
    setCreating(true);
    try {
      await api.users.create({
        username: newUsername,
        password: newPassword,
        role: newRole,
      });
      setNewUsername("");
      setNewPassword("");
      setNewRole("user");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  async function handleChangeRole(userId: string, role: string) {
    setError("");
    try {
      await api.users.update(userId, { role });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to change role");
    }
  }

  async function submitResetPassword(userId: string, newPassword: string) {
    await api.users.update(userId, { password: newPassword });
  }

  async function handleDelete(userId: string, username: string) {
    if (!window.confirm(`Delete user ${username}? This cannot be undone.`)) return;
    setError("");
    try {
      await api.users.delete(userId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete user");
    }
  }

  return (
    <Card>
      <SectionHeader
        icon={<LockIcon className="h-4 w-4 text-claude-text-muted" />}
        title="User management"
        description="Create users, set roles, reset passwords. Only admins can manage users."
      />

      {error && <ErrorBanner message={error} />}

      <div className="mb-5 space-y-2 rounded-lg border border-claude-border bg-claude-surface p-3">
        <h3 className="text-xs font-semibold text-claude-text-primary">
          Create user
        </h3>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[160px]">
            <label className="mb-1 block text-xs font-medium text-claude-text-muted">
              Username
            </label>
            <Input
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="alice"
              disabled={creating}
            />
          </div>
          <div className="flex-1 min-w-[160px]">
            <label className="mb-1 block text-xs font-medium text-claude-text-muted">
              Password
            </label>
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="initial password"
              disabled={creating}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-claude-text-muted">
              Role
            </label>
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              className="rounded border border-claude-border bg-claude-bg px-2 py-2 text-sm"
              disabled={creating}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <Button onClick={handleCreate} disabled={creating}>
            {creating ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-xs text-claude-text-muted">Loading users…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-claude-text-muted">
              <th className="pb-2 font-medium">Username</th>
              <th className="pb-2 font-medium">Role</th>
              <th className="pb-2 font-medium">Created</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSelf = u.id === currentUser?.id;
              return (
                <tr key={u.id} className="border-t border-claude-border">
                  <td className="py-2 text-claude-text-primary">{u.username}</td>
                  <td className="py-2">
                    <select
                      value={u.role}
                      onChange={(e) => handleChangeRole(u.id, e.target.value)}
                      disabled={isSelf}
                      className="rounded border border-claude-border bg-claude-bg px-2 py-1 text-xs disabled:opacity-60"
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="py-2 text-xs text-claude-text-muted">
                    {u.created_at?.slice(0, 10)}
                  </td>
                  <td className="py-2 text-right space-x-3">
                    <button
                      type="button"
                      onClick={() => setResetTarget(u)}
                      className="text-xs text-claude-accent hover:underline"
                    >
                      Reset password
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(u.id, u.username)}
                      disabled={isSelf}
                      className="text-xs text-red-600 hover:underline disabled:opacity-40 disabled:no-underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {resetTarget && (
        <ResetPasswordModal
          username={resetTarget.username}
          onClose={() => setResetTarget(null)}
          onSubmit={(pw) => submitResetPassword(resetTarget.id, pw)}
        />
      )}
    </Card>
  );
}

function SettingsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
      />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function RuntimeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
    </svg>
  );
}


const selectCls =
  "w-full rounded-lg border border-claude-border bg-claude-bg px-3 py-2 text-sm text-claude-text-primary focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors appearance-none bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20fill%3D%22%239B958F%22%20viewBox%3D%220%200%2016%2016%22%3E%3Cpath%20d%3D%22M4.646%206.646a.5.5%200%2001.708%200L8%209.293l2.646-2.647a.5.5%200%2001.708.708l-3%203a.5.5%200%2001-.708%200l-3-3a.5.5%200%20010-.708z%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_8px_center] bg-no-repeat pr-8";

function SectionHeader({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-claude-surface">
        {icon}
      </div>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-claude-text-primary">{title}</h2>
        <p className="mt-0.5 text-xs text-claude-text-muted leading-relaxed">{description}</p>
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2">
      <svg className="h-4 w-4 shrink-0 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
      </svg>
      <p className="text-xs text-red-700">{message}</p>
    </div>
  );
}

function LockIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm6-10V7a3 3 0 00-3-3H9a3 3 0 00-3 3v2h12z" />
    </svg>
  );
}

function InfoIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function SuccessBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border border-green-200 dark:border-green-900 bg-green-50 dark:bg-green-950/40 px-3 py-2">
      <svg className="h-4 w-4 shrink-0 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p className="text-xs text-green-700">{message}</p>
    </div>
  );
}

export default function AdminSettings() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [activeTab, setActiveTab] = useState<TabType>("general");
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeInfo | null>(null);
  const [runtimeError, setRuntimeError] = useState("");
  const [runtimeSwitching, setRuntimeSwitching] = useState(false);

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");
  const [passwordChanging, setPasswordChanging] = useState(false);

  const fetchRuntimeInfo = useCallback(async () => {
    try {
      setRuntimeError("");
      const info = await api.runtime.info();
      setRuntimeInfo(info);
    } catch (e) {
      setRuntimeError(e instanceof Error ? e.message : "Failed to load runtime info");
    }
  }, []);


  useEffect(() => {
    fetchRuntimeInfo();
  }, [fetchRuntimeInfo]);

  async function handleRuntimeBackendChange(kind: string) {
    if (!runtimeInfo || kind === runtimeInfo.runtime_type) return;
    setRuntimeSwitching(true);
    setRuntimeError("");
    try {
      await api.runtime.setBackend(kind);
      await fetchRuntimeInfo();
    } catch (e) {
      setRuntimeError(e instanceof Error ? e.message : "Failed to switch backend");
    } finally {
      setRuntimeSwitching(false);
    }
  }

  async function handlePasswordChange() {
    setPasswordError("");
    setPasswordSuccess("");

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError("All fields are required");
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match");
      return;
    }

    if (newPassword.length < 6) {
      setPasswordError("New password must be at least 6 characters");
      return;
    }

    setPasswordChanging(true);
    try {
      await api.auth.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordSuccess("Password changed successfully");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setTimeout(() => setPasswordSuccess(""), 5000);
    } catch (e) {
      setPasswordError(e instanceof Error ? e.message : "Failed to change password");
    } finally {
      setPasswordChanging(false);
    }
  }


  return (
    <PageContainer>
      <PageHeader
        title="Settings"
        icon={<SettingsIcon className="h-5 w-5" />}
        description="Global configuration for the admin platform."
      />

      {/* ── Tab Navigation ────────────────────────────────────── */}
      <div className="mb-6 border-b border-claude-border">
        <div className="flex gap-6">
          <button
            onClick={() => setActiveTab("general")}
            className={`py-3 px-1 font-medium text-sm border-b-2 transition-colors ${
              activeTab === "general"
                ? "border-claude-accent text-claude-accent"
                : "border-transparent text-claude-text-muted hover:text-claude-text-primary"
            }`}
          >
            General
          </button>
          <button
            onClick={() => setActiveTab("password")}
            className={`py-3 px-1 font-medium text-sm border-b-2 transition-colors ${
              activeTab === "password"
                ? "border-claude-accent text-claude-accent"
                : "border-transparent text-claude-text-muted hover:text-claude-text-primary"
            }`}
          >
            Password
          </button>
          {isAdmin && (
            <button
              onClick={() => setActiveTab("users")}
              className={`py-3 px-1 font-medium text-sm border-b-2 transition-colors ${
                activeTab === "users"
                  ? "border-claude-accent text-claude-accent"
                  : "border-transparent text-claude-text-muted hover:text-claude-text-primary"
              }`}
            >
              Users
            </button>
          )}
          {isAdmin && (
            <button
              onClick={() => setActiveTab("providers")}
              className={`py-3 px-1 font-medium text-sm border-b-2 transition-colors ${
                activeTab === "providers"
                  ? "border-claude-accent text-claude-accent"
                  : "border-transparent text-claude-text-muted hover:text-claude-text-primary"
              }`}
            >
              Providers
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4">
        {/* ── General Tab ──────────────────────────────────────── */}
        {activeTab === "general" && (
          <>
            {runtimeInfo && (
              <Card>
                <SectionHeader
                  icon={<InfoIcon className="h-4 w-4 text-claude-text-muted" />}
                  title="Setup info"
                  description="System configuration and storage details"
                />

                {runtimeInfo.data_root && (
                  <div className="max-w-sm">
                    <label className="mb-1 block text-xs font-medium text-claude-text-muted">Root storage path</label>
                    <div className="flex items-center gap-2 rounded-lg bg-claude-surface px-3 py-2">
                      <svg className="h-3.5 w-3.5 shrink-0 text-claude-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                      </svg>
                      <span className="text-xs text-claude-text-primary font-mono break-all">{runtimeInfo.data_root}</span>
                    </div>
                  </div>
                )}
              </Card>
            )}

            <Card>
              <SectionHeader
                icon={<RuntimeIcon className="h-4 w-4 text-claude-text-muted" />}
                title="Agent runtime backend"
                description="Controls how agents are executed. All agents share this backend. Stop all running agents before switching."
              />

              {runtimeError && <ErrorBanner message={runtimeError} />}

              {runtimeInfo ? (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-claude-text-muted">Backend</label>
                    <div className="max-w-sm">
                      <select
                        value={runtimeInfo.runtime_type}
                        onChange={(e) => handleRuntimeBackendChange(e.target.value)}
                        disabled={runtimeSwitching}
                        className={selectCls + (runtimeSwitching ? " opacity-50 cursor-wait" : "")}
                      >
                        {runtimeInfo.available_backends.map((b) => (
                          <option key={b.value} value={b.value}>{b.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {runtimeInfo.running_count > 0 && (
                    <div className="flex items-center gap-2 rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40 px-3 py-2">
                      <svg className="h-4 w-4 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                      </svg>
                      <p className="text-xs text-amber-700">
                        <span className="font-medium">{runtimeInfo.running_count} agent(s) running</span> — stop all before switching backend.
                      </p>
                    </div>
                  )}
                </div>
              ) : !runtimeError ? (
                <div className="flex items-center gap-2 py-2">
                  <svg className="h-4 w-4 animate-spin text-claude-text-muted" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <p className="text-xs text-claude-text-muted">Loading runtime info…</p>
                </div>
              ) : null}
            </Card>
          </>
        )}

        {/* ── Users Tab ─────────────────────────────────────────── */}
        {activeTab === "users" && isAdmin && <UsersTab />}

        {/* ── Providers Tab ─────────────────────────────────────── */}
        {activeTab === "providers" && isAdmin && <ProvidersTab />}

        {/* ── Password Tab ──────────────────────────────────────── */}
        {activeTab === "password" && (
          <Card>
            <SectionHeader
              icon={<LockIcon className="h-4 w-4 text-claude-text-muted" />}
              title="Change password"
              description="Update your admin account password."
            />

            {passwordError && <ErrorBanner message={passwordError} />}
            {passwordSuccess && <SuccessBanner message={passwordSuccess} />}

            <div className="space-y-3">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-claude-text-muted">Current password</label>
                <Input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="Enter current password"
                  disabled={passwordChanging}
                  className="w-[400px] max-w-full"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-claude-text-muted">New password</label>
                <Input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                  disabled={passwordChanging}
                  className="w-[400px] max-w-full"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-claude-text-muted">Confirm new password</label>
                <Input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  disabled={passwordChanging}
                  className="w-[400px] max-w-full"
                />
              </div>
              <Button
                onClick={handlePasswordChange}
                disabled={passwordChanging}
              >
                {passwordChanging ? "Changing..." : "Change Password"}
              </Button>
            </div>
          </Card>
        )}
      </div>
    </PageContainer>
  );
}
