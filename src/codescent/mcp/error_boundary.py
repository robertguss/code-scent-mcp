"""One uniform error boundary for every MCP tool.

FastMCP invokes ``on_call_tool`` around every tool call at the single wiring
point, so this middleware is the one choke point that turns a raised exception
into the uniform ``{ok:false, code, message, recoverable, data}`` payload
instead of an out-of-band tool-error string (F1).

Only ``CodeScentError`` and ``ResultStoreError`` are treated as structured,
recoverable domain errors; every other exception (bare ``LookupError`` /
``ValueError`` / ``KeyError`` and any real bug) is logged and mapped to
``code:internal, recoverable:false`` so an internal fault is never mislabelled
as "fix your input" (KTD2).

The payload is delivered with ``is_error=True``. That is required, not
incidental: 45/48 tools declare a strict output schema, and both the MCP server
and client validate structured content against it unless the result is flagged
as an error. ``is_error=True`` is also the honest protocol-level signal that the
call failed, while the structured, branchable ``{ok:false, ...}`` content still
reaches the model (it is not an opaque error string).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, override

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from mcp.types import TextContent

from codescent.core.errors import CodeScentError
from codescent.services.result_store import ResultStoreError

if TYPE_CHECKING:
    import mcp.types as mt

logger = logging.getLogger("codescent.mcp.error_boundary")

# FastMCP re-raises tool exceptions as ``ToolError(...) from original`` at its
# single wiring point, so the domain error we care about is reached through the
# ``__cause__`` chain. The bound guards against a pathological cycle.
_MAX_CAUSE_DEPTH = 8
_INTERNAL_CODE = "internal"


class ToolErrorBoundary(Middleware):
    """Catch every tool exception and return the uniform error payload."""

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except Exception as exc:
            domain = _find_domain_error(exc)
            if domain is not None:
                payload = dict(domain.to_payload())
            else:
                logger.exception("Unhandled error in tool %r", _tool_name(context))
                payload = _internal_payload()
            return _error_result(payload)


def _find_domain_error(
    exc: BaseException,
) -> CodeScentError | ResultStoreError | None:
    seen: set[int] = set()
    current: BaseException | None = exc
    depth = 0
    while current is not None and depth < _MAX_CAUSE_DEPTH:
        if id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, (CodeScentError, ResultStoreError)):
            return current
        current = current.__cause__
        depth += 1
    return None


def _internal_payload() -> dict[str, object]:
    return {
        "ok": False,
        "code": _INTERNAL_CODE,
        "message": "An internal error occurred while handling the tool call.",
        "recoverable": False,
        "data": {},
    }


def _error_result(payload: dict[str, object]) -> ToolResult:
    text = json.dumps(payload, sort_keys=True, default=str)
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=payload,
        is_error=True,
    )


def _tool_name(context: MiddlewareContext[mt.CallToolRequestParams]) -> str:
    return context.message.name
