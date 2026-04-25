export type MCPConfigField = {
  name: string;
  title: string;
  description: string;
  type?: "string" | "number" | "boolean";
  format?: "password" | "uri" | string;
  "x-widget"?: "file" | string;
  default?: string | number | boolean | null;
  enum?: string[];
  required?: boolean;
};

export type MCPServer = {
  command: string;
  args: string[];
  env: Record<string, string>;
  url: string;
  headers?: Record<string, string>;
  /** When set, only these tool names are registered. Empty/undefined = all tools. */
  enabledTools?: string[];
  /** Config schema the server needs, populated from the registry at install time. */
  configSchema?: MCPConfigField[];
};

export type ApprovalCfg = {
  default_mode: string;
  per_tool: Record<string, string>;
  timeout_seconds: number;
};

export type SoftwareInstalledEntry = {
  name: string;
  description: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  installed_via: string;
  package: string;
  stdin?: boolean;
  installed_at?: string;
  verified?: boolean;
};

export type GuardrailRef = {
  name: string;
  on_fail?: "retry" | "raise" | "fix" | "escalate";
  max_retries?: number;
  pattern?: string | null;
  prompt?: string | null;
  regex_mode?: "block" | "allow";
};

export type ToolsCfg = {
  web: { search: { provider: "duckduckgo" | "brave" | "serpapi"; brave_api_key: string; serpapi_api_key: string; max_results: number } };
  exec: { timeout: number; policy?: { mode: "allow_all" | "deny_all" | "allowlist"; allow: string[]; deny: string[]; relaxed?: boolean } };
  restrict_to_workspace: boolean;
  ssrf_protection?: boolean;
  mcp_servers: Record<string, MCPServer>;
  software?: Record<string, SoftwareInstalledEntry>;
  approval?: ApprovalCfg;
  guardrails?: GuardrailRef[];
};

export type HeartbeatCfg = {
  enabled: boolean;
  interval_s: number;
  cron_expr: string;
  timezone: string;
};

export type SkillsCfg = {
  disabled: string[];
};

export type MCPStatusInfo = {
  name: string;
  status: "connected" | "failed" | "skipped";
  tools: number;
  error?: string;
  needs_auth?: boolean;
  /** OAuth 2.1 resource_metadata URL from WWW-Authenticate on 401. When set,
   *  the UI should open this URL to initiate the OAuth flow (MCP spec, RFC 9728). */
  auth_url?: string;
};

export type SecurityCfg = {
  docker?: { level?: "permissive" | "sandboxed" };
};

export type ProviderConfigSlot = {
  apiKey?: string;
  api_key?: string;
  apiBase?: string;
  api_base?: string;
  extraHeaders?: Record<string, string> | null;
  extra_headers?: Record<string, string> | null;
};

// Values in Agent.providers: per-type slots hold a config dict;
// ``provider_ref`` / ``providerRef`` holds a string id (or null to unbind).
export type ProviderValue = ProviderConfigSlot | string | null;

export type Agent = {
  id: string;
  name: string;
  description: string;
  color?: string;
  model: string;
  status: string;
  status_message?: string;
  enabled: boolean;
  temperature: number;
  max_tokens: number;
  max_tool_iterations: number;
  memory_window: number;
  fault_tolerance?: { max_attempts: number; backoff_factor: number };
  workspace: string;
  tools: ToolsCfg;
  skills?: SkillsCfg;
  channels: Record<string, Record<string, unknown>>;
  // Per-type slots map to config dicts; `provider_ref` / `providerRef` maps to
  // a centrally-managed provider id (or null to unbind).
  providers?: Record<string, ProviderValue>;
  heartbeat?: HeartbeatCfg;
  security?: SecurityCfg;
  mcp_status?: Record<string, MCPStatusInfo>;
  software_warnings?: { key: string; name: string; command: string }[];
  software_installing?: boolean;
  onboarding_completed?: boolean;
  owner_user_id?: string;
  /** Server-reported permission for the current caller on this agent. */
  effective_permission?: "viewer" | "editor" | "manager" | "owner";
};

export type MainTab = "workspace" | "chat" | "jobs" | "logs" | "settings" | "sharing";

export type SettingsTab = "general" | "variables" | "channels" | "tools" | "skills" | "software";

export type FieldDef = { name: string; label: string; type: "text" | "password" | "number" | "toggle" | "tags"; placeholder?: string };

export type TreeNode = { name: string; path: string; isDir: boolean; children: TreeNode[] };

export type LogView = "activity" | "process";

export type ActivityEntry = {
  ts: string;
  type: string;
  content: string;
  channel: string;
  toolName?: string;
  resultStatus?: string;
  durationMs?: number;
  eventId?: string;
};

export type ActivityFilter = "all" | "messages" | "tools" | "lifecycle";

export type CronJobData = {
  id: string;
  name: string;
  enabled: boolean;
  schedule: { kind: string; atMs?: number; everyMs?: number; expr?: string; tz?: string };
  payload: { kind: string; message: string; deliver?: boolean; channel?: string; to?: string };
  state: { nextRunAtMs?: number; lastRunAtMs?: number; lastStatus?: string; lastError?: string };
  createdAtMs: number;
  deleteAfterRun?: boolean;
};

export type SkillInfo = {
  name: string;
  description: string;
  source: "builtin" | "workspace";
  emoji: string;
  enabled: boolean;
  available: boolean;
  always: boolean;
};

export type ProviderDef = { field: string; label: string; keywords: string[]; oauth?: boolean };

export type WsViewMode = "edit" | "preview";
