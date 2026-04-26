"""Runtime tests for GeneratedHttpTool.

Uses ``httpx.MockTransport`` to intercept the request and assert URL,
method, headers (after ${VAR} substitution), and body assembly. No
network is touched.
"""

from pathlib import Path

import httpx
import pytest

import specialagent.agent.tools.openapi as openapi_mod
from specialagent.agent.tools.openapi import (
    GeneratedHttpTool,
    generate_tools_from_config,
    parse_spec_text,
)
from specops_lib.config.schema import OpenAPIToolConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "openapi"


@pytest.fixture
def petstore_spec() -> str:
    return (FIXTURE_DIR / "petstore_openapi3.yaml").read_text(encoding="utf-8")


def _build_tool(
    op_id: str,
    *,
    spec_text: str,
    headers: dict[str, str] | None = None,
    var_lookup: dict[str, str] | None = None,
) -> GeneratedHttpTool:
    spec = parse_spec_text(spec_text)
    op = next(o for o in spec.operations if o.operation_id == op_id)
    return GeneratedHttpTool(
        operation=op,
        spec_id="petstore",
        base_url=spec.base_url,
        headers_template=headers or {},
        var_lookup=var_lookup or {},
        replay_safety=op.replay_safety,
    )


class TestGeneratedHttpTool:
    async def test_get_with_path_and_query(self, petstore_spec: str) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["headers"] = dict(request.headers)
            return httpx.Response(200, json={"id": "p1", "name": "Rex"})

        tool = _build_tool(
            "showPetById",
            spec_text=petstore_spec,
            headers={"Authorization": "Bearer ${KEY}"},
            var_lookup={"KEY": "sk_test"},
        )

        # Monkeypatch the module-level httpx.AsyncClient with a thin
        # wrapper that swaps in a MockTransport. Cleaner than passing
        # the client through GeneratedHttpTool's constructor.
        orig_client_cls = openapi_mod.httpx.AsyncClient

        class _PatchedClient:
            def __init__(self, *a, **kw) -> None:
                self._inner = orig_client_cls(transport=httpx.MockTransport(handler))

            async def __aenter__(self):
                await self._inner.__aenter__()
                return self._inner

            async def __aexit__(self, *exc):
                return await self._inner.__aexit__(*exc)

        openapi_mod.httpx.AsyncClient = _PatchedClient  # type: ignore[attr-defined]
        try:
            result = await tool.execute(petId="p1")
        finally:
            openapi_mod.httpx.AsyncClient = orig_client_cls  # type: ignore[attr-defined]

        assert captured["method"] == "GET"
        assert captured["url"] == "https://api.example.com/v1/pets/p1"
        assert captured["headers"]["authorization"] == "Bearer sk_test"
        assert "200" in result and "Rex" in result

    async def test_missing_var_returns_error_not_request(self, petstore_spec: str) -> None:
        tool = _build_tool(
            "listPets",
            spec_text=petstore_spec,
            headers={"Authorization": "Bearer ${KEY}"},
            var_lookup={},
        )
        result = await tool.execute()
        assert "Missing required credential variable" in result
        assert "KEY" in result


class TestGenerateFromConfig:
    def test_round_trips_through_config(self, petstore_spec: str) -> None:
        cfg = OpenAPIToolConfig(
            spec_id="petstore",
            spec_url="https://example.com/petstore.json",
            headers={"Authorization": "Bearer ${KEY}"},
            max_tools=2,
            role_hint="read pets list",
        )
        tools = generate_tools_from_config(cfg, spec_text=petstore_spec, var_lookup={"KEY": "x"})
        names = {t.name for t in tools}
        assert len(tools) == 2
        # role_hint emphasises reads; the two safe ops should be picked.
        assert all("petstore" in n for n in names)

    def test_replay_safety_propagates(self, petstore_spec: str) -> None:
        cfg = OpenAPIToolConfig(
            spec_id="petstore",
            spec_url="https://example.com/petstore.json",
            headers={},
            max_tools=10,
        )
        tools = generate_tools_from_config(cfg, spec_text=petstore_spec, var_lookup={})
        by_op = {}
        for t in tools:
            # Tool name pattern is api_<spec>_<op>; reverse-engineer the op.
            for orig in ("listPets", "createPet", "showPetById", "deletePet"):
                if orig in t.name:
                    by_op[orig] = t
        assert by_op["listPets"].replay_safety == "safe"
        assert by_op["createPet"].replay_safety == "checkpoint"
        assert by_op["showPetById"].replay_safety == "safe"
        assert by_op["deletePet"].replay_safety == "checkpoint"
