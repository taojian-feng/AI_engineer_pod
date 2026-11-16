"""Minimal tracing: every LLM call, tool call, retrieval and graph node becomes a
span stored in SQLite, so applicants can inspect what the system actually did.

This is deliberately a small home-grown version of what LangSmith / MLflow /
Arize give you, so the data model is visible and discussable in an interview.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from . import db

current_trace: ContextVar[str | None] = ContextVar("current_trace", default=None)
current_session: ContextVar[str] = ContextVar("current_session", default="anonymous")


def new_trace() -> str:
    tid = uuid.uuid4().hex[:16]
    current_trace.set(tid)
    return tid


def _short(v, limit: int = 4000) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= limit else s[:limit] + "…[truncated]"


def log_span(kind: str, name: str, input=None, output=None, latency_ms: float = 0.0,
             input_tokens: int = 0, output_tokens: int = 0, error: str | None = None) -> None:
    with db.tx() as c:
        c.execute(
            "INSERT INTO spans(trace_id, session_id, ts, kind, name, input, output, latency_ms,"
            " input_tokens, output_tokens, error) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (current_trace.get() or "untraced", current_session.get(), time.time(), kind, name,
             _short(input), _short(output), latency_ms, input_tokens, output_tokens, error),
        )


@contextmanager
def span(kind: str, name: str, input=None):
    """Context manager; set `holder["output"]` inside the block to record output."""
    holder: dict = {}
    t0 = time.perf_counter()
    err = None
    try:
        yield holder
    except Exception as e:  # recorded then re-raised
        err = f"{type(e).__name__}: {e}"
        raise
    finally:
        log_span(kind, name, input, holder.get("output"), (time.perf_counter() - t0) * 1000,
                 holder.get("input_tokens", 0), holder.get("output_tokens", 0), err)


def get_trace(trace_id: str) -> list[dict]:
    rows = db.conn().execute(
        "SELECT * FROM spans WHERE trace_id=? ORDER BY id", (trace_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def recent_traces(session_id: str, limit: int = 30) -> list[dict]:
    rows = db.conn().execute(
        "SELECT trace_id, MIN(ts) ts, COUNT(*) spans, SUM(input_tokens+output_tokens) tokens,"
        " SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) errors,"
        " GROUP_CONCAT(DISTINCT kind) kinds"
        " FROM spans WHERE session_id=? GROUP BY trace_id ORDER BY ts DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
