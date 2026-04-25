import { useState, useEffect } from "react";
import Modal from "./Modal";
import {
  useSpecialAgents,
  useInstallApiTool,
} from "../lib/queries";
import type { AgentSummary, ApiToolEntry } from "../lib/types";

const css = {
  btn: "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
  select:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  input:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

interface Props {
  open: boolean;
  onClose: () => void;
  entry: ApiToolEntry | null;
  agentId?: string;
}

export default function InstallApiToolModal({
  open,
  onClose,
  entry,
  agentId: preselectedAgentId,
}: Props) {
  const { data: agents = [] } = useSpecialAgents();
  const [selectedAgentId, setSelectedAgentId] = useState<string>(
    preselectedAgentId ?? "",
  );
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [maxTools, setMaxTools] = useState<number>(
    entry?.default_max_tools ?? 64,
  );
  const [roleHint, setRoleHint] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const installMutation = useInstallApiTool(selectedAgentId);
  const installing = installMutation.isPending;
  const requiredEnv = entry?.required_env ?? [];

  useEffect(() => {
    if (preselectedAgentId) setSelectedAgentId(preselectedAgentId);
  }, [preselectedAgentId]);

  useEffect(() => {
    setMaxTools(entry?.default_max_tools ?? 64);
    setEnvValues({});
    setError(null);
    setDone(false);
    setRoleHint("");
  }, [entry?.id]);

  async function handleInstall() {
    if (!entry || !selectedAgentId) return;
    setError(null);
    setDone(false);

    const missing = requiredEnv.filter((k) => !(envValues[k] ?? "").trim());
    if (missing.length > 0) {
      setError(`Missing required values: ${missing.join(", ")}`);
      return;
    }

    const headers: Record<string, string> = {};
    for (const [k, tpl] of Object.entries(entry.headers ?? {})) {
      let resolved = tpl;
      for (const [varName, varValue] of Object.entries(envValues)) {
        resolved = resolved.replace(
          new RegExp(`\\$\\{${varName}\\}`, "g"),
          varValue,
        );
      }
      headers[k] = resolved;
    }

    try {
      await installMutation.mutateAsync({
        spec_id: entry.id,
        headers,
        max_tools: maxTools,
        role_hint: roleHint || undefined,
      });
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Install failed");
    }
  }

  function handleClose() {
    if (!installing) {
      onClose();
      setError(null);
      setDone(false);
    }
  }

  if (!entry) return null;

  return (
    <Modal open={open} onClose={handleClose} title={`Install ${entry.name}`}>
      <div className="space-y-4">
        {entry.description && (
          <p className="text-sm text-claude-text-secondary">{entry.description}</p>
        )}

        <div>
          <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
            Agent
          </label>
          <select
            className={css.select}
            value={selectedAgentId}
            onChange={(e) => setSelectedAgentId(e.target.value)}
            disabled={!!preselectedAgentId}
          >
            <option value="">Select an agent…</option>
            {agents.map((a: AgentSummary) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.status})
              </option>
            ))}
          </select>
        </div>

        {requiredEnv.length > 0 && (
          <div>
            <p className="text-xs font-medium text-claude-text-secondary mb-2">
              Required credentials
            </p>
            <div className="space-y-2">
              {requiredEnv.map((key) => (
                <div key={key}>
                  <label className="block text-xs mb-1 text-claude-text-muted">
                    {key}
                  </label>
                  <input
                    type="password"
                    className={css.input}
                    value={envValues[key] ?? ""}
                    onChange={(e) =>
                      setEnvValues({ ...envValues, [key]: e.target.value })
                    }
                    placeholder={`value for \${${key}}`}
                  />
                </div>
              ))}
            </div>
            <p className="text-xs text-claude-text-muted mt-1">
              Headers are constructed by substituting <code>${"${VAR}"}</code> placeholders.
            </p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
              Max tools
            </label>
            <input
              type="number"
              className={css.input}
              value={maxTools}
              onChange={(e) => setMaxTools(Math.max(1, Number(e.target.value)))}
              min={1}
              max={64}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
              Role hint (optional)
            </label>
            <input
              type="text"
              className={css.input}
              value={roleHint}
              onChange={(e) => setRoleHint(e.target.value)}
              placeholder="e.g. read-only billing"
            />
          </div>
        </div>

        {error && (
          <div className="text-sm text-red-500 bg-red-500/10 border border-red-500/30 rounded-md p-2">
            {error}
          </div>
        )}

        {done && (
          <div className="text-sm text-emerald-500 bg-emerald-500/10 border border-emerald-500/30 rounded-md p-2">
            Installed. Restart the agent or wait for the next message — tools
            register at the start of the next turn.
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={handleClose}
            className={`${css.btn} border border-claude-border bg-claude-input hover:bg-claude-surface text-claude-text-primary`}
            disabled={installing}
          >
            {done ? "Close" : "Cancel"}
          </button>
          {!done && (
            <button
              onClick={handleInstall}
              className={`${css.btn} bg-claude-accent text-white hover:opacity-90`}
              disabled={installing || !selectedAgentId}
            >
              {installing ? "Installing…" : "Install"}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
