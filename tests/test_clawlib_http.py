"""Tests for the CLAWFORCE_DISABLE_SSL_VERIFY toggle in clawlib.http."""

from __future__ import annotations

import ssl

import pytest

from clawlib import http as clawlib_http
from clawlib.http import (
    ENV_VAR,
    httpx_verify,
    insecure_ssl_context,
    ssl_verify_disabled,
)


@pytest.fixture(autouse=True)
def _reset_warn_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the one-shot warning flag between tests so each run is independent."""
    monkeypatch.setattr(clawlib_http, "_warned", False, raising=True)


@pytest.fixture
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)


@pytest.mark.parametrize("value", ["1", "true", "YES", "On", "TrUe"])
def test_truthy_values_disable_verification(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ENV_VAR, value)
    assert ssl_verify_disabled() is True
    assert httpx_verify() is False


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_falsy_values_keep_verification(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ENV_VAR, value)
    assert ssl_verify_disabled() is False
    assert httpx_verify() is True


def test_unset_env_keeps_verification(_clear_env: None) -> None:
    assert ssl_verify_disabled() is False
    assert httpx_verify() is True


def test_insecure_ssl_context_skips_verification() -> None:
    ctx = insecure_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


def test_warning_is_emitted_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "1")
    calls: list[str] = []
    monkeypatch.setattr(clawlib_http.logger, "warning", lambda msg: calls.append(msg))

    for _ in range(5):
        assert ssl_verify_disabled() is True

    assert len(calls) == 1
    assert ENV_VAR in calls[0]
