"""Shared HTTP/SSL configuration helpers.

Provides a single toggle — the ``CLAWFORCE_DISABLE_SSL_VERIFY`` environment
variable — for disabling TLS certificate verification across clawforce,
clawbot, clawlib, and every claw (agent) spawned by the runtime.

When the env var is set to a truthy value (``1``, ``true``, ``yes``, or ``on``,
case-insensitive), outbound HTTPS calls via ``httpx`` and SMTP/IMAP TLS via
``smtplib``/``imaplib`` skip certificate verification. Default behaviour is
unchanged.
"""

from __future__ import annotations

import os
import ssl
import threading

from loguru import logger

ENV_VAR = "CLAWFORCE_DISABLE_SSL_VERIFY"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

_warned = False
_warn_lock = threading.Lock()


def ssl_verify_disabled() -> bool:
    """Return True when the operator has opted out of TLS verification."""
    value = os.environ.get(ENV_VAR)
    if not value:
        return False
    disabled = value.strip().lower() in _TRUTHY
    if disabled:
        _warn_once()
    return disabled


def httpx_verify() -> bool:
    """Return the ``verify=`` value to pass to ``httpx.AsyncClient(...)``."""
    return not ssl_verify_disabled()


def insecure_ssl_context() -> ssl.SSLContext:
    """Return a permissive SSL context for stdlib SMTP/IMAP clients."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _warn_once() -> None:
    global _warned
    if _warned:
        return
    with _warn_lock:
        if _warned:
            return
        _warned = True
        logger.warning(
            f"{ENV_VAR} is set — TLS certificate verification is DISABLED "
            "for all outbound HTTPS and SMTP/IMAP connections. Do not use in production."
        )
