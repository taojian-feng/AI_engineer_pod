"""One place where the app talks to Claude.

Every call goes through here so that we get, for free:
  * per-session and per-day token budgets (protects the owner's API key),
  * a trace span with latency and token counts,
  * a single switch between the real Anthropic API and an offline fake.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from . import db, tracing
from .config import FALLBACK_MODELS, get_settings

T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    pass


class ModelRefused(RuntimeError):
    pass


class LLMError(RuntimeError):
    """Claude could not be reached or returned nothing usable. The message is shown to the user."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _explain(e: Exception) -> LLMError:
    """Turn an Anthropic SDK exception into a message that says what to fix."""
    import anthropic

    model = get_settings().model
    detail = getattr(e, "message", None) or str(e)
    if isinstance(e, anthropic.AuthenticationError):
        return LLMError("Claude API rejected the API key (401). Check the ANTHROPIC_API_KEY secret on the server.")
    if isinstance(e, anthropic.PermissionDeniedError):
        return LLMError(f"The API key is not allowed to use model '{model}' (403): {detail}")
    if isinstance(e, anthropic.NotFoundError):
        return LLMError(f"Model '{model}' was not found (404). Check the MODEL setting on the server.")
    if isinstance(e, anthropic.RateLimitError):
        return LLMError("Claude API rate limit reached (429). Wait a minute and try again.", 429)
    if isinstance(e, anthropic.BadRequestError):
        return LLMError(f"Claude API rejected the request (400): {detail}")
    if isinstance(e, anthropic.APITimeoutError):
        return LLMError("Claude API timed out. Try again.", 504)
    if isinstance(e, anthropic.APIConnectionError):
        return LLMError("Could not connect to the Claude API from the server (network error).")
    if isinstance(e, anthropic.APIStatusError):
        return LLMError(f"Claude API error ({e.status_code}): {detail}")
    return LLMError(f"Claude call failed: {type(e).__name__}: {detail}")


@dataclass
class Reply:
    content: list[dict]  # assistant content blocks, safe to append back to messages
    text: str
    tool_uses: list[dict] = field(default_factory=list)  # [{id, name, input}]
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------- budget

def _check_budget() -> None:
    s = get_settings()
    sid = tracing.current_session.get()
    if db.session_tokens(sid) >= s.session_token_budget:
        raise BudgetExceeded(
            "This practice session has used its token budget. Start a new session or ask the admin to raise SESSION_TOKEN_BUDGET."
        )
    if db.day_tokens() >= s.daily_token_budget:
        raise BudgetExceeded("The site has reached today's token budget. Please try again tomorrow.")


def _account(label: str, model: str, inp: int, out: int) -> None:
    db.record_usage(tracing.current_session.get(), label, model, inp, out)


# ---------------------------------------------------------------- real provider

_client = None


def _anthropic():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(max_retries=3, timeout=120.0)
    return _client


def _base_kwargs(system: str, messages: list, max_tokens: int) -> dict:
    s = get_settings()
    kw: dict[str, Any] = {
        "model": s.model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if s.effort:
        kw["output_config"] = {"effort": s.effort}
    return kw


def _real_chat(system: str, messages: list, tools: list | None, max_tokens: int) -> Reply:
    s = get_settings()
    kw = _base_kwargs(system, messages, max_tokens)
    if tools:
        kw["tools"] = tools
    client = _anthropic()
    if s.fallbacks and s.fallbacks != "off" and s.model in FALLBACK_MODELS:
        resp = client.beta.messages.create(
            **kw, betas=["server-side-fallback-2026-07-01"], fallbacks=s.fallbacks
        )
    else:
        resp = client.messages.create(**kw)
    if resp.stop_reason == "refusal":
        raise ModelRefused("The model declined this request.")
    content = [b.model_dump(exclude_none=True) for b in resp.content if b.type != "fallback"]
    text = "".join(b.text for b in resp.content if b.type == "text")
    tool_uses = [
        {"id": b.id, "name": b.name, "input": b.input} for b in resp.content if b.type == "tool_use"
    ]
    return Reply(content, text, tool_uses, resp.stop_reason or "end_turn",
                 resp.usage.input_tokens, resp.usage.output_tokens)


def _real_parse(system: str, messages: list, schema: type[T], max_tokens: int) -> tuple[T, int, int]:
    kw = _base_kwargs(system, messages, max_tokens)
    resp = _anthropic().messages.parse(**kw, output_format=schema)
    if resp.stop_reason == "refusal":
        raise ModelRefused("The model declined this request.")
    return resp.parsed_output, resp.usage.input_tokens, resp.usage.output_tokens


# ---------------------------------------------------------------- fake provider
# Used for tests and for an offline demo without an API key. Tests can push
# scripted replies with `fake_script`.

_fake_queue: list[Reply | Callable[[str, list, list | None], Reply]] = []
_fake_parse_queue: list[BaseModel] = []


def fake_script(*replies: Reply | Callable) -> None:
    _fake_queue.extend(replies)


def fake_parse_script(*objs: BaseModel) -> None:
    _fake_parse_queue.extend(objs)


def fake_reset() -> None:
    _fake_queue.clear()
    _fake_parse_queue.clear()


def text_reply(text: str) -> Reply:
    return Reply([{"type": "text", "text": text}], text)


def tool_reply(name: str, input: dict, id: str | None = None, text: str = "") -> Reply:
    tid = id or f"toolu_fake_{int(time.time()*1e6) % 10**9}"
    content = ([{"type": "text", "text": text}] if text else []) + [
        {"type": "tool_use", "id": tid, "name": name, "input": input}
    ]
    return Reply(content, text, [{"id": tid, "name": name, "input": input}], "tool_use")


def _fake_chat(system: str, messages: list, tools: list | None, max_tokens: int) -> Reply:
    if _fake_queue:
        r = _fake_queue.pop(0)
        return r(system, messages, tools) if callable(r) else r
    last = messages[-1]["content"] if messages else ""
    if isinstance(last, list):
        last = " ".join(str(b.get("content", b.get("text", ""))) for b in last)
    if "<context>" in str(last):
        # Offline RAG: echo the first retrieved passage with a citation.
        body = str(last).split("<context>", 1)[1]
        first = body.split("</doc>", 1)[0].split(">", 1)[-1].strip().split("\n")[0]
        return text_reply(f"(offline demo mode) {first[:300]} [1]")
    return text_reply(
        "(offline demo mode: set ANTHROPIC_API_KEY to talk to Claude) "
        "Tell me about a GenAI system you took from prototype to production."
    )


def _fake_instance(schema: type[BaseModel]):
    if _fake_parse_queue:
        return _fake_parse_queue.pop(0)
    vals = {}
    for name, f in schema.model_fields.items():
        ann = f.annotation
        if f.default is not None and f.default.__class__.__name__ != "PydanticUndefinedType":
            continue
        if ann in (int, float):
            vals[name] = 3
        elif ann is bool:
            vals[name] = False
        elif ann is str:
            vals[name] = "(offline demo mode)"
        elif getattr(ann, "__origin__", None) is list:
            vals[name] = []
        else:
            vals[name] = None
    return schema.model_validate(vals)


# ---------------------------------------------------------------- public API

def _call(fn, *args):
    import anthropic

    try:
        return fn(*args)
    except anthropic.AnthropicError as e:
        raise _explain(e) from e


def chat(system: str, messages: list, tools: list | None = None, max_tokens: int = 4096,
         label: str = "chat", require_text: bool = False) -> Reply:
    s = get_settings()
    _check_budget()
    with tracing.span("llm", label, {"system": system[:1500], "last_message": messages[-1] if messages else None,
                                     "tools": [t["name"] for t in tools or []]}) as sp:
        if s.provider == "anthropic":
            r = _call(_real_chat, system, messages, tools, max_tokens)
        else:
            r = _fake_chat(system, messages, tools, max_tokens)
        sp["output"] = {"text": r.text, "tool_uses": r.tool_uses, "stop_reason": r.stop_reason}
        sp["input_tokens"], sp["output_tokens"] = r.input_tokens, r.output_tokens
    _account(label, s.model, r.input_tokens, r.output_tokens)
    if require_text and not r.text.strip():
        # Thinking can use up max_tokens before any visible text is written.
        raise LLMError(f"Claude returned an empty reply (stop_reason={r.stop_reason}). Try again.")
    return r


def parse(system: str, messages: list, schema: type[T], max_tokens: int = 4096,
          label: str = "parse") -> T:
    s = get_settings()
    _check_budget()
    with tracing.span("llm", label, {"system": system[:1500], "schema": schema.__name__}) as sp:
        if s.provider == "anthropic":
            obj, i, o = _call(_real_parse, system, messages, schema, max_tokens)
        else:
            obj, i, o = _fake_instance(schema), 0, 0
        sp["output"] = obj.model_dump()
        sp["input_tokens"], sp["output_tokens"] = i, o
    _account(label, s.model, i, o)
    return obj
