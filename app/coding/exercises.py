"""Hands-on Python exercises graded by hidden tests run in the sandbox.

Each exercise maps to a JD responsibility. Tests are plain functions named
test_*; they reference the applicant's functions by name.
"""
from __future__ import annotations

EXERCISES = [
    {
        "id": "chunking",
        "title": "Chunk documents for RAG ingestion",
        "skill": "RAG: data ingestion",
        "minutes": 15,
        "prompt": """Implement `chunk_text(text, chunk_size, overlap)` for the policy-document ingestion pipeline.

* Split on whitespace into words. Each chunk is a string of at most `chunk_size` words joined by single spaces.
* Consecutive chunks share exactly `overlap` words (the last `overlap` words of chunk *i* start chunk *i+1*).
* Every word appears in at least one chunk; no empty chunks; empty/blank text returns `[]`.
* Don't emit a final chunk that contains only words already covered by the previous chunk.
* Raise `ValueError` if `chunk_size < 1`, `overlap < 0` or `overlap >= chunk_size`.

Interview follow-up to think about: why chunk by tokens/sections instead of words, and how would you pick chunk size?""",
        "starter": '''def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    # TODO
    raise NotImplementedError
''',
        "tests": '''
def test_basic():
    assert chunk_text("a b c d e", 2, 0) == ["a b", "c d", "e"]

def test_overlap():
    assert chunk_text("a b c d e f", 3, 1) == ["a b c", "c d e", "e f"]

def test_no_redundant_tail():
    assert chunk_text("a b c d", 3, 2) == ["a b c", "b c d"]

def test_exact_fit():
    assert chunk_text("a b c d", 2, 0) == ["a b", "c d"]

def test_empty():
    assert chunk_text("   \\n ", 5, 1) == []

def test_whitespace_normalised():
    assert chunk_text("a\\n\\n b\\tc", 5, 0) == ["a b c"]

def test_invalid_args():
    for args in [(0, 0), (3, 3), (3, -1), (2, 5)]:
        try:
            chunk_text("a b c", *args)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for chunk_size, overlap = {args}")

def test_coverage_large():
    words = [f"w{i}" for i in range(1000)]
    chunks = chunk_text(" ".join(words), 64, 16)
    assert all(1 <= len(c.split()) <= 64 for c in chunks)
    seen = set(w for c in chunks for w in c.split())
    assert seen == set(words)
    for a, b in zip(chunks, chunks[1:]):
        assert a.split()[-16:] == b.split()[:16]
''',
    },
    {
        "id": "rrf",
        "title": "Hybrid search with reciprocal rank fusion",
        "skill": "RAG: retrieval",
        "minutes": 10,
        "prompt": """You have ranked results from a keyword (BM25) retriever and a vector retriever. Implement
`rrf(rankings, k=60)` returning a single fused list of document ids.

* `rankings` is a list of ranked lists of doc ids (best first). Ranks are 1-based.
* score(doc) = sum over lists containing doc of `1 / (k + rank)`.
* Return all unique doc ids sorted by score descending; break ties by doc id ascending.
* Duplicate ids within one list: only the first (best) occurrence counts.

Follow-up: when would hybrid search beat pure vector search on enterprise documents?""",
        "starter": '''def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    # TODO
    raise NotImplementedError
''',
        "tests": '''
def test_single_list_preserved():
    assert rrf([["a", "b", "c"]]) == ["a", "b", "c"]

def test_fusion():
    # a and c tie (1/61 + 1/63) and beat b (2/62); the tie is broken by id
    assert rrf([["a", "b", "c"], ["c", "b", "a"]]) == ["a", "c", "b"]
    assert rrf([["a", "b"], ["b", "c"]]) == ["b", "a", "c"]

def test_k_matters():
    r = [["x", "y"], ["y", "z"], ["z", "x"]]
    assert rrf(r, k=1)[0] in ("x", "y", "z")
    assert sorted(rrf(r, k=1)) == ["x", "y", "z"]

def test_duplicates_in_list():
    assert rrf([["a", "a", "b"], ["b"]]) == ["b", "a"]

def test_empty():
    assert rrf([]) == []
    assert rrf([[], []]) == []

def test_scores_exact():
    out = rrf([["d1", "d2", "d3"], ["d3", "d4"]], k=0)
    # d1: 1, d3: 1/3 + 1 = 1.333, d2: .5, d4: .5 -> tie broken by id
    assert out == ["d3", "d1", "d2", "d4"]
''',
    },
    {
        "id": "retrieval_metrics",
        "title": "Retrieval evaluation metrics",
        "skill": "Evaluation frameworks",
        "minutes": 15,
        "prompt": """Implement `retrieval_metrics(retrieved, relevant, k)` to evaluate a retriever over a set of queries.

* `retrieved[i]` is the ranked list of doc ids returned for query *i*; `relevant[i]` is the set of relevant ids.
* Skip queries whose `relevant` set is empty (they're unanswerable and evaluated separately).
* Return a dict with `recall_at_k`, `precision_at_k` and `mrr`, each the mean over non-skipped queries,
  rounded to 4 decimals. MRR uses the full ranked list (not just the top k); 0 if nothing relevant was found.
* precision@k divides by k even if fewer than k docs were retrieved.
* If no queries remain, return all three metrics as `0.0`.

Follow-up: how would you combine these with answer-level metrics like groundedness?""",
        "starter": '''def retrieval_metrics(retrieved: list[list[str]], relevant: list[set[str]], k: int) -> dict:
    # TODO
    raise NotImplementedError
''',
        "tests": '''
def test_perfect():
    m = retrieval_metrics([["a"], ["b"]], [{"a"}, {"b"}], 1)
    assert m == {"recall_at_k": 1.0, "precision_at_k": 1.0, "mrr": 1.0}

def test_mixed():
    m = retrieval_metrics([["x", "a", "b"], ["c", "y"]], [{"a", "b"}, {"z"}], 2)
    assert m["recall_at_k"] == 0.25
    assert m["precision_at_k"] == 0.25
    assert m["mrr"] == 0.25

def test_mrr_beyond_k():
    m = retrieval_metrics([["x", "y", "a"]], [{"a"}], 1)
    assert m["recall_at_k"] == 0.0 and m["mrr"] == round(1/3, 4)

def test_skip_unanswerable():
    m = retrieval_metrics([["a"], ["b"]], [{"a"}, set()], 1)
    assert m == {"recall_at_k": 1.0, "precision_at_k": 1.0, "mrr": 1.0}

def test_short_list_precision():
    m = retrieval_metrics([["a"]], [{"a"}], 3)
    assert m["precision_at_k"] == round(1/3, 4)

def test_no_queries():
    assert retrieval_metrics([], [], 5) == {"recall_at_k": 0.0, "precision_at_k": 0.0, "mrr": 0.0}
''',
    },
    {
        "id": "agent_loop",
        "title": "A reliable tool-calling agent loop",
        "skill": "Agents: tool calling, multi-step reasoning",
        "minutes": 25,
        "prompt": """Implement `run_agent(llm, tools, user_message, max_steps=5)`. No real model is involved: `llm` is a
callable you pass the message list to, and it returns one of:

```python
{"type": "tool_call", "id": "c1", "name": "get_item", "args": {"sku": "DB-8812"}}
{"type": "final", "text": "Done."}
```

Requirements:
* Start with `messages = [{"role": "user", "content": user_message}]`.
* Append every llm output as `{"role": "assistant", "content": <the dict returned>}`.
* For a tool call, run `tools[name](**args)` and append `{"role": "tool", "id": <call id>, "content": <result>}`.
* If the tool doesn't exist or raises, don't crash: append `{"role": "tool", "id": ..., "content": "Error: <message>", "is_error": True}`
  and let the model recover.
* Each tool call counts as one step. If the model asks for a tool call after `max_steps` calls have already run,
  stop without running it and return final text `"Stopped: step limit reached"`.
* Return `{"final": str, "steps": int, "messages": list}`.

Follow-up: what else would you add before letting this agent create real purchase orders?""",
        "starter": '''def run_agent(llm, tools: dict, user_message: str, max_steps: int = 5) -> dict:
    # TODO
    raise NotImplementedError
''',
        "tests": '''
def _scripted(outputs):
    calls = []
    def llm(messages):
        calls.append([dict(m) for m in messages])
        return outputs[len(calls) - 1]
    llm.calls = calls
    return llm

def test_direct_answer():
    llm = _scripted([{"type": "final", "text": "hi"}])
    r = run_agent(llm, {}, "hello")
    assert r["final"] == "hi" and r["steps"] == 0
    assert r["messages"][0] == {"role": "user", "content": "hello"}

def test_tool_then_answer():
    llm = _scripted([{"type": "tool_call", "id": "c1", "name": "add", "args": {"a": 2, "b": 3}},
                     {"type": "final", "text": "5"}])
    r = run_agent(llm, {"add": lambda a, b: a + b}, "2+3?")
    assert r["final"] == "5" and r["steps"] == 1
    assert {"role": "tool", "id": "c1", "content": 5} in r["messages"]
    # the model saw the tool result on its second call
    assert llm.calls[1][-1] == {"role": "tool", "id": "c1", "content": 5}

def test_tool_error_recovers():
    def boom(**kw):
        raise RuntimeError("db down")
    llm = _scripted([{"type": "tool_call", "id": "c1", "name": "boom", "args": {}},
                     {"type": "tool_call", "id": "c2", "name": "nope", "args": {}},
                     {"type": "final", "text": "sorry"}])
    r = run_agent(llm, {"boom": boom}, "x")
    errs = [m for m in r["messages"] if m.get("is_error")]
    assert len(errs) == 2 and all(m["content"].startswith("Error:") for m in errs)
    assert "db down" in errs[0]["content"]
    assert r["final"] == "sorry" and r["steps"] == 2

def test_step_limit():
    ran = []
    loop = [{"type": "tool_call", "id": f"c{i}", "name": "t", "args": {}} for i in range(50)]
    r = run_agent(_scripted(loop), {"t": lambda: ran.append(1) or "ok"}, "go", max_steps=3)
    assert r["final"] == "Stopped: step limit reached"
    assert r["steps"] == 3 and len(ran) == 3

def test_assistant_messages_recorded():
    out = [{"type": "tool_call", "id": "c1", "name": "t", "args": {}}, {"type": "final", "text": "ok"}]
    r = run_agent(_scripted(out), {"t": lambda: 1}, "go")
    roles = [m["role"] for m in r["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant"]
''',
    },
    {
        "id": "pii_guardrail",
        "title": "PII redaction guardrail",
        "skill": "Trust & reliability",
        "minutes": 15,
        "prompt": """Before HR tickets are sent to an LLM, PII must be masked. Implement `redact_pii(text)`:

* Email addresses -> `[EMAIL]`
* US phone numbers -> `[PHONE]`: `713-555-0182`, `(713) 555-0182`, `713.555.0182`, `+1 713 555 0182`, `7135550182`
* US SSNs `123-45-6789` -> `[SSN]`
* Do **not** touch business identifiers: PO numbers (`PO-2001`), SKUs (`DB-8812`, `SEAL-KIT-210`), dates (`2026-11-16`),
  dollar amounts, or policy ids (`POL-HR-003`).

Follow-up: where in an agent pipeline would you apply redaction, and what can regexes not catch?""",
        "starter": '''import re

def redact_pii(text: str) -> str:
    # TODO
    raise NotImplementedError
''',
        "tests": '''
def test_email():
    assert redact_pii("mail jane.doe+hr@meridian-energy.com now") == "mail [EMAIL] now"

def test_phones():
    for p in ["713-555-0182", "(713) 555-0182", "713.555.0182", "+1 713 555 0182", "7135550182"]:
        assert redact_pii(f"call {p}.") == "call [PHONE].", p

def test_ssn():
    assert redact_pii("SSN 123-45-6789") == "SSN [SSN]"

def test_business_ids_untouched():
    s = "PO-2001 for DB-8812 and SEAL-KIT-210 on 2026-11-16 costs $25,900 per POL-HR-003"
    assert redact_pii(s) == s

def test_mixed():
    s = "Priya (priya@x.io, 832-555-0100) re PO-2002"
    assert redact_pii(s) == "Priya ([EMAIL], [PHONE]) re PO-2002"
''',
    },
]

BY_ID = {e["id"]: e for e in EXERCISES}
