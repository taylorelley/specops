"""Shared technical library (clawlib) for clawforce and clawbot.

Subpackages:
- storage: StorageBackend, LocalStorage, S3Storage, get_storage_backend, get_storage_root
- registry: SkillRegistry, MCPRegistry, SoftwareRegistry, PlanTemplateRegistry, get_skill_registry, get_mcp_registry, get_software_registry, get_plan_template_registry
- activity: ActivityEvent, ActivityLog, ActivityLogRegistry
- config: Config, load_config, save_config, deep_merge
- http: httpx_verify, insecure_ssl_context, ssl_verify_disabled
- utils: deep_merge
"""

from clawlib.http import httpx_verify, insecure_ssl_context, ssl_verify_disabled

__all__ = [
    "httpx_verify",
    "insecure_ssl_context",
    "ssl_verify_disabled",
]
