"""Parser tests against fixture specs (OpenAPI 3, Swagger 2, Postman v2.1)."""

import json
from pathlib import Path

import pytest
import yaml

from specialagent.agent.tools.openapi import (
    detect_dialect,
    parse_spec_text,
    rank_operations,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "openapi"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


class TestDetectDialect:
    def test_openapi3(self) -> None:
        data = yaml.safe_load(_read("petstore_openapi3.yaml"))
        assert detect_dialect(data) == "openapi3"

    def test_swagger2(self) -> None:
        data = yaml.safe_load(_read("petstore_swagger2.yaml"))
        assert detect_dialect(data) == "swagger2"

    def test_postman2(self) -> None:
        data = json.loads(_read("postman2.json"))
        assert detect_dialect(data) == "postman2"

    def test_unknown(self) -> None:
        assert detect_dialect({"random": True}) == "unknown"


class TestParseOpenapi3:
    def test_extracts_operations(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        assert spec.source_dialect == "openapi3"
        assert spec.title == "Petstore"
        assert spec.base_url == "https://api.example.com/v1"
        ids = {op.operation_id for op in spec.operations}
        assert ids == {"listPets", "createPet", "showPetById", "deletePet"}

    def test_replay_safety_extension(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        by_id = {op.operation_id: op for op in spec.operations}
        assert by_id["listPets"].replay_safety == "safe"
        assert by_id["showPetById"].replay_safety == "safe"
        assert by_id["createPet"].replay_safety == "checkpoint"
        assert by_id["deletePet"].replay_safety == "checkpoint"

    def test_path_param_recognised(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        show = next(op for op in spec.operations if op.operation_id == "showPetById")
        assert any(p["name"] == "petId" and p["in"] == "path" for p in show.parameters)

    def test_request_body_attached(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        create = next(op for op in spec.operations if op.operation_id == "createPet")
        assert create.request_body is not None
        assert create.request_body["content_type"] == "application/json"


class TestParseSwagger2:
    def test_extracts_operations(self) -> None:
        spec = parse_spec_text(_read("petstore_swagger2.yaml"))
        assert spec.source_dialect == "swagger2"
        assert spec.base_url == "https://api.example.com/v2"
        ids = {op.operation_id for op in spec.operations}
        assert ids == {"listPets", "addPet"}

    def test_body_param_promoted_to_request_body(self) -> None:
        spec = parse_spec_text(_read("petstore_swagger2.yaml"))
        add = next(op for op in spec.operations if op.operation_id == "addPet")
        assert add.request_body is not None
        # The "in: body" param must NOT also appear under parameters[].
        assert all(p["in"] != "body" for p in add.parameters)


class TestParsePostman:
    def test_extracts_items(self) -> None:
        spec = parse_spec_text(_read("postman2.json"))
        assert spec.source_dialect == "postman2"
        assert spec.base_url == "https://api.example.com"
        names = {op.operation_id for op in spec.operations}
        assert "Get_user" in names
        assert "List_orders" in names

    def test_method_normalised(self) -> None:
        spec = parse_spec_text(_read("postman2.json"))
        assert all(op.method == "GET" for op in spec.operations)


class TestRankOperations:
    def test_caps_at_max_tools(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        ranked = rank_operations(spec.operations, max_tools=2)
        assert len(ranked) == 2

    def test_enabled_operations_exact_match(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        ranked = rank_operations(spec.operations, enabled_operations=["showPetById"], max_tools=10)
        assert [op.operation_id for op in ranked] == ["showPetById"]

    def test_role_hint_prefers_overlap(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        # role hint mentions 'read' which appears in tags of listPets / showPetById
        ranked = rank_operations(spec.operations, role_hint="read pets list", max_tools=2)
        assert {op.operation_id for op in ranked} == {"listPets", "showPetById"}

    def test_no_role_hint_preserves_order(self) -> None:
        spec = parse_spec_text(_read("petstore_openapi3.yaml"))
        ranked = rank_operations(spec.operations, max_tools=10)
        assert [op.operation_id for op in ranked] == [op.operation_id for op in spec.operations]


class TestParseErrors:
    def test_unknown_dialect_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_spec_text('{"random": true}')
