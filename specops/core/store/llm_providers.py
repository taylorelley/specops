"""LLMProviderStore: admin-managed LLM provider credentials (one row per named instance).

Rows are keyed by UUID so multiple entries of the same provider type may coexist
(e.g. an "OpenAI-prod" and an "OpenAI-dev"). ``config_json`` holds the
``{api_key, api_base, extra_headers}`` blob, encrypted when ``SECRETS_MASTER_KEY``
is set (same Fernet pattern as ``AgentConfigStore`` / ``AgentVariablesStore``).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from specops.core.database import Database


def _redact_key(value: str) -> str:
    if not value:
        return ""
    return "***" + value[-4:] if len(value) > 4 else "***"


class LLMProviderStore:
    """CRUD for centrally-managed LLM provider credentials in SQLite.

    Note: this store deliberately does not inherit ``BaseRepository[T]`` — it
    stores an encrypted JSON blob, not a single Pydantic model per column, so
    the generic CRUD helpers in ``BaseRepository`` don't apply. It mirrors the
    pattern used by ``AgentConfigStore`` and ``AgentVariablesStore``.
    """

    def __init__(self, db: Database, fernet: Fernet | None = None) -> None:
        self._db = db
        self._fernet = fernet

    def _encrypt_blob(self, data: str) -> str:
        if self._fernet:
            return self._fernet.encrypt(data.encode()).decode()
        return data

    def _decrypt_blob(self, stored: str | None) -> str:
        if not stored:
            return "{}"
        if self._fernet:
            return self._fernet.decrypt(stored.encode()).decode()
        return stored

    def _row_to_dict(self, row, *, with_secrets: bool) -> dict:
        try:
            cfg = json.loads(self._decrypt_blob(row["config_json"]))
        except (json.JSONDecodeError, TypeError):
            cfg = {}
        api_key = str(cfg.get("api_key") or "")
        api_base = cfg.get("api_base") or ""
        extra_headers = cfg.get("extra_headers") or None
        out: dict = {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "api_base": api_base,
            "extra_headers": extra_headers,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if with_secrets:
            out["api_key"] = api_key
        else:
            out["api_key"] = _redact_key(api_key)
        return out

    def list(self, *, with_secrets: bool = False) -> list[dict]:
        """Return all providers. With redacted api_key by default."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, type, config_json, created_at, updated_at "
                "FROM llm_providers ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_dict(r, with_secrets=with_secrets) for r in rows]

    def list_public(self) -> list[dict]:
        """Non-admin-safe list: id, name, type only (no credentials)."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, type FROM llm_providers ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [{"id": r["id"], "name": r["name"], "type": r["type"]} for r in rows]

    def get(self, provider_id: str, *, with_secrets: bool = False) -> dict | None:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT id, name, type, config_json, created_at, updated_at "
                "FROM llm_providers WHERE id = ?",
                (provider_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row, with_secrets=with_secrets)

    def create(
        self,
        *,
        name: str,
        type: str,
        api_key: str,
        api_base: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        """Insert a new provider row. Raises ValueError on unique-name conflict."""
        now = datetime.now(timezone.utc).isoformat()
        provider_id = uuid.uuid4().hex
        cfg = {
            "api_key": api_key or "",
            "api_base": api_base or "",
            "extra_headers": extra_headers or None,
        }

        blob = self._encrypt_blob(json.dumps(cfg))
        try:
            with self._db.connection() as conn:
                conn.execute(
                    "INSERT INTO llm_providers (id, name, type, config_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (provider_id, name, type, blob, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Provider name '{name}' already exists") from exc
        return self.get(provider_id, with_secrets=False) or {}

    def update(
        self,
        provider_id: str,
        *,
        name: str | None = None,
        type: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict | None:
        """Patch a provider. Omitted fields keep stored values. ``api_key`` starting
        with ``***`` is treated as redacted and preserved.
        """
        existing = self.get(provider_id, with_secrets=True)
        if not existing:
            return None

        new_name = name if name is not None else existing["name"]
        new_type = type if type is not None else existing["type"]

        if api_key is None or (isinstance(api_key, str) and api_key.startswith("***")):
            new_api_key = existing["api_key"]
        else:
            new_api_key = api_key

        new_api_base = api_base if api_base is not None else existing.get("api_base") or ""
        new_extra_headers = (
            extra_headers if extra_headers is not None else existing.get("extra_headers")
        )

        cfg = {
            "api_key": new_api_key,
            "api_base": new_api_base,
            "extra_headers": new_extra_headers or None,
        }
        blob = self._encrypt_blob(json.dumps(cfg))
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._db.connection() as conn:
                conn.execute(
                    "UPDATE llm_providers SET name = ?, type = ?, config_json = ?, updated_at = ? "
                    "WHERE id = ?",
                    (new_name, new_type, blob, now, provider_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Provider name '{new_name}' already exists") from exc
        return self.get(provider_id, with_secrets=False)

    def delete(self, provider_id: str) -> bool:
        with self._db.connection() as conn:
            c = conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
        return c.rowcount > 0
