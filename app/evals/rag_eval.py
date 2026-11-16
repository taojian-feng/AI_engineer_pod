"""RAG evaluation: retrieval hit rate, answer correctness, groundedness,
hallucination rate, abstention, citations, latency and cost.

Deterministic checks are used where possible (cheap, reproducible); an
LLM-as-judge is used only for groundedness/abstention, with a strict rubric and
structured output.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path

from pydantic import BaseModel, Field

from .. import llm, tracing
from ..rag.pipeline import RagConfig, answer

DATASET = json.loads((Path(__file__).parent / "rag_dataset.json").read_text())

JUDGE_SYSTEM = """You are a strict evaluator for a retrieval-augmented QA system.
You get the retrieved CONTEXT, a QUESTION and the system's ANSWER.
- grounded: true only if every factual claim in the ANSWER is directly supported by the CONTEXT.
  An answer that only says the information is not available counts as grounded.
- abstained: true if the ANSWER declines to answer or says the information is not in the provided documents.
- unsupported_claims: list the specific claims that are not supported by the CONTEXT (empty if none).
Judge only against the CONTEXT, never your own knowledge."""


class Judgement(BaseModel):
    grounded: bool
    abstained: bool
    unsupported_claims: list[str] = Field(default_factory=list)


ABSTAIN_RE = re.compile(
    r"(don't know|do not know|not (?:covered|mentioned|specified|included|addressed|in the)|no information|"
    r"(?:cannot|can't|couldn't|unable to) find|(?:do not|don't|does not|doesn't) (?:say|specify|mention|contain|"
    r"include|address|cover))", re.I)


def _norm(s: str) -> str:
    return s.lower().replace(",", "")


def _correct(ans: str, groups: list[list[str]]) -> bool:
    a = _norm(ans)
    return all(any(_norm(opt) in a for opt in g) for g in groups)


def judge(question: str, contexts: list[dict], ans: str) -> Judgement:
    ctx = "\n\n".join(c["text"] for c in contexts) or "(no context retrieved)"
    msg = f"CONTEXT:\n{ctx}\n\nQUESTION: {question}\n\nANSWER: {ans}"
    try:
        return llm.parse(JUDGE_SYSTEM, [{"role": "user", "content": msg}], Judgement, max_tokens=1500,
                         label="eval.judge")
    except llm.BudgetExceeded:
        raise
    except Exception:
        return Judgement(grounded=False, abstained=bool(ABSTAIN_RE.search(ans)), unsupported_claims=["judge error"])


def eval_case(case: dict, cfg: RagConfig, use_judge: bool) -> dict:
    with tracing.span("eval", f"rag_case.{case['id']}", {"question": case["question"]}) as sp:
        r = answer(case["question"], cfg)
        retrieved = {c["source"] for c in r["contexts"]}
        hit = bool(set(case["sources"]) & retrieved) if case["answerable"] else None
        abstained_rx = bool(ABSTAIN_RE.search(r["answer"]))
        j = judge(case["question"], r["contexts"], r["answer"]) if use_judge else None
        abstained = j.abstained if j else abstained_rx
        if case["answerable"]:
            correct = _correct(r["answer"], case["must_include"]) and not abstained
        else:
            correct = abstained
        grounded = j.grounded if j else None
        # Hallucination = an ungrounded answer, or confidently answering an unanswerable question.
        hallucinated = (not case["answerable"] and not abstained) or (grounded is False and not abstained)
        out = {
            "id": case["id"], "question": case["question"], "answerable": case["answerable"],
            "answer": r["answer"], "retrieved": [c["id"] for c in r["contexts"]], "retrieval_hit": hit,
            "correct": correct, "grounded": grounded, "abstained": abstained, "hallucinated": hallucinated,
            "cited": bool(re.search(r"\[\d+\]", r["answer"])),
            "unsupported_claims": j.unsupported_claims if j else [],
            "latency_ms": r["latency_ms"], "tokens": r["tokens"],
        }
        sp["output"] = {k: out[k] for k in ("correct", "grounded", "hallucinated", "retrieval_hit")}
    return out


def run(cfg: RagConfig, use_judge: bool = True, case_ids: list[str] | None = None) -> dict:
    cases = [c for c in DATASET if not case_ids or c["id"] in case_ids]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(copy_context().run, eval_case, c, cfg, use_judge) for c in cases]
        rows = [f.result() for f in futures]
    n = len(rows)
    ans = [r for r in rows if r["answerable"]]
    unans = [r for r in rows if not r["answerable"]]

    def rate(xs, key):
        vals = [x[key] for x in xs if x[key] is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None

    lat = sorted(r["latency_ms"] for r in rows)
    metrics = {
        "accuracy": rate(rows, "correct"),
        "retrieval_hit_rate": rate(ans, "retrieval_hit"),
        "groundedness": rate(rows, "grounded"),
        "hallucination_rate": rate(rows, "hallucinated"),
        "abstention_on_unanswerable": rate(unans, "abstained"),
        "citation_rate": rate(ans, "cited"),
        "p50_latency_ms": lat[n // 2] if n else None,
        "p95_latency_ms": lat[min(n - 1, int(n * 0.95))] if n else None,
        "total_tokens": sum(r["tokens"] for r in rows),
        "cases": n,
    }
    # Single headline score the leaderboard uses.
    score = round(100 * (0.5 * (metrics["accuracy"] or 0) + 0.3 * (1 - (metrics["hallucination_rate"] or 0))
                         + 0.2 * (metrics["retrieval_hit_rate"] or 0)), 1)
    return {"score": score, "metrics": metrics, "rows": rows}
