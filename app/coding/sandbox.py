"""Run untrusted applicant code somewhere that is NOT this web process.

Backends (env SANDBOX):
  azure - Azure Container Apps dynamic sessions (Hyper-V isolated, egress disabled).
          Production setting. The web app authenticates with its managed identity;
          the sandbox never sees ANTHROPIC_API_KEY or anything else from this app.
  local - a resource-limited subprocess on this machine. DEVELOPMENT ONLY: the child
          runs as the same OS user and could read this process's environment via /proc.
  off   - coding labs disabled.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    ok: bool
    backend: str
    duration_ms: int


class SandboxUnavailable(RuntimeError):
    pass


def backend() -> str:
    return os.getenv("SANDBOX", "off").lower()


def execute(code: str, timeout_s: int = 20) -> ExecResult:
    b = backend()
    if b == "azure":
        return _azure(code, timeout_s)
    if b == "local":
        return _local(code, timeout_s)
    raise SandboxUnavailable(
        "Code execution is turned off. Set SANDBOX=azure (production) or SANDBOX=local (dev only)."
    )


# ---------------------------------------------------------------- local (dev)

def _limits():  # runs in the child before exec
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    os.setsid()


def _local(code: str, timeout_s: int) -> ExecResult:
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="podsim-") as d:
        path = os.path.join(d, "main.py")
        with open(path, "w") as f:
            f.write(code)
        try:
            p = subprocess.run(
                [sys.executable, "-I", path], cwd=d, capture_output=True, text=True, timeout=timeout_s,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"}, preexec_fn=_limits,
            )
            out, err, ok = p.stdout, p.stderr, p.returncode == 0
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err, ok = f"Timed out after {timeout_s}s", False
    return ExecResult(out[-20000:], err[-20000:], ok, "local", round((time.perf_counter() - t0) * 1000))


# ---------------------------------------------------------------- Azure dynamic sessions

_token_cache: dict = {}


def _azure_token() -> str:
    tok = _token_cache.get("t")
    if tok and tok.expires_on - 120 > time.time():
        return tok.token
    from azure.identity import DefaultAzureCredential

    tok = DefaultAzureCredential().get_token("https://dynamicsessions.io/.default")
    _token_cache["t"] = tok
    return tok.token


def _azure(code: str, timeout_s: int) -> ExecResult:
    import httpx

    endpoint = os.getenv("AZURE_SESSION_POOL_ENDPOINT", "").rstrip("/")
    if not endpoint:
        raise SandboxUnavailable("AZURE_SESSION_POOL_ENDPOINT is not set.")
    api_version = os.getenv("AZURE_SESSIONS_API_VERSION", "2024-02-02-preview")
    # A fresh identifier per run = a fresh sandbox, so runs can't leak state into each other.
    identifier = f"run-{uuid.uuid4().hex}"
    t0 = time.perf_counter()
    r = httpx.post(
        f"{endpoint}/code/execute",
        params={"api-version": api_version, "identifier": identifier},
        headers={"Authorization": f"Bearer {_azure_token()}"},
        json={"properties": {"codeInputType": "inline", "executionType": "synchronous", "code": code,
                             "timeoutInSeconds": timeout_s}},
        timeout=timeout_s + 60,
    )
    r.raise_for_status()
    data = r.json()
    props = data.get("properties", data)
    if isinstance(props.get("result"), dict) and "stdout" in props["result"]:
        props = props["result"]
    stdout, stderr = props.get("stdout") or "", props.get("stderr") or ""
    status = str(props.get("status", "Success"))
    return ExecResult(stdout, stderr, status.lower() in ("success", "succeeded"), "azure",
                      round((time.perf_counter() - t0) * 1000))
