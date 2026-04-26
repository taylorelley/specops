"""OpenAPI / Swagger / Postman → SpecialAgent tool generator.

Phase 2 of the Agentspan idea-adoption project. Given an
:class:`OpenAPIToolConfig` (spec URL, header template, top-N cap), this
module:

1. Fetches the spec (OpenAPI 3 / Swagger 2 / Postman v2.1) and parses
   it into a normalised :class:`ApiSpec` shape.
2. Filters to the top-N most relevant operations using a token-set
   overlap with the agent's role hint.
3. Generates one :class:`GeneratedHttpTool` per operation.

At runtime each generated tool builds an ``httpx`` request with
``${VAR}``-substituted headers / path / query parameters, applies the
existing SSRF policy, and returns the response body to the LLM.

The dependency footprint is intentionally minimal: ``httpx`` and
``yaml`` are already part of SpecOps; ``prance`` is preferred when
installed but the module falls back to a hand-rolled OpenAPI 3 parser
covering the 80% case (no $ref dereferencing for non-trivial schemas;
operations with refs are skipped with a logged warning).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import httpx
import yaml

from specialagent.agent.tools.base import Tool
from specialagent.agent.tools.utils import truncate_output
from specialagent.agent.tools.web import _validate_url
from specops_lib.config.schema import OpenAPIToolConfig
from specops_lib.config.templating import (
    MissingVariableError,
    substitute_vars_in_mapping,
)
from specops_lib.http import httpx_verify

logger = logging.getLogger(__name__)

# Cap so a misconfigured spec can't run away.
MAX_TOOLS_HARD_CAP = 64

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


# ---------------------------------------------------------------------------
# Normalised spec types
# ---------------------------------------------------------------------------


@dataclass
class ApiOperation:
    """One operation extracted from an OpenAPI / Swagger / Postman spec."""

    operation_id: str
    method: str  # GET / POST / PUT / PATCH / DELETE
    path: str  # e.g. /v1/customers/{id}
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    # Each parameter: {"name", "in", "required", "schema"}; "in" ∈ {path, query, header}.
    parameters: list[dict[str, Any]] = field(default_factory=list)
    # Request body: {"content_type", "schema"} or None.
    request_body: dict[str, Any] | None = None
    replay_safety: str = "checkpoint"  # parser respects ``x-replay-safety`` extension


@dataclass
class ApiSpec:
    """Normalised spec ready for tool generation."""

    title: str
    version: str
    base_url: str
    operations: list[ApiOperation]
    source_dialect: str  # "openapi3" | "swagger2" | "postman2"


# ---------------------------------------------------------------------------
# Spec ingestion
# ---------------------------------------------------------------------------


def detect_dialect(data: Any) -> str:
    """Identify the spec dialect from a parsed JSON/YAML document."""
    if not isinstance(data, dict):
        return "unknown"
    if "openapi" in data and str(data["openapi"]).startswith("3"):
        return "openapi3"
    if data.get("swagger") == "2.0":
        return "swagger2"
    info = data.get("info") or {}
    schema = info.get("schema") if isinstance(info, dict) else None
    if isinstance(schema, str) and "schema.postman.com" in schema:
        return "postman2"
    if "item" in data and "info" in data and isinstance(data.get("info"), dict):
        return "postman2"
    return "unknown"


def parse_spec_text(content: str | bytes, source_url: str = "") -> ApiSpec:
    """Parse a spec document. Accepts JSON or YAML; auto-detects dialect."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    text = content.strip()
    data: Any
    if text.startswith("{") or text.startswith("["):
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    dialect = detect_dialect(data)
    if dialect == "openapi3":
        return _parse_openapi3(data, source_url)
    if dialect == "swagger2":
        return _parse_swagger2(data, source_url)
    if dialect == "postman2":
        return _parse_postman(data, source_url)
    raise ValueError(f"Unrecognised API spec dialect for {source_url or '<inline>'}")


def _parse_openapi3(data: dict[str, Any], source_url: str) -> ApiSpec:
    info = data.get("info") or {}
    title = str(info.get("title") or source_url or "openapi")
    version = str(info.get("version") or "")
    servers = data.get("servers") or []
    base_url = ""
    if servers and isinstance(servers, list) and isinstance(servers[0], dict):
        base_url = str(servers[0].get("url") or "")
    operations: list[ApiOperation] = []
    paths = data.get("paths") or {}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_level_params = path_item.get("parameters") or []
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            op_id = str(op.get("operationId") or _synth_op_id(method, path))
            params = list(path_level_params) + list(op.get("parameters") or [])
            request_body = _openapi3_request_body(op.get("requestBody"))
            operations.append(
                ApiOperation(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    summary=str(op.get("summary") or ""),
                    description=str(op.get("description") or ""),
                    tags=[str(t) for t in (op.get("tags") or [])],
                    parameters=[_normalise_parameter(p) for p in params if isinstance(p, dict)],
                    request_body=request_body,
                    replay_safety=str(op.get("x-replay-safety") or "checkpoint"),
                )
            )
    return ApiSpec(
        title=title,
        version=version,
        base_url=base_url,
        operations=operations,
        source_dialect="openapi3",
    )


def _openapi3_request_body(rb: Any) -> dict[str, Any] | None:
    if not isinstance(rb, dict):
        return None
    content = rb.get("content")
    if not isinstance(content, dict):
        return None
    # Prefer JSON; fall back to whatever's first.
    chosen = content.get("application/json")
    content_type = "application/json"
    if not isinstance(chosen, dict):
        for ct, body in content.items():
            if isinstance(body, dict):
                chosen = body
                content_type = str(ct)
                break
    if not isinstance(chosen, dict):
        return None
    schema = chosen.get("schema") or {}
    return {"content_type": content_type, "schema": schema}


def _parse_swagger2(data: dict[str, Any], source_url: str) -> ApiSpec:
    info = data.get("info") or {}
    title = str(info.get("title") or source_url or "swagger")
    version = str(info.get("version") or "")
    host = str(data.get("host") or "")
    base_path = str(data.get("basePath") or "")
    schemes = data.get("schemes") or ["https"]
    base_url = f"{schemes[0]}://{host}{base_path}" if host else ""
    operations: list[ApiOperation] = []
    paths = data.get("paths") or {}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_level_params = path_item.get("parameters") or []
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            op_id = str(op.get("operationId") or _synth_op_id(method, path))
            raw_params = list(path_level_params) + list(op.get("parameters") or [])
            params = [_normalise_parameter(p) for p in raw_params if isinstance(p, dict)]
            request_body = _swagger2_request_body(raw_params)
            operations.append(
                ApiOperation(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    summary=str(op.get("summary") or ""),
                    description=str(op.get("description") or ""),
                    tags=[str(t) for t in (op.get("tags") or [])],
                    parameters=[p for p in params if p["in"] != "body"],
                    request_body=request_body,
                    replay_safety=str(op.get("x-replay-safety") or "checkpoint"),
                )
            )
    return ApiSpec(
        title=title,
        version=version,
        base_url=base_url,
        operations=operations,
        source_dialect="swagger2",
    )


def _swagger2_request_body(raw_params: list[Any]) -> dict[str, Any] | None:
    for p in raw_params:
        if not isinstance(p, dict):
            continue
        if p.get("in") == "body":
            schema = p.get("schema") or {}
            return {"content_type": "application/json", "schema": schema}
    return None


def _parse_postman(data: dict[str, Any], source_url: str) -> ApiSpec:
    info = data.get("info") or {}
    title = str(info.get("name") or source_url or "postman-collection")
    version = str(info.get("version") or "")
    operations: list[ApiOperation] = []
    base_url = ""
    items = data.get("item") or []
    for item in _flatten_postman(items):
        request = item.get("request")
        if not isinstance(request, dict):
            continue
        method = str(request.get("method") or "GET").upper()
        url_obj = request.get("url")
        url_string = ""
        path = ""
        host = ""
        if isinstance(url_obj, str):
            url_string = url_obj
            path = url_obj
        elif isinstance(url_obj, dict):
            url_string = str(url_obj.get("raw") or "")
            host_parts = url_obj.get("host") or []
            if isinstance(host_parts, list):
                host = ".".join(str(h) for h in host_parts)
            path_parts = url_obj.get("path") or []
            if isinstance(path_parts, list):
                path = "/" + "/".join(str(p) for p in path_parts)
            elif isinstance(path_parts, str):
                path = path_parts
        if not base_url and host:
            scheme = "https"
            if isinstance(url_obj, dict) and url_obj.get("protocol"):
                scheme = str(url_obj["protocol"])
            base_url = f"{scheme}://{host}"
        op_id = str(item.get("name") or _synth_op_id(method, path or url_string))
        operations.append(
            ApiOperation(
                operation_id=_sanitise_op_id(op_id),
                method=method,
                path=path or url_string,
                summary=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                tags=[],
                parameters=[],
                request_body=None,
                replay_safety="checkpoint",
            )
        )
    return ApiSpec(
        title=title,
        version=version,
        base_url=base_url,
        operations=operations,
        source_dialect="postman2",
    )


def _flatten_postman(items: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "request" in item:
            out.append(item)
        nested = item.get("item")
        if isinstance(nested, list):
            out.extend(_flatten_postman(nested))
    return out


def _normalise_parameter(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(p.get("name") or ""),
        "in": str(p.get("in") or "query"),
        "required": bool(p.get("required") or False),
        "description": str(p.get("description") or ""),
        "schema": p.get("schema") or _swagger_schema_from_param(p),
    }


def _swagger_schema_from_param(p: dict[str, Any]) -> dict[str, Any]:
    """Swagger 2 stores type/format directly on the parameter; lift to a JSON Schema dict."""
    if not isinstance(p, dict):
        return {"type": "string"}
    out: dict[str, Any] = {}
    for key in ("type", "format", "enum", "items", "minimum", "maximum"):
        if key in p:
            out[key] = p[key]
    return out or {"type": "string"}


def _synth_op_id(method: str, path: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")
    return f"{method.lower()}_{slug}"


_INVALID_TOOL_NAME = re.compile(r"[^A-Za-z0-9_]")


def _sanitise_op_id(op_id: str) -> str:
    cleaned = _INVALID_TOOL_NAME.sub("_", op_id).strip("_")
    return cleaned or "op"


# ---------------------------------------------------------------------------
# Top-N filter
# ---------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def rank_operations(
    operations: list[ApiOperation],
    *,
    role_hint: str = "",
    enabled_operations: list[str] | None = None,
    max_tools: int = 64,
) -> list[ApiOperation]:
    """Pick up to ``max_tools`` most relevant operations.

    Selection precedence:
      1. ``enabled_operations`` exact match (by ``operation_id``); kept in spec order.
      2. Token-set overlap with ``role_hint`` against tags + summary + path.
      3. Stable tiebreak on shorter ``operation_id`` first.
    """
    cap = min(max_tools, MAX_TOOLS_HARD_CAP)
    if enabled_operations:
        wanted = set(enabled_operations)
        return [op for op in operations if op.operation_id in wanted][:cap]
    if not role_hint or not role_hint.strip():
        # Stable cap, preserve spec order.
        return operations[:cap]
    role_tokens = _tokens(role_hint)
    scored: list[tuple[int, int, ApiOperation]] = []
    for op in operations:
        haystack = " ".join([*op.tags, op.summary, op.path, op.description])
        overlap = len(role_tokens & _tokens(haystack))
        scored.append((-overlap, len(op.operation_id), op))
    scored.sort(key=lambda t: (t[0], t[1], t[2].operation_id))
    return [op for _, __, op in scored[:cap]]


# ---------------------------------------------------------------------------
# Generated HTTP tool
# ---------------------------------------------------------------------------


class GeneratedHttpTool(Tool):
    """A single tool generated from one OpenAPI/Postman operation.

    The tool's parameters JSON Schema mirrors the operation's path,
    query, header, and body parameters. At execute time the tool
    interpolates ``${VAR}`` placeholders in the configured headers from
    the agent's variable lookup, builds the request, and returns the
    response body (truncated to ``max_chars``).
    """

    def __init__(
        self,
        *,
        operation: ApiOperation,
        spec_id: str,
        base_url: str,
        headers_template: Mapping[str, str],
        var_lookup: Mapping[str, str],
        replay_safety: str = "checkpoint",
        max_chars: int = 8192,
        ssrf_protection: bool = True,
        timeout_s: float = 30.0,
    ) -> None:
        self._op = operation
        self._spec_id = spec_id
        self._base_url = base_url.rstrip("/")
        self._headers_template = dict(headers_template)
        self._var_lookup = dict(var_lookup)
        self._max_chars = max_chars
        self._ssrf_protection = ssrf_protection
        self._timeout_s = timeout_s
        # Instance-level so each generated tool can carry its own value
        # (the class-level default lives on Tool); ToolsManager reads
        # via getattr() which honours the instance attr first.
        self.replay_safety = replay_safety
        self._tool_name = self._build_tool_name()

    def _build_tool_name(self) -> str:
        prefix = f"api_{_sanitise_op_id(self._spec_id)}_"
        return (prefix + _sanitise_op_id(self._op.operation_id))[:64]

    @property
    def name(self) -> str:
        return self._tool_name

    @property
    def description(self) -> str:
        bits = [
            f"{self._op.method} {self._op.path}",
            self._op.summary or self._op.description or "",
        ]
        return " — ".join(b for b in bits if b)[:400]

    @property
    def parameters(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self._op.parameters:
            schema = dict(p.get("schema") or {"type": "string"})
            schema["description"] = (
                p.get("description") or f"{p.get('in', 'query')} parameter {p['name']}"
            )
            properties[p["name"]] = schema
            if p.get("required"):
                required.append(p["name"])
        if self._op.request_body:
            properties["body"] = {
                "type": "object",
                "description": "Request body (JSON object)",
            }
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            headers = substitute_vars_in_mapping(self._headers_template, self._var_lookup)
        except MissingVariableError as e:
            return json.dumps(
                {"error": f"Missing required credential variable: {e}", "tool": self._tool_name}
            )

        path = self._op.path
        for p in self._op.parameters:
            if p["in"] == "path" and p["name"] in kwargs:
                path = path.replace("{" + p["name"] + "}", str(kwargs[p["name"]]))
        query: dict[str, Any] = {}
        for p in self._op.parameters:
            if p["in"] == "query" and p["name"] in kwargs:
                query[p["name"]] = kwargs[p["name"]]
        for p in self._op.parameters:
            if p["in"] == "header" and p["name"] in kwargs:
                headers[p["name"]] = str(kwargs[p["name"]])

        url = self._base_url + path if path.startswith("/") else f"{self._base_url}/{path}"
        if not url.startswith(("http://", "https://")):
            return json.dumps({"error": "spec missing servers/base_url; cannot build absolute URL"})
        ok, msg = _validate_url(url)
        if not ok:
            return json.dumps({"error": f"URL validation failed: {msg}", "url": url})

        body = kwargs.get("body") if self._op.request_body else None

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, verify=httpx_verify(), follow_redirects=True
            ) as client:
                resp = await client.request(
                    self._op.method,
                    url,
                    params=query or None,
                    headers=headers,
                    json=body,
                )
                ct = resp.headers.get("content-type", "")
                text = resp.text
                summary = {
                    "status": resp.status_code,
                    "content_type": ct,
                    "body": text,
                }
                payload = json.dumps(summary, ensure_ascii=False)
                return truncate_output(payload, self._max_chars)
        except httpx.HTTPError as exc:
            return json.dumps({"error": f"HTTP error: {exc}", "url": url})


# ---------------------------------------------------------------------------
# High-level helpers used by the tools manager
# ---------------------------------------------------------------------------


async def fetch_spec(
    spec_url: str,
    *,
    cache_path: Path | None = None,
    timeout_s: float = 30.0,
) -> str:
    """Fetch a spec from disk (cache_path) or HTTP and return the raw text."""
    if cache_path and cache_path.exists():
        try:
            return cache_path.read_text(encoding="utf-8")
        except OSError:
            pass
    async with httpx.AsyncClient(timeout=timeout_s, verify=httpx_verify()) as client:
        resp = await client.get(spec_url, follow_redirects=True)
        resp.raise_for_status()
        text = resp.text
    if cache_path:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")
        except OSError:
            logger.warning("Failed to cache spec at %s", cache_path)
    return text


def generate_tools_from_config(
    cfg: OpenAPIToolConfig,
    *,
    spec_text: str,
    var_lookup: Mapping[str, str],
    ssrf_protection: bool = True,
    max_chars: int = 8192,
) -> list[GeneratedHttpTool]:
    """Parse + filter + instantiate tools for one OpenAPIToolConfig."""
    spec = parse_spec_text(spec_text, cfg.spec_url)
    base_url = cfg.base_url_override or spec.base_url
    if not base_url:
        logger.warning(
            "OpenAPI spec %s has no servers/host — generated tools will fail at runtime",
            cfg.spec_id,
        )
    operations = rank_operations(
        spec.operations,
        role_hint=cfg.role_hint,
        enabled_operations=cfg.enabled_operations,
        max_tools=cfg.max_tools,
    )
    tools: list[GeneratedHttpTool] = []
    for op in operations:
        tools.append(
            GeneratedHttpTool(
                operation=op,
                spec_id=cfg.spec_id,
                base_url=base_url,
                headers_template=cfg.headers,
                var_lookup=var_lookup,
                replay_safety=op.replay_safety or "checkpoint",
                max_chars=max_chars,
                ssrf_protection=ssrf_protection,
            )
        )
    return tools


__all__ = [
    "ApiOperation",
    "ApiSpec",
    "GeneratedHttpTool",
    "MAX_TOOLS_HARD_CAP",
    "detect_dialect",
    "fetch_spec",
    "generate_tools_from_config",
    "parse_spec_text",
    "rank_operations",
]
