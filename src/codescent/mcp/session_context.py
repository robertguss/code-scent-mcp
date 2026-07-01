from __future__ import annotations

import contextvars
import uuid
from typing import Final

# One stable session id per running server process. MCP tool calls that do not
# carry an explicit ``session_id`` record their telemetry under this id, and the
# read tools (``context_stats`` / ``resume_task``) default to it -- so the
# context / token-savings stats and the resume trail are populated for the live
# session without the agent having to thread a session id through every call.
#
# Previously every emitter early-returned when ``session_id is None`` (which is
# what an agent that never passes one produces), so the whole tool-call event
# stream was silently unwritten. A ContextVar leaves room for a real
# per-connection id to override this later; today the process id IS the session,
# which is correct for CodeScent's single-local-agent model and survives a
# client-side context compaction (the server process does not restart).
_PROCESS_SESSION_ID: Final = f"live-{uuid.uuid4().hex[:12]}"

_ambient_session: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "codescent_ambient_session",
    default=None,
)


def ambient_session_id() -> str:
    """Return the session id telemetry should be keyed under when none is given."""
    return _ambient_session.get() or _PROCESS_SESSION_ID


def resolve_session_id(session_id: str | None) -> str:
    """Prefer an explicit session id; fall back to the ambient live session."""
    return session_id or ambient_session_id()
