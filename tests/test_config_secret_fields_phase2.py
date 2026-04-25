"""Phase-2 config redaction guards.

Covers the new ``OpenAPIToolConfig.headers`` redaction and the drive-by
fix that adds ``headers`` and ``env`` to ``MCPServerConfig.secret_fields``.
"""

from specops_lib.config.helpers import redact
from specops_lib.config.schema import MCPServerConfig, OpenAPIToolConfig


class TestOpenAPIToolConfigSchema:
    def test_secret_fields_includes_headers(self) -> None:
        assert "headers" in OpenAPIToolConfig.secret_fields

    def test_redact_at_full_path(self) -> None:
        full = {
            "tools": {
                "openapi_tools": {
                    "stripe": {
                        "spec_id": "stripe",
                        "spec_url": "https://example.com/spec.json",
                        "headers": {"Authorization": "Bearer sk_live_abcdef"},
                    }
                }
            }
        }
        redacted = redact(full)
        # The whole headers value collapses to a placeholder.
        assert redacted["tools"]["openapi_tools"]["stripe"]["headers"] == "***" or redacted[
            "tools"
        ]["openapi_tools"]["stripe"]["headers"].startswith("***")


class TestMCPServerConfigSchema:
    def test_secret_fields_now_set(self) -> None:
        assert "headers" in MCPServerConfig.secret_fields
        assert "env" in MCPServerConfig.secret_fields

    def test_redact_mcp_headers(self) -> None:
        full = {
            "tools": {
                "mcp_servers": {
                    "linear": {
                        "url": "https://mcp.example.com",
                        "headers": {"Authorization": "Bearer LINEAR_KEY"},
                        "env": {"API_KEY": "secret"},
                    }
                }
            }
        }
        redacted = redact(full)
        srv = redacted["tools"]["mcp_servers"]["linear"]
        assert srv["headers"] != {"Authorization": "Bearer LINEAR_KEY"}
        assert srv["env"] != {"API_KEY": "secret"}
