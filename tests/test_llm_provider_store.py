"""Tests for LLMProviderStore: centrally-managed LLM provider credentials."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from specops.core.database import Database
from specops.core.store.llm_providers import LLMProviderStore


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture
def store_plain(db: Database) -> LLMProviderStore:
    return LLMProviderStore(db, fernet=None)


@pytest.fixture
def store_encrypted(db: Database) -> LLMProviderStore:
    return LLMProviderStore(db, fernet=Fernet(Fernet.generate_key()))


class TestCrud:
    def test_list_empty(self, store_plain: LLMProviderStore):
        assert store_plain.list() == []
        assert store_plain.list_public() == []

    def test_create_and_get(self, store_plain: LLMProviderStore):
        row = store_plain.create(name="OpenAI-prod", type="openai", api_key="sk-test")
        assert row["name"] == "OpenAI-prod"
        assert row["type"] == "openai"
        # Redacted by default
        assert row["api_key"].startswith("***")

        fetched = store_plain.get(row["id"], with_secrets=True)
        assert fetched is not None
        assert fetched["api_key"] == "sk-test"

    def test_create_duplicate_name_raises(self, store_plain: LLMProviderStore):
        store_plain.create(name="Dup", type="openai", api_key="sk-a")
        with pytest.raises(ValueError, match="already exists"):
            store_plain.create(name="Dup", type="anthropic", api_key="sk-b")

    def test_list_with_and_without_secrets(self, store_plain: LLMProviderStore):
        store_plain.create(name="A", type="openai", api_key="sk-longkey-1234")
        [row_redacted] = store_plain.list(with_secrets=False)
        assert row_redacted["api_key"].startswith("***")
        assert row_redacted["api_key"].endswith("1234")

        [row_full] = store_plain.list(with_secrets=True)
        assert row_full["api_key"] == "sk-longkey-1234"

    def test_list_public_excludes_credentials(self, store_plain: LLMProviderStore):
        store_plain.create(name="A", type="openai", api_key="sk-secret")
        public = store_plain.list_public()
        assert public == [{"id": public[0]["id"], "name": "A", "type": "openai"}]
        for row in public:
            assert "api_key" not in row
            assert "api_base" not in row

    def test_update_patches_fields(self, store_plain: LLMProviderStore):
        row = store_plain.create(name="Orig", type="openai", api_key="sk-orig")
        updated = store_plain.update(row["id"], name="Renamed", api_key="sk-new")
        assert updated is not None
        assert updated["name"] == "Renamed"

        with_secrets = store_plain.get(row["id"], with_secrets=True)
        assert with_secrets["api_key"] == "sk-new"

    def test_update_redacted_api_key_preserved(self, store_plain: LLMProviderStore):
        row = store_plain.create(name="A", type="openai", api_key="sk-keep-me")
        # Simulate the UI round-trip: client sends back the redacted value
        store_plain.update(row["id"], api_key="***e-me", name="A-renamed")
        with_secrets = store_plain.get(row["id"], with_secrets=True)
        assert with_secrets["api_key"] == "sk-keep-me"
        assert with_secrets["name"] == "A-renamed"

    def test_update_nonexistent_returns_none(self, store_plain: LLMProviderStore):
        assert store_plain.update("does-not-exist", name="x") is None

    def test_delete(self, store_plain: LLMProviderStore):
        row = store_plain.create(name="A", type="openai", api_key="sk")
        assert store_plain.delete(row["id"]) is True
        assert store_plain.get(row["id"]) is None
        assert store_plain.delete(row["id"]) is False


class TestEncryption:
    def test_roundtrip(self, store_encrypted: LLMProviderStore):
        row = store_encrypted.create(name="Enc", type="openai", api_key="sk-top-secret")
        fetched = store_encrypted.get(row["id"], with_secrets=True)
        assert fetched["api_key"] == "sk-top-secret"

    def test_blob_is_encrypted_at_rest(self, db: Database):
        store = LLMProviderStore(db, fernet=Fernet(Fernet.generate_key()))
        store.create(name="X", type="openai", api_key="sk-supersecretvalue")
        with db.connection() as conn:
            row = conn.execute("SELECT config_json FROM llm_providers WHERE name = 'X'").fetchone()
        assert row is not None
        assert "supersecretvalue" not in row["config_json"]

    def test_wrong_key_fails(self, db: Database):
        a = LLMProviderStore(db, fernet=Fernet(Fernet.generate_key()))
        row = a.create(name="A", type="openai", api_key="sk")
        b = LLMProviderStore(db, fernet=Fernet(Fernet.generate_key()))
        with pytest.raises(InvalidToken):
            b.get(row["id"], with_secrets=True)
