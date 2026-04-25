import { useEffect, useState } from "react";
import Modal from "./Modal";
import { useAddCustomApiTool } from "../lib/queries";
import type { AddCustomApiToolPayload } from "../lib/types";

const css = {
  btn: "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
  input:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
  textarea:
    "w-full rounded-lg border border-claude-border bg-claude-input px-3 py-2 text-sm font-mono placeholder:text-claude-text-muted focus:border-claude-accent focus:outline-none focus:ring-1 focus:ring-claude-accent/30 transition-colors",
};

const SLUG_RE = /^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$/;

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function AddCustomApiToolModal({ open, onClose }: Props) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [specUrl, setSpecUrl] = useState("");
  const [headersJson, setHeadersJson] = useState(
    '{\n  "Authorization": "Bearer ${YOUR_KEY}"\n}',
  );
  const [requiredEnv, setRequiredEnv] = useState("");
  const [maxTools, setMaxTools] = useState(64);
  const [error, setError] = useState<string | null>(null);

  const addMutation = useAddCustomApiTool();
  const submitting = addMutation.isPending;

  useEffect(() => {
    if (!open) {
      setId("");
      setName("");
      setDescription("");
      setSpecUrl("");
      setHeadersJson('{\n  "Authorization": "Bearer ${YOUR_KEY}"\n}');
      setRequiredEnv("");
      setMaxTools(64);
      setError(null);
    }
  }, [open]);

  async function handleSubmit() {
    setError(null);
    if (!SLUG_RE.test(id)) {
      setError(
        "id must be lowercase letters, digits, dashes, or underscores (no leading/trailing separator)",
      );
      return;
    }
    if (!name.trim()) {
      setError("name is required");
      return;
    }
    let parsedSpecUrl: URL;
    try {
      parsedSpecUrl = new URL(specUrl);
    } catch {
      setError("spec_url must be a valid http(s) URL");
      return;
    }
    if (!["http:", "https:"].includes(parsedSpecUrl.protocol)) {
      setError("spec_url must be http or https");
      return;
    }
    let headers: Record<string, string> = {};
    try {
      const parsed = JSON.parse(headersJson || "{}");
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        for (const [k, v] of Object.entries(parsed)) {
          if (typeof v !== "string") throw new Error(`header ${k} must be a string`);
          headers[k] = v;
        }
      } else {
        throw new Error("headers must be a JSON object");
      }
    } catch (e) {
      setError(`Headers JSON: ${e instanceof Error ? e.message : "invalid"}`);
      return;
    }
    const required_env = requiredEnv
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const payload: AddCustomApiToolPayload = {
      id,
      name,
      description,
      spec_url: specUrl,
      headers,
      default_max_tools: maxTools,
      required_env,
    };
    try {
      await addMutation.mutateAsync(payload);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add custom API tool");
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add custom API tool">
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
              id
            </label>
            <input
              className={css.input}
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="internal-billing"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
              Name
            </label>
            <input
              className={css.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Internal Billing"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
            Description
          </label>
          <input
            className={css.input}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Short summary"
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
            Spec URL
          </label>
          <input
            className={css.input}
            value={specUrl}
            onChange={(e) => setSpecUrl(e.target.value)}
            placeholder="https://api.example.com/openapi.json"
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
            Headers template (JSON)
          </label>
          <textarea
            className={css.textarea}
            rows={4}
            value={headersJson}
            onChange={(e) => setHeadersJson(e.target.value)}
          />
          <p className="text-xs text-claude-text-muted mt-1">
            Use <code>${"${VAR_NAME}"}</code> placeholders for credentials. The
            user supplies the values at install time.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
              Required env (comma-separated)
            </label>
            <input
              className={css.input}
              value={requiredEnv}
              onChange={(e) => setRequiredEnv(e.target.value)}
              placeholder="MY_API_KEY"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1 text-claude-text-secondary">
              Default max tools
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
        </div>

        {error && (
          <div className="text-sm text-red-500 bg-red-500/10 border border-red-500/30 rounded-md p-2">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className={`${css.btn} border border-claude-border bg-claude-input hover:bg-claude-surface text-claude-text-primary`}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className={`${css.btn} bg-claude-accent text-white hover:opacity-90`}
            disabled={submitting}
          >
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
