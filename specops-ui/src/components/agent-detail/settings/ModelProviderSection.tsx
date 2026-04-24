import { useEffect, useRef, useState } from "react";
import { api } from "../../../lib/api";
import { css, PROVIDER_DEFS } from "../constants";

type FetchedModel = { id: string; name: string };

type CentralProvider = { id: string; name: string; type: string };

// Non-OAuth selection uses a central provider ref prefixed with "ref:".
// OAuth selection uses the raw provider field name (e.g. "chatgpt").
type Selection =
  | { kind: "none" }
  | { kind: "ref"; providerId: string; type: string; name: string }
  | { kind: "oauth"; field: string };

export function ModelProviderSection({
  agentId,
  model,
  savedProviders,
  onModelChange,
  onProviderChange,
}: {
  agentId: string;
  model: string;
  savedProviders?: Record<string, unknown>;
  onModelChange: (model: string) => void;
  onProviderChange: (provider: string, patch: { apiKey?: string; apiBase?: string; providerRef?: string | null }) => void;
}) {
  const [centrals, setCentrals] = useState<CentralProvider[]>([]);
  const [centralsLoading, setCentralsLoading] = useState(false);
  const [centralsError, setCentralsError] = useState("");

  const savedRef = (savedProviders?.providerRef ?? savedProviders?.provider_ref ?? "") as string;

  const [selection, setSelection] = useState<Selection>({ kind: "none" });

  const [models, setModels] = useState<FetchedModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelError, setModelError] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // OAuth state
  const [oauthAuthorized, setOauthAuthorized] = useState<boolean | null>(null);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [oauthPending, setOauthPending] = useState(false);
  const [oauthError, setOauthError] = useState("");
  const [oauthAccountId, setOauthAccountId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const oauthProviders = PROVIDER_DEFS.filter((p) => p.oauth);

  // Load centrally-managed providers once on mount
  useEffect(() => {
    let cancelled = false;
    setCentralsLoading(true);
    api.llmProviders
      .list()
      .then((rows) => {
        if (!cancelled) setCentrals(rows);
      })
      .catch((err) => {
        if (!cancelled) setCentralsError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setCentralsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Initialise selection from savedProviders.providerRef or any OAuth-only slot
  useEffect(() => {
    if (savedRef) {
      const match = centrals.find((c) => c.id === savedRef);
      if (match) {
        setSelection({ kind: "ref", providerId: match.id, type: match.type, name: match.name });
        return;
      }
      // Saved ref no longer exists (deleted by admin): fall back to none
      setSelection({ kind: "none" });
      return;
    }
    // No central ref — if an OAuth provider has stored creds, default to it
    for (const def of oauthProviders) {
      const slot = savedProviders?.[def.field];
      if (slot && typeof slot === "object") {
        setSelection({ kind: "oauth", field: def.field });
        return;
      }
    }
    setSelection({ kind: "none" });
    // centrals changes when list loads; we intentionally only re-init then.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedRef, centrals]);

  // Clear OAuth state on selection change
  useEffect(() => {
    setOauthAuthorized(null);
    setOauthError("");
    setOauthAccountId(null);
    setOauthPending(false);
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (selection.kind !== "oauth") return;
    // Cancellation guard: ignore a stale response if selection/agent changes
    // before oauthStatus resolves.
    let cancelled = false;
    api.providers
      .oauthStatus(selection.field, agentId)
      .then((r) => {
        if (cancelled) return;
        setOauthAuthorized(r.authorized);
        setOauthAccountId(r.account_id ?? null);
      })
      .catch(() => {
        if (!cancelled) setOauthAuthorized(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selection, agentId]);

  useEffect(() => {
    return () => {
      if (pollRef.current !== null) clearInterval(pollRef.current);
    };
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    if (!modelDropdownOpen) return;
    function onClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setModelDropdownOpen(false);
        setModelSearch("");
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [modelDropdownOpen]);

  // Fetch models when a selection is active and credentials exist
  useEffect(() => {
    setModels([]);
    setModelError("");
    if (selection.kind === "none") return;

    // Cancellation guard: selection or agentId can change mid-flight; we don't
    // want a stale response to overwrite the model list for the newer selection.
    let cancelled = false;

    if (selection.kind === "oauth") {
      if (!oauthAuthorized) return;
      setLoadingModels(true);
      api.providers
        .listModels(selection.field, "", agentId)
        .then((r) => {
          if (cancelled) return;
          setModels(r.models);
          const expectedPrefix = `${selection.field}/`;
          const hasModel = model && model.startsWith(expectedPrefix);
          if (!hasModel && r.models.length > 0) {
            onModelChange(`${selection.field}/${r.models[0].id}`);
          }
        })
        .catch(() => {})
        .finally(() => {
          if (!cancelled) setLoadingModels(false);
        });
      return () => {
        cancelled = true;
      };
    }

    // Central ref
    setLoadingModels(true);
    api.providers
      .listModels(selection.type, "", agentId, undefined, selection.providerId)
      .then((r) => {
        if (cancelled) return;
        setModels(r.models);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        setModelError(msg.replace(/^API \d+: /, ""));
      })
      .finally(() => {
        if (!cancelled) setLoadingModels(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selection, agentId, oauthAuthorized]);  // eslint-disable-line react-hooks/exhaustive-deps

  function startPolling(provider: string) {
    if (pollRef.current !== null) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const r = await api.providers.oauthStatus(provider, agentId);
        if (r.authorized) {
          setOauthAuthorized(true);
          setOauthAccountId(r.account_id ?? null);
          setOauthPending(false);
          if (pollRef.current !== null) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch { /* ignore poll errors */ }
    }, 2000);
  }

  function cancelPolling() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setOauthPending(false);
  }

  async function handleOAuthAuthorize(field: string) {
    setOauthLoading(true);
    setOauthError("");
    cancelPolling();
    try {
      const r = await api.providers.oauthAuthorize(field, agentId);
      window.open(r.auth_url, "_blank", "noopener,noreferrer");
      setOauthPending(true);
      startPolling(field);
    } catch (err) {
      setOauthError((err instanceof Error ? err.message : String(err)).replace(/^API \d+: /, ""));
    } finally {
      setOauthLoading(false);
    }
  }

  function handleSelectionChange(raw: string) {
    if (!raw) {
      setSelection({ kind: "none" });
      onProviderChange("", { providerRef: null });
      return;
    }
    if (raw.startsWith("ref:")) {
      const id = raw.slice(4);
      const entry = centrals.find((c) => c.id === id);
      if (!entry) {
        setSelection({ kind: "none" });
        return;
      }
      setSelection({ kind: "ref", providerId: entry.id, type: entry.type, name: entry.name });
      onProviderChange(entry.type, { providerRef: entry.id });
      return;
    }
    if (raw.startsWith("oauth:")) {
      const field = raw.slice(6);
      setSelection({ kind: "oauth", field });
      // Clear any central provider ref when switching to OAuth
      onProviderChange(field, { providerRef: null });
      return;
    }
  }

  function handleModelSelect(modelId: string) {
    if (selection.kind === "none") return;
    const prefix = selection.kind === "oauth" ? selection.field : selection.type;
    onModelChange(`${prefix}/${modelId}`);
    setModelDropdownOpen(false);
    setModelSearch("");
  }

  const selectedValue =
    selection.kind === "ref"
      ? `ref:${selection.providerId}`
      : selection.kind === "oauth"
        ? `oauth:${selection.field}`
        : "";

  const currentModelDisplay = model
    ? model.includes("/") ? model.substring(model.indexOf("/") + 1) : model
    : "";

  const filteredModels = modelSearch
    ? models.filter((m) =>
      m.id.toLowerCase().includes(modelSearch.toLowerCase()) ||
      m.name.toLowerCase().includes(modelSearch.toLowerCase())
    )
    : models;

  const oauthDef = selection.kind === "oauth" ? oauthProviders.find((p) => p.field === selection.field) : undefined;

  return (
    <div className="space-y-2.5">
      <div className="flex gap-4 flex-wrap items-end">
        <div className="flex-1 min-w-[220px]">
          <label className={css.label}>Provider</label>
          <select
            className={`${css.input} w-full`}
            value={selectedValue}
            onChange={(e) => handleSelectionChange(e.target.value)}
          >
            <option value="">
              {centralsLoading ? "Loading providers…" : "Select a provider…"}
            </option>
            {centrals.length > 0 && (
              <optgroup label="── Centrally-managed">
                {centrals.map((c) => (
                  <option key={c.id} value={`ref:${c.id}`}>
                    {c.name} ({c.type})
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label="── Subscription (OAuth)">
              {oauthProviders.map((p) => (
                <option key={p.field} value={`oauth:${p.field}`}>
                  {p.label}
                </option>
              ))}
            </optgroup>
          </select>
          {centralsError && (
            <p className="mt-1 text-[10px] text-red-500">{centralsError}</p>
          )}
          {!centralsLoading && centrals.length === 0 && !centralsError && (
            <p className="mt-1 text-[10px] text-claude-text-muted">
              No centrally-managed providers yet. An admin can add them in Settings → Providers.
            </p>
          )}
        </div>

        {selection.kind === "oauth" && oauthDef && (
          <div className="flex-1 min-w-[220px]">
            <label className={css.label}>Authorization</label>
            {oauthAuthorized === null && !oauthPending && (
              <p className="text-xs text-claude-text-muted">Checking status…</p>
            )}
            {oauthAuthorized === true && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 inline-block shrink-0" />
                  Connected{oauthAccountId ? ` · ${oauthAccountId.slice(0, 8)}…` : ""}
                </span>
                <button
                  type="button"
                  onClick={() => handleOAuthAuthorize(selection.field)}
                  disabled={oauthLoading}
                  className={`${css.btn} text-xs text-claude-text-muted ring-1 ring-claude-border hover:bg-claude-surface disabled:opacity-40`}
                >
                  Re-authorize
                </button>
              </div>
            )}
            {oauthPending && (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <svg className="h-3.5 w-3.5 animate-spin text-claude-accent shrink-0" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-xs text-claude-text-secondary">Waiting for authorization…</span>
                  <button
                    type="button"
                    onClick={cancelPolling}
                    className="text-[11px] text-claude-text-muted hover:text-red-500 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
                <p className="text-[10px] text-claude-text-muted">Complete sign-in in the browser tab that just opened.</p>
              </div>
            )}
            {oauthAuthorized === false && !oauthPending && (
              <div className="flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={() => handleOAuthAuthorize(selection.field)}
                  disabled={oauthLoading}
                  className={`${css.btn} text-claude-accent ring-1 ring-claude-accent/30 hover:bg-claude-accent/5 disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  {oauthLoading ? "Opening browser…" : `Connect ${oauthDef.label}`}
                </button>
                {oauthError && <p className="text-xs text-red-500">{oauthError}</p>}
                <p className="text-[10px] text-claude-text-muted">Opens a new tab to authorize</p>
              </div>
            )}
          </div>
        )}
      </div>

      {selection.kind !== "none" && (
        <div>
          <label className={css.label}>Model</label>
          {modelError && (
            <p className="text-xs text-red-500 mb-1">{modelError}</p>
          )}
          <div className="flex gap-2">
            <div ref={dropdownRef} className="relative flex-1 min-w-0">
              <button
                type="button"
                onClick={() => {
                  if (models.length > 0) {
                    setModelDropdownOpen(!modelDropdownOpen);
                    setTimeout(() => searchRef.current?.focus(), 0);
                  }
                }}
                disabled={models.length === 0 && !loadingModels}
                className={`${css.input} flex items-center justify-between text-left disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <span className={currentModelDisplay ? "text-claude-text-primary" : "text-claude-text-muted"}>
                  {loadingModels
                    ? "Loading models…"
                    : models.length === 0
                      ? (selection.kind === "oauth"
                          ? (oauthAuthorized ? "Select a model…" : "Connect first to browse models")
                          : "No models available")
                      : currentModelDisplay || "Select a model…"}
                </span>
                <svg className="h-4 w-4 text-claude-text-muted flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {modelDropdownOpen && models.length > 0 && (
                <div className="absolute z-50 mt-1 w-full rounded-xl border border-claude-border bg-claude-input shadow-lg">
                  <div className="border-b border-claude-border p-2">
                    <input
                      ref={searchRef}
                      className="w-full rounded-lg border border-claude-border bg-claude-bg px-3 py-1.5 text-sm text-claude-text-primary placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none"
                      placeholder="Search models…"
                      value={modelSearch}
                      onChange={(e) => setModelSearch(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Escape") {
                          setModelDropdownOpen(false);
                          setModelSearch("");
                        }
                        if (e.key === "Enter" && filteredModels.length === 1) {
                          handleModelSelect(filteredModels[0].id);
                        }
                      }}
                    />
                  </div>
                  <div className="max-h-64 overflow-y-auto p-1">
                    {filteredModels.length === 0 && (
                      <div className="px-3 py-4 text-center text-xs text-claude-text-muted">
                        No matching models.
                      </div>
                    )}
                    {filteredModels.map((m) => {
                      const prefix = selection.kind === "oauth" ? selection.field : selection.type;
                      const fullId = `${prefix}/${m.id}`;
                      return (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => handleModelSelect(m.id)}
                          className={`flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-left text-sm transition-colors ${
                            fullId === model
                              ? "bg-claude-accent/10 text-claude-accent font-medium"
                              : "text-claude-text-secondary hover:bg-claude-surface"
                          }`}
                        >
                          <span className="font-mono text-xs truncate">{m.id}</span>
                          {m.name !== m.id && (
                            <span className="text-[10px] text-claude-text-muted ml-2 shrink-0">{m.name}</span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                  <div className="border-t border-claude-border p-2">
                    <p className="text-[10px] text-claude-text-muted text-center">
                      {models.length} model{models.length !== 1 ? "s" : ""} available
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="mt-1.5">
            <button
              type="button"
              onClick={() => {
                const prefix = selection.kind === "oauth" ? selection.field : selection.type;
                const manual = prompt("Enter model ID (e.g. claude-sonnet-4-20250514):", currentModelDisplay);
                if (manual !== null && manual.trim()) {
                  onModelChange(`${prefix}/${manual.trim()}`);
                }
              }}
              className="text-[11px] text-claude-text-muted hover:text-claude-accent transition-colors"
            >
              Or enter model ID manually
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
