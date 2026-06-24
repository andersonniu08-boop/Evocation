"""Structured JSON telemetry logger for Evocation internals.

Writes line-delimited JSON to evocation.log in workspace root.
Each line = one JSON event. No streaming to user-facing UI or CLI.
"""

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_log_lock = threading.Lock()
_log_path: Path | None = None


def init_logger(workspace_root: str | Path = ".") -> Path:
    """Set the log file path. Called once at startup."""
    global _log_path
    root = Path(workspace_root).resolve()
    _log_path = root / "evocation.log"
    return _log_path


def _write_event(event: dict):
    """Thread-safe write of a single JSON event to the log file."""
    global _log_path
    if _log_path is None:
        _log_path = Path("evocation.log")

    event["timestamp"] = datetime.now(UTC).isoformat()

    with _log_lock:
        try:
            with open(_log_path, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass  # Logging must never crash the agent


def log_state_transition(component: str, from_state: str, to_state: str, metadata: dict[str, Any] | None = None):
    """Log a state machine transition."""
    _write_event({
        "component": component,
        "event": "state_transition",
        "from": from_state,
        "to": to_state,
        "metadata": metadata or {},
    })


def log_tool_call(component: str, tool_name: str, params: dict, approved: bool | None = None, result_summary: str | None = None, metadata: dict[str, Any] | None = None):
    """Log a tool execution (input, approval status, output summary)."""
    event: dict[str, Any] = {
        "component": component,
        "event": "tool_call",
        "tool": tool_name,
        "params_summary": _truncate_params(params),
    }
    if approved is not None:
        event["approved"] = approved
    if result_summary:
        event["result"] = result_summary[:300]
    if metadata:
        event["metadata"] = metadata
    _write_event(event)


def log_llm_request(component: str, model: str, token_count: int, latency_ms: float | None = None, purpose: str = "", metadata: dict[str, Any] | None = None):
    """Log an LLM API call with token usage and latency."""
    event: dict[str, Any] = {
        "component": component,
        "event": "llm_request",
        "model": model,
        "tokens": token_count,
    }
    if latency_ms is not None:
        event["latency_ms"] = round(latency_ms, 1)
    if purpose:
        event["purpose"] = purpose
    if metadata:
        event["metadata"] = metadata
    _write_event(event)


def log_retrieval(component: str, query: str, result_count: int, top_scores: list[float] | None = None, metadata: dict[str, Any] | None = None):
    """Log a memory retrieval query and its results."""
    event: dict[str, Any] = {
        "component": component,
        "event": "retrieval",
        "query": query[:200],
        "results": result_count,
    }
    if top_scores:
        event["top_scores"] = [round(s, 4) for s in top_scores[:5]]
    if metadata:
        event["metadata"] = metadata
    _write_event(event)


def log_error(component: str, error: str, context: dict[str, Any] | None = None):
    """Log an error or exception."""
    _write_event({
        "component": component,
        "event": "error",
        "error": error[:500],
        "context": context or {},
    })


def log_info(component: str, message: str, metadata: dict[str, Any] | None = None):
    """Log a general informational event."""
    _write_event({
        "component": component,
        "event": "info",
        "message": message[:500],
        "metadata": metadata or {},
    })


def _truncate_params(params: dict, max_len: int = 200) -> dict:
    """Truncate large parameter values for logging."""
    result = {}
    for k, v in params.items():
        s = str(v)
        if len(s) > max_len:
            result[k] = s[:max_len] + "..."
        else:
            result[k] = v
    return result


def get_log_path() -> Path:
    """Return the current log file path."""
    global _log_path
    return _log_path or Path("evocation.log")
