import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { AgentSummary } from "./types";

export const queryKeys = {
  templates: ["templates"] as const,
  templateDetail: (id: string) => ["templates", id] as const,
  specialagents: ["specialagents"] as const,
  agent: (id: string) => ["agents", id] as const,
  agentConfig: (id: string) => ["agents", id, "config"] as const,
  agentVariables: (id: string) => ["agents", id, "variables"] as const,
  agentSkills: (id: string) => ["agents", id, "skills"] as const,
  skillsSearch: (q: string) => ["skills", "search", q] as const,
  customSkills: ["skills", "custom"] as const,
  mcpServers: (q: string) => ["mcp", "search", q] as const,
  customMcpServers: ["mcp", "custom"] as const,
  softwareCatalog: ["software", "catalog"] as const,
  customSoftware: ["software", "custom"] as const,
  planTemplates: ["plan-templates"] as const,
  customPlanTemplates: ["plan-templates", "custom"] as const,
  planTemplate: (id: string) => ["plan-templates", id] as const,
  workspaceFiles: (id: string, root?: string) => ["agents", id, "workspace", root ?? "workspace"] as const,
  workspaceFile: (id: string, path: string) => ["agents", id, "workspace", path] as const,
  plans: ["plans"] as const,
  plan: (id: string) => ["plans", id] as const,
  planArtifacts: (planId: string) => ["plans", planId, "artifacts"] as const,
  planWorkspaceFiles: (planId: string) => ["plans", planId, "workspace"] as const,
  planWorkspaceFile: (planId: string, path: string) => ["plans", planId, "workspace", path] as const,
  planTaskComments: (planId: string, taskId: string) =>
    ["plans", planId, "tasks", taskId, "comments"] as const,
};

export function useTemplates() {
  return useQuery({
    queryKey: queryKeys.templates,
    queryFn: api.templates.list,
    staleTime: 60_000,
  });
}

export function useTemplateDetail(templateId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.templateDetail(templateId!),
    queryFn: () => api.templates.detail(templateId!),
    enabled: !!templateId,
    staleTime: 60_000,
  });
}

export function useSpecialAgents() {
  return useQuery({
    queryKey: queryKeys.specialagents,
    queryFn: api.specialagents.list,
    staleTime: 10_000,
    refetchInterval: (query) => {
      // Poll faster if any agent is in a transitional state
      const data = query.state.data as Array<{ status?: string }> | undefined;
      const hasTransitioning = data?.some(
        (a) => a.status === "provisioning" || a.status === "connecting"
      );
      return hasTransitioning ? 2_000 : 15_000;
    },
  });
}

export function useAllAgents(): { agents: AgentSummary[]; isLoading: boolean } {
  const { data: agents = [], isLoading } = useSpecialAgents();
  return { agents, isLoading };
}

export function useAgent(agentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.agent(agentId!),
    queryFn: () => api.agents.get(agentId!),
    enabled: !!agentId,
    staleTime: 10_000,
  });
}

export function useAgentConfig(agentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.agentConfig(agentId!),
    queryFn: () => api.agents.config(agentId!),
    enabled: !!agentId,
    staleTime: 60_000,
  });
}

export function useWorkspaceFiles(agentId: string | undefined, root?: "workspace" | "profiles") {
  return useQuery({
    queryKey: queryKeys.workspaceFiles(agentId!, root),
    queryFn: () => api.agents.workspaceFiles(agentId!, root),
    enabled: !!agentId,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}

export function useWorkspaceFile(agentId: string | undefined, path: string) {
  return useQuery({
    queryKey: queryKeys.workspaceFile(agentId!, path),
    queryFn: () => api.agents.workspaceFile(agentId!, path),
    enabled: !!agentId && !!path,
    staleTime: 5_000,
    refetchInterval: 10_000,
  });
}

export function useCreateSpecialAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; description?: string; template?: string; color?: string }) => api.specialagents.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.specialagents }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.agents.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.specialagents }),
  });
}

export function useStartAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.agents.start(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: queryKeys.agent(id) });
      qc.invalidateQueries({ queryKey: queryKeys.specialagents });
    },
  });
}

export function useStopAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.agents.stop(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: queryKeys.agent(id) });
      qc.invalidateQueries({ queryKey: queryKeys.specialagents });
    },
  });
}

export function useAgentSkills(agentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.agentSkills(agentId!),
    queryFn: () => api.agents.skills(agentId!),
    enabled: !!agentId,
    staleTime: 60_000,
  });
}

export function useSaveConfig(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (config: unknown) => api.agents.updateConfig(agentId, config),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.agentConfig(agentId) }),
  });
}

export function useAgentVariables(agentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.agentVariables(agentId!),
    queryFn: () => api.agents.variables(agentId!),
    enabled: !!agentId,
    staleTime: 60_000,
  });
}

export function useSaveVariables(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { variables: Record<string, string>; secret_keys: string[] }) =>
      api.agents.updateVariables(agentId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.agentVariables(agentId) }),
  });
}

export function useSaveWorkspaceFile(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      api.agents.saveWorkspaceFile(agentId, path, content),
    onSuccess: (_data, { path }) => {
      qc.invalidateQueries({ queryKey: ["agents", agentId, "workspace"] });
      qc.invalidateQueries({ queryKey: queryKeys.workspaceFile(agentId, path) });
    },
  });
}

export function useDeleteWorkspaceFile(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => api.agents.deleteWorkspaceFile(agentId, path),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentId, "workspace"] });
    },
  });
}

export function useRenameWorkspaceFile(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, newName }: { path: string; newName: string }) =>
      api.agents.renameWorkspaceFile(agentId, path, newName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentId, "workspace"] });
    },
  });
}

export function useMoveWorkspaceFile(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ srcPath, destPath }: { srcPath: string; destPath: string }) =>
      api.agents.moveWorkspaceFile(agentId, srcPath, destPath),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentId, "workspace"] });
    },
  });
}

export function useSearchSkills(query: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.skillsSearch(query),
    queryFn: () => api.skills.search(query, 30),
    enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useCustomSkills() {
  return useQuery({
    queryKey: queryKeys.customSkills,
    queryFn: () => api.skills.listCustom(),
    staleTime: 30_000,
  });
}

export function useAddCustomSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entry: import("./types").AddCustomSkillPayload) =>
      api.skills.addCustom(entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customSkills });
      qc.invalidateQueries({ queryKey: ["skills", "search"] });
    },
  });
}

export function useUpdateCustomSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, entry }: { slug: string; entry: import("./types").AddCustomSkillPayload }) =>
      api.skills.updateCustom(slug, entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customSkills });
      qc.invalidateQueries({ queryKey: ["skills", "search"] });
    },
  });
}

export function useDeleteCustomSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.skills.deleteCustom(slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customSkills });
      qc.invalidateQueries({ queryKey: ["skills", "search"] });
    },
  });
}

export function useSearchMcpServers(query: string = "", enabled: boolean = true) {
  return useQuery({
    queryKey: queryKeys.mcpServers(query),
    queryFn: () => api.mcpRegistry.search(query.trim(), 18),
    staleTime: 60_000,
    enabled,
  });
}

export function useInstallMcpServer(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (config: {
      server_id: string;
      server_name: string;
      command?: string;
      args?: string[];
      env?: Record<string, string>;
      url?: string;
    }) => api.mcpRegistry.install(agentId, config),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agentConfig(agentId) });
    },
  });
}

export function useCustomMcpServers() {
  return useQuery({
    queryKey: queryKeys.customMcpServers,
    queryFn: () => api.mcpRegistry.listCustom(),
    staleTime: 30_000,
  });
}

export function useAddCustomMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entry: import("./types").AddCustomMcpPayload) =>
      api.mcpRegistry.addCustom(entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customMcpServers });
      qc.invalidateQueries({ queryKey: ["mcp", "search"] });
    },
  });
}

export function useUpdateCustomMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, entry }: { slug: string; entry: import("./types").AddCustomMcpPayload }) =>
      api.mcpRegistry.updateCustom(slug, entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customMcpServers });
      qc.invalidateQueries({ queryKey: ["mcp", "search"] });
    },
  });
}

export function useDeleteCustomMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.mcpRegistry.deleteCustom(slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customMcpServers });
      qc.invalidateQueries({ queryKey: ["mcp", "search"] });
    },
  });
}

export function useSoftwareCatalog() {
  return useQuery({
    queryKey: queryKeys.softwareCatalog,
    queryFn: () => api.software.catalog(),
    staleTime: 60_000,
  });
}

export function useCustomSoftware() {
  return useQuery({
    queryKey: queryKeys.customSoftware,
    queryFn: () => api.software.listCustom(),
    staleTime: 30_000,
  });
}

export function useAddCustomSoftware() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entry: import("./types").AddCustomSoftwarePayload) =>
      api.software.addCustom(entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customSoftware });
      qc.invalidateQueries({ queryKey: queryKeys.softwareCatalog });
    },
  });
}

export function useUpdateCustomSoftware() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ softwareId, entry }: { softwareId: string; entry: import("./types").AddCustomSoftwarePayload }) =>
      api.software.updateCustom(softwareId, entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customSoftware });
      qc.invalidateQueries({ queryKey: queryKeys.softwareCatalog });
    },
  });
}

export function useDeleteCustomSoftware() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (softwareId: string) => api.software.deleteCustom(softwareId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customSoftware });
      qc.invalidateQueries({ queryKey: queryKeys.softwareCatalog });
    },
  });
}

export function usePlanTemplates() {
  return useQuery({
    queryKey: queryKeys.planTemplates,
    queryFn: () => api.planTemplates.list(),
    staleTime: 60_000,
  });
}

export function useCustomPlanTemplates() {
  return useQuery({
    queryKey: queryKeys.customPlanTemplates,
    queryFn: () => api.planTemplates.listCustom(),
    staleTime: 30_000,
  });
}

export function useAddCustomPlanTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entry: import("./types").AddPlanTemplatePayload) =>
      api.planTemplates.add(entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customPlanTemplates });
      qc.invalidateQueries({ queryKey: queryKeys.planTemplates });
    },
  });
}

export function useUpdateCustomPlanTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, entry }: { templateId: string; entry: import("./types").AddPlanTemplatePayload }) =>
      api.planTemplates.update(templateId, entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customPlanTemplates });
      qc.invalidateQueries({ queryKey: queryKeys.planTemplates });
    },
  });
}

export function useDeleteCustomPlanTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (templateId: string) => api.planTemplates.delete(templateId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.customPlanTemplates });
      qc.invalidateQueries({ queryKey: queryKeys.planTemplates });
    },
  });
}

export function useInstallSoftware(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { software_id: string; env?: Record<string, string> }) =>
      api.software.install(agentId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agentConfig(agentId) });
    },
  });
}

export function useUninstallSoftware(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.software.uninstall(agentId, { slug }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agentConfig(agentId) });
      qc.invalidateQueries({ queryKey: queryKeys.agent(agentId) });
    },
  });
}

export function useInstallSkill(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, version }: { slug: string; version?: string }) =>
      api.agents.installSkill(agentId, slug, version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agentSkills(agentId) });
    },
  });
}

export function useUninstallSkill(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.agents.uninstallSkill(agentId, slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.agentSkills(agentId) });
    },
  });
}

export function usePlans() {
  return useQuery({
    queryKey: queryKeys.plans,
    queryFn: api.plans.list,
    staleTime: 5_000,
    refetchInterval: 8_000,
  });
}

export function usePlan(planId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.plan(planId!),
    queryFn: () => api.plans.get(planId!),
    enabled: !!planId,
    staleTime: 3_000,
    refetchInterval: (query) => {
      const status = (query.state.data as { status?: string } | undefined)?.status;
      return status === "active" ? 4_000 : 15_000;
    },
  });
}

export function useCreatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; description?: string; template_id?: string }) =>
      api.plans.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plans }),
  });
}

export function useUpdatePlan(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<import("./types").Plan>) => api.plans.update(planId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.plan(planId) });
      qc.invalidateQueries({ queryKey: queryKeys.plans });
    },
  });
}

export function useDeletePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => api.plans.delete(planId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plans }),
  });
}

export function useAddTask(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { column_id: string; title?: string; description?: string; agent_id?: string }) =>
      api.plans.addTask(planId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useAddColumn(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      title: string;
      kind?: import("./types").ColumnKind;
      position?: number | null;
    }) => api.plans.addColumn(planId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useUpdateColumn(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      columnId,
      data,
    }: {
      columnId: string;
      data: { title?: string; kind?: import("./types").ColumnKind; position?: number | null };
    }) => api.plans.updateColumn(planId, columnId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useDeleteColumn(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (columnId: string) => api.plans.deleteColumn(planId, columnId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useUpdateTask(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: Partial<import("./types").PlanTask> }) =>
      api.plans.updateTask(planId, taskId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useReviewTask(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      taskId,
      decision,
      note,
    }: {
      taskId: string;
      decision: import("./types").ReviewStatus;
      note?: string;
    }) => api.plans.reviewTask(planId, taskId, { decision, note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useDeleteTask(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => api.plans.deleteTask(planId, taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useAssignAgent(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => api.plans.assignAgent(planId, agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useRemoveAgent(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => api.plans.removeAgent(planId, agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function useActivatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => api.plans.activate(planId),
    onSuccess: (_data, planId) => {
      qc.invalidateQueries({ queryKey: queryKeys.plan(planId) });
      qc.invalidateQueries({ queryKey: queryKeys.plans });
    },
  });
}

export function useDeactivatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => api.plans.deactivate(planId),
    onSuccess: (_data, planId) => {
      qc.invalidateQueries({ queryKey: queryKeys.plan(planId) });
      qc.invalidateQueries({ queryKey: queryKeys.plans });
    },
  });
}

export function useCompletePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => api.plans.complete(planId),
    onSuccess: (_data, planId) => {
      qc.invalidateQueries({ queryKey: queryKeys.plan(planId) });
      qc.invalidateQueries({ queryKey: queryKeys.plans });
    },
  });
}

export function usePlanAssistant(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, message }: { agentId: string; message: string }) =>
      api.plans.assistant(planId, agentId, message),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.plan(planId) }),
  });
}

export function usePlanArtifacts(planId: string | undefined, taskId?: string) {
  return useQuery({
    queryKey: [...queryKeys.planArtifacts(planId!), taskId ?? ""] as const,
    queryFn: () => api.plans.listArtifacts(planId!, taskId),
    enabled: !!planId,
    staleTime: 5_000,
    refetchInterval: 10_000,
  });
}

export function useUploadArtifact(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.plans.uploadArtifact(planId, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planArtifacts(planId) }),
  });
}

export function useDeleteArtifact(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (artifactId: string) => api.plans.deleteArtifact(planId, artifactId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planArtifacts(planId) }),
  });
}

export function useRenameArtifact(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ artifactId, newName }: { artifactId: string; newName: string }) =>
      api.plans.renameArtifact(planId, artifactId, newName),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planArtifacts(planId) }),
  });
}

export function useMoveArtifact(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ artifactId, taskId }: { artifactId: string; taskId: string }) =>
      api.plans.moveArtifact(planId, artifactId, taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planArtifacts(planId) }),
  });
}

// Plan Workspace Filesystem Hooks

export function usePlanWorkspaceFiles(planId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.planWorkspaceFiles(planId!),
    queryFn: () => api.plans.workspaceFiles(planId!),
    enabled: !!planId,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}

export function usePlanWorkspaceFile(planId: string | undefined, path: string) {
  return useQuery({
    queryKey: queryKeys.planWorkspaceFile(planId!, path),
    queryFn: () => api.plans.workspaceFile(planId!, path),
    enabled: !!planId && !!path,
    staleTime: 5_000,
  });
}

export function useSavePlanWorkspaceFile(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      api.plans.saveWorkspaceFile(planId, path, content),
    onSuccess: (_data, { path }) => {
      qc.invalidateQueries({ queryKey: queryKeys.planWorkspaceFiles(planId) });
      qc.invalidateQueries({ queryKey: queryKeys.planWorkspaceFile(planId, path) });
    },
  });
}

export function useUploadPlanWorkspaceFile(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, path }: { file: File; path?: string }) =>
      api.plans.uploadWorkspaceFile(planId, file, path),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planWorkspaceFiles(planId) }),
  });
}

export function useDeletePlanWorkspaceFile(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => api.plans.deleteWorkspaceFile(planId, path),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planWorkspaceFiles(planId) }),
  });
}

export function useRenamePlanWorkspaceFile(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, newName }: { path: string; newName: string }) =>
      api.plans.renameWorkspaceFile(planId, path, newName),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planWorkspaceFiles(planId) }),
  });
}

export function useMovePlanWorkspaceFile(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ srcPath, destPath }: { srcPath: string; destPath: string }) =>
      api.plans.moveWorkspaceFile(planId, srcPath, destPath),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planWorkspaceFiles(planId) }),
  });
}

export function useCreatePlanWorkspaceFolder(planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => api.plans.createWorkspaceFolder(planId, path),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.planWorkspaceFiles(planId) }),
  });
}

export function useTaskComments(planId: string | undefined, taskId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.planTaskComments(planId ?? "", taskId ?? ""),
    queryFn: () => api.plans.listComments(planId!, taskId!),
    enabled: !!planId && !!taskId,
    staleTime: 5_000,
  });
}

export function useAddComment(planId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => api.plans.addComment(planId, taskId, content),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.planTaskComments(planId, taskId) });
      qc.invalidateQueries({ queryKey: queryKeys.plan(planId) });
    },
  });
}

export function useDeleteComment(planId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (commentId: string) => api.plans.deleteComment(planId, commentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.planTaskComments(planId, taskId) });
      qc.invalidateQueries({ queryKey: queryKeys.plan(planId) });
    },
  });
}
