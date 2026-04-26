export type MCPServerConfig = {
  command: string;
  args: string[];
  env: Record<string, string>;
  url: string;
  headers?: Record<string, string>;
  /** When set, only these tool names are registered. Empty/undefined = all tools. */
  enabledTools?: string[];
};

export type MCPServerStatusInfo = {
  name: string;
  status: "connected" | "failed" | "skipped";
  tools: number;
  error?: string;
};

export type WebSearchConfig = {
  provider: "duckduckgo" | "brave" | "serpapi";
  brave_api_key: string;
  serpapi_api_key: string;
  max_results: number;
};

export type ShellPolicyConfig = {
  mode: "allow_all" | "deny_all" | "allowlist";
  allow: string[];
  deny: string[];
  relaxed?: boolean;
};

export type FaultToleranceConfig = {
  max_attempts: number;
  backoff_factor: number;
};

export type SoftwareCatalogEntry = {
  id: string;
  name: string;
  author: string;
  description: string;
  version: string;
  categories: string[];
  install: { type: string; package: string };
  run: { command: string; args: string[]; stdin?: boolean };
  required_env: string[];
  icon?: string;
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

export type SoftwareInstallResult = {
  ok: boolean;
  slug: string;
  message: string;
  logs: string;
  exit_code: number;
  verified: boolean;
};

export type AddCustomSoftwarePayload = {
  id: string;
  name: string;
  description?: string;
  author?: string;
  version?: string;
  categories?: string[];
  install: { type: string; package: string };
  run: { command: string; args?: string[]; stdin?: boolean };
  post_install?: { command: string; args?: string[]; daemon?: boolean; env?: Record<string, string> };
  required_env?: string[];
};

export type SecretsConfig = {
  env: Record<string, string>;
};

export type ToolsConfig = {
  web: { search: WebSearchConfig };
  exec: { timeout: number; policy?: ShellPolicyConfig };
  restrict_to_workspace: boolean;
  ssrf_protection?: boolean;
  mcp_servers: Record<string, MCPServerConfig>;
  software?: Record<string, SoftwareInstalledEntry>;
};

export type SoftwareWarning = {
  key: string;
  name: string;
  command: string;
};

export type SecurityConfig = {
  docker?: {
    level?: "permissive" | "sandboxed";
  };
};

export type SharePermission = "viewer" | "editor" | "manager";
/** The caller's effective permission on a resource (server-computed). */
export type EffectivePermission = SharePermission | "owner";

export type Agent = {
  id: string;
  name: string;
  description: string;
  model: string;
  status: string;
  status_message?: string;
  enabled: boolean;
  temperature: number;
  max_tokens: number;
  max_tool_iterations: number;
  memory_window: number;
  max_tool_output_chars: number;
  fault_tolerance?: FaultToleranceConfig;
  workspace: string;
  tools: ToolsConfig;
  channels: Record<string, Record<string, unknown>>;
  providers?: Record<string, Record<string, unknown>>;
  skills?: { disabled: string[] };
  heartbeat?: Record<string, unknown>;
  security?: SecurityConfig;
  color?: string;
  mcp_status?: Record<string, MCPServerStatusInfo>;
  software_warnings?: SoftwareWarning[];
  software_installing?: boolean;
  onboarding_completed?: boolean;
  owner_user_id?: string;
  effective_permission?: EffectivePermission;
};

export type AgentSummary = {
  id: string;
  name: string;
  status: string;
  status_message?: string;
  color?: string;
  channels_enabled?: string[];
  owner_user_id?: string;
  effective_permission?: EffectivePermission;
};

export type InboxEvent = {
  id: string;
  agent_id: string;
  agent_name: string;
  agent_color?: string;
  timestamp: string;
  event_type: string;
  content: string;
  tool_name?: string;
  result_status?: string;
  duration_ms?: number;
};

export type SkillsConfig = {
  disabled: string[];
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

export type SkillSource = "agentskill.sh" | "self-hosted";

export type MarketplaceSkill = {
  slug: string;
  name: string;
  description: string;
  version: string;
  author: string;
  downloads: number;
  categories?: string[];
  homepage?: string;
  repository?: string;
  required_env?: string[];
  source?: SkillSource;
};

export type CustomSkillEntry = {
  slug: string;
  name: string;
  description?: string;
  author?: string;
  version?: string;
  categories?: string[];
  homepage?: string;
  repository?: string;
  license?: string;
  required_env?: string[];
  skill_content: string;
};

export type AddCustomSkillPayload = {
  slug: string;
  name: string;
  description?: string;
  author?: string;
  version?: string;
  categories?: string[];
  homepage?: string;
  repository?: string;
  license?: string;
  required_env?: string[];
  skill_content: string;
};

export type McpSource = "official" | "self-hosted";

export type MCPRegistryServer = {
  id: string;
  slug: string;
  name: string;
  description: string;
  repository: string;
  homepage: string;
  version: string;
  license: string;
  author: string;
  verified: boolean;
  is_verified: boolean;
  downloads: number;
  created_at: string;
  updated_at: string;
  categories: string[];
  capabilities: string[];
  install_config: Record<string, unknown> | Record<string, unknown>[];
  config_schema?: unknown[];
  required_env?: string[];
  source?: McpSource;
};

export type CustomMcpInstallConfig =
  | { command: string; args: string[] }
  | { url: string };

export type CustomMcpEntry = {
  slug: string;
  name: string;
  description?: string;
  author?: string;
  version?: string;
  categories?: string[];
  homepage?: string;
  repository?: string;
  license?: string;
  required_env?: string[];
  install_config: CustomMcpInstallConfig;
};

export type AddCustomMcpPayload = CustomMcpEntry;

export type WorkspaceFiles = {
  files: string[];
};

export type ColumnKind = "standard" | "review";

export type PlanTemplateColumn = {
  title: string;
  position?: number | null;
  /** "review" marks the column as a human-approval gate. Defaults to "standard". */
  kind?: ColumnKind;
};

export type PlanTemplateTask = {
  title: string;
  description?: string;
  /** Short column name ("todo", "in-progress", ...) or a column title. Empty = first column. */
  column?: string;
  /** Agent id to preassign this task to. Empty / unknown = task stays unassigned. */
  agent_id?: string;
  /** Whether this task must pass a human review when in a review column. Defaults true. */
  requires_review?: boolean;
};

export type ReviewStatus = "pending" | "approved" | "rejected";

export type PlanTemplate = {
  id: string;
  name: string;
  description?: string;
  author?: string;
  categories?: string[];
  columns?: PlanTemplateColumn[];
  tasks: PlanTemplateTask[];
  /** Agent ids to preassign at the plan level. Missing agents are skipped. */
  agent_ids?: string[];
};

export type AddPlanTemplatePayload = {
  id: string;
  name: string;
  description?: string;
  author?: string;
  categories?: string[];
  columns?: PlanTemplateColumn[];
  tasks: PlanTemplateTask[];
  agent_ids?: string[];
};

export type PlanTask = {
  id: string;
  title: string;
  description: string;
  column_id: string;
  agent_id: string;
  position: number;
  requires_review?: boolean;
  review_status?: ReviewStatus | null;
  reviewed_by?: string;
  reviewed_at?: string;
  review_note?: string;
  created_at?: string;
  updated_at?: string;
};

export type PlanColumn = {
  id: string;
  title: string;
  position: number;
  kind?: ColumnKind;
};

export type Plan = {
  id: string;
  name: string;
  description: string;
  status: string;
  columns: PlanColumn[];
  tasks: PlanTask[];
  agent_ids: string[];
  created_at: string;
  updated_at: string;
  owner_user_id?: string;
  effective_permission?: EffectivePermission;
};

export type Share = {
  user_id: string;
  username: string;
  permission: SharePermission;
};

export type PlanArtifact = {
  id: string;
  task_id: string;
  name: string;
  content_type: string;
  content: string;
  file_path: string;
  size: number;
  created_at: string;
};

export type TaskComment = {
  id: string;
  task_id: string;
  author_type: "admin" | "agent";
  author_id: string;
  author_name: string;
  content: string;
  created_at: string;
};

export type ApiToolEntry = {
  id: string;
  name: string;
  description?: string;
  author?: string;
  version?: string;
  categories?: string[];
  spec_url: string;
  headers?: Record<string, string>;
  default_max_tools?: number;
  required_env?: string[];
  homepage?: string;
  source?: "bundled" | "self-hosted";
};

export type AddCustomApiToolPayload = {
  id: string;
  name: string;
  description?: string;
  author?: string;
  version?: string;
  categories?: string[];
  homepage?: string;
  spec_url: string;
  headers?: Record<string, string>;
  default_max_tools?: number;
  required_env?: string[];
};

export type InstallApiToolPayload = {
  spec_id: string;
  headers?: Record<string, string>;
  enabled_operations?: string[] | null;
  max_tools?: number;
  base_url_override?: string | null;
  role_hint?: string;
};

export type AgentApiToolEntry = {
  spec_id: string;
  spec_url: string;
  max_tools: number;
  enabled_operations?: string[] | null;
  role_hint?: string;
};

export type Execution = {
  id: string;
  agent_id: string;
  plan_id?: string;
  session_key?: string;
  channel?: string;
  chat_id?: string;
  status: "running" | "paused" | "failed" | "completed";
  last_step_id?: string;
  error_message?: string;
  pending_resume?: number;
  created_at: string;
  updated_at: string;
  paused_at?: string;
};

export type ExecutionEvent = {
  id: number;
  execution_id: string;
  event_id: string;
  step_id?: string;
  event_kind: string;
  replay_safety?: string | null;
  idempotency_key?: string | null;
  tool_name?: string | null;
  result_status?: string | null;
  duration_ms?: number | null;
  payload_json?: string | null;
  timestamp: string;
  agent_id?: string;
};

export type ResolveDecision = "approve" | "reject";
