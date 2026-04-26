"""Durable execution journal types and helpers.

The journal extends the :class:`specops_lib.activity.ActivityEvent`
envelope with optional fields scoped to an in-flight turn (an
``Execution``). When ``execution_id`` is present on an ``ActivityEvent``
the control plane also writes the row to the ``execution_events``
table, where it powers crash recovery and durable HITL resume.
"""

from specops_lib.execution.events import (
    EVENT_KINDS,
    EXECUTION_STATUSES,
    REPLAY_SAFETIES,
    EventKind,
    ExecutionStatus,
    ReplaySafety,
    derive_idempotency_key,
    journal_fields,
    make_event,
)
from specops_lib.execution.journal import (
    Journal,
    JournalLookup,
    LocalJournalLookup,
    NullJournal,
    canonical_args,
)

__all__ = [
    "EVENT_KINDS",
    "REPLAY_SAFETIES",
    "EXECUTION_STATUSES",
    "EventKind",
    "ExecutionStatus",
    "ReplaySafety",
    "Journal",
    "JournalLookup",
    "LocalJournalLookup",
    "NullJournal",
    "canonical_args",
    "derive_idempotency_key",
    "journal_fields",
    "make_event",
]
