"""Tiny SQLite layer: sessions, token usage, traces and scored attempts."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, created REAL, display_name TEXT
);
CREATE TABLE IF NOT EXISTS usage (
  session_id TEXT, ts REAL, day TEXT, label TEXT, model TEXT,
  input_tokens INTEGER, output_tokens INTEGER
);
CREATE TABLE IF NOT EXISTS spans (
  id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT, session_id TEXT, ts REAL,
  kind TEXT, name TEXT, input TEXT, output TEXT, latency_ms REAL,
  input_tokens INTEGER, output_tokens INTEGER, error TEXT
);
CREATE INDEX IF NOT EXISTS spans_trace ON spans(trace_id);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, ts REAL, module TEXT,
  config TEXT, result TEXT, score REAL
);
"""

_lock = threading.Lock()  # serialises writes
_local = threading.local()  # one connection per thread; sqlite connections aren't thread-safe
_initialised: set[str] = set()


def conn() -> sqlite3.Connection:
    path = get_settings().db_path
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != path:
        c = sqlite3.connect(path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        with _lock:
            if path not in _initialised:
                c.executescript(SCHEMA)
                _initialised.add(path)
        _local.conn, _local.path = c, path
    return c


@contextmanager
def tx():
    c = conn()
    with _lock:
        yield c
        c.commit()


def record_usage(session_id: str, label: str, model: str, inp: int, out: int) -> None:
    with tx() as c:
        c.execute(
            "INSERT INTO usage VALUES (?,?,?,?,?,?,?)",
            (session_id, time.time(), time.strftime("%Y-%m-%d"), label, model, inp, out),
        )


def session_tokens(session_id: str) -> int:
    row = conn().execute(
        "SELECT COALESCE(SUM(input_tokens+output_tokens),0) t FROM usage WHERE session_id=?",
        (session_id,),
    ).fetchone()
    return int(row["t"])


def day_tokens() -> int:
    row = conn().execute(
        "SELECT COALESCE(SUM(input_tokens+output_tokens),0) t FROM usage WHERE day=?",
        (time.strftime("%Y-%m-%d"),),
    ).fetchone()
    return int(row["t"])


def save_attempt(session_id: str, module: str, config: dict, result: dict, score: float) -> int:
    with tx() as c:
        cur = c.execute(
            "INSERT INTO attempts(session_id, ts, module, config, result, score) VALUES (?,?,?,?,?,?)",
            (session_id, time.time(), module, json.dumps(config), json.dumps(result), score),
        )
        return int(cur.lastrowid)


def list_attempts(session_id: str, module: str | None = None) -> list[dict]:
    q = "SELECT id, ts, module, score, config, result FROM attempts WHERE session_id=?"
    args: list = [session_id]
    if module:
        q += " AND module=?"
        args.append(module)
    q += " ORDER BY id DESC LIMIT 50"
    out = []
    for r in conn().execute(q, args).fetchall():
        d = dict(r)
        d["config"] = json.loads(d["config"])
        d["result"] = json.loads(d["result"])
        out.append(d)
    return out
