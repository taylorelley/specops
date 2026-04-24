"""Tests for resolve_provider_ref: looks up an admin-managed provider row and
materialises credentials into the config dict sent to the agent worker.
"""

from pathlib import Path

import pytest

from specops.core.database import Database
from specops.core.providers_resolve import resolve_provider_ref
from specops.core.store.llm_providers import LLMProviderStore


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture
def store(db: Database) -> LLMProviderStore:
    return LLMProviderStore(db, fernet=None)


class TestResolveProviderRef:
    def test_noop_when_no_providers(self, store: LLMProviderStore):
        cfg = {"agents": {"defaults": {"model": "x"}}}
        assert resolve_provider_ref(cfg, store) == cfg

    def test_noop_when_provider_ref_missing(self, store: LLMProviderStore):
        cfg = {"providers": {"openai": {"api_key": "direct"}}}
        assert resolve_provider_ref(cfg, store) == cfg

    def test_resolves_openai_provider(self, store: LLMProviderStore):
        row = store.create(
            name="OpenAI-prod",
            type="openai",
            api_key="sk-resolved-key",
            api_base="",
        )
        cfg = {"providers": {"provider_ref": row["id"]}}
        resolved = resolve_provider_ref(cfg, store)
        assert resolved["providers"]["openai"]["api_key"] == "sk-resolved-key"
        # provider_ref is kept so the UI round-trips the selection
        assert resolved["providers"]["provider_ref"] == row["id"]

    def test_resolves_with_api_base(self, store: LLMProviderStore):
        row = store.create(
            name="Custom-gateway",
            type="custom",
            api_key="key",
            api_base="https://example.com/v1",
        )
        cfg = {"providers": {"provider_ref": row["id"]}}
        resolved = resolve_provider_ref(cfg, store)
        assert resolved["providers"]["custom"]["api_key"] == "key"
        assert resolved["providers"]["custom"]["api_base"] == "https://example.com/v1"

    def test_overrides_stale_inline_slot(self, store: LLMProviderStore):
        """Central row is authoritative — stale inline api_key/extra_headers are replaced."""
        row = store.create(name="A", type="anthropic", api_key="sk-new")
        cfg = {
            "providers": {
                "provider_ref": row["id"],
                # These came from a prior inline config; they must not leak through.
                "anthropic": {"extra_headers": {"X": "Y"}, "api_key": "stale"},
            }
        }
        resolved = resolve_provider_ref(cfg, store)
        assert resolved["providers"]["anthropic"]["api_key"] == "sk-new"
        # No extra_headers on the row → none in the resolved slot.
        assert "extra_headers" not in resolved["providers"]["anthropic"]

    def test_unknown_ref_is_noop(self, store: LLMProviderStore):
        cfg = {"providers": {"provider_ref": "does-not-exist"}}
        assert resolve_provider_ref(cfg, store) == cfg

    def test_oauth_slot_left_untouched(self, store: LLMProviderStore):
        row = store.create(name="A", type="openai", api_key="sk")
        cfg = {
            "providers": {
                "provider_ref": row["id"],
                "chatgpt": {"api_key": "oauth-token-json"},
            }
        }
        resolved = resolve_provider_ref(cfg, store)
        # OAuth provider slot must remain
        assert resolved["providers"]["chatgpt"] == {"api_key": "oauth-token-json"}
        assert resolved["providers"]["openai"]["api_key"] == "sk"

    def test_camelcase_provider_ref_alias(self, store: LLMProviderStore):
        row = store.create(name="A", type="openai", api_key="sk-alias")
        cfg = {"providers": {"providerRef": row["id"]}}
        resolved = resolve_provider_ref(cfg, store)
        assert resolved["providers"]["openai"]["api_key"] == "sk-alias"

    def test_returns_new_dict_not_mutating_input(self, store: LLMProviderStore):
        row = store.create(name="A", type="openai", api_key="sk")
        cfg = {"providers": {"provider_ref": row["id"]}}
        resolved = resolve_provider_ref(cfg, store)
        # input dict should not gain the resolved slot
        assert "openai" not in cfg["providers"]
        assert "openai" in resolved["providers"]

    def test_extra_headers_preserved_when_set(self, store: LLMProviderStore):
        row = store.create(
            name="H",
            type="custom",
            api_key="k",
            api_base="https://x/v1",
            extra_headers={"X-Org": "acme"},
        )
        cfg = {"providers": {"provider_ref": row["id"]}}
        resolved = resolve_provider_ref(cfg, store)
        assert resolved["providers"]["custom"]["extra_headers"] == {"X-Org": "acme"}

    def test_extra_headers_dropped_when_row_has_none(self, store: LLMProviderStore):
        """Row without extra_headers must clear any stale inline value."""
        row = store.create(name="H2", type="openai", api_key="sk")
        cfg = {
            "providers": {
                "provider_ref": row["id"],
                "openai": {"extra_headers": {"Stale": "value"}},
            }
        }
        resolved = resolve_provider_ref(cfg, store)
        assert "extra_headers" not in resolved["providers"]["openai"]

    def test_empty_api_key_still_populates_slot(self, store: LLMProviderStore):
        """The worker needs the slot key present even when the key is blank."""
        row = store.create(name="Empty", type="openai", api_key="")
        cfg = {"providers": {"provider_ref": row["id"]}}
        resolved = resolve_provider_ref(cfg, store)
        assert resolved["providers"]["openai"] == {"api_key": ""}
