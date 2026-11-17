"""RAG pipeline: retrieve -> build grounded prompt -> generate with citations."""
from __future__ import annotations

import time

from pydantic import BaseModel, Field

from .. import llm, tracing
from .index import build_index


class RagConfig(BaseModel):
    """Everything the applicant can tune in the RAG lab."""
    chunk_size: int = Field(400, ge=20, le=2000, description="Words per chunk")
    chunk_overlap: int = Field(0, ge=0, le=500)
    split_on_headings: bool = False
    top_k: int = Field(1, ge=1, le=10)
    min_score: float = Field(0.0, ge=0, description="Drop retrieved chunks scoring below this")
    system_prompt: str = "You are a helpful assistant for Meridian employees. Answer the user's question."


# The "good" settings used when the agent calls search_policies.
AGENT_RAG = RagConfig(chunk_size=120, chunk_overlap=30, split_on_headings=True, top_k=3, min_score=1.0)


def retrieve(question: str, cfg: RagConfig) -> list[dict]:
    with tracing.span("retrieval", "bm25.search", {"query": question, "top_k": cfg.top_k,
                                                   "chunk_size": cfg.chunk_size}) as sp:
        idx = build_index(cfg.chunk_size, min(cfg.chunk_overlap, cfg.chunk_size - 1), cfg.split_on_headings)
        hits = [
            {"id": c.id, "source": c.source, "title": c.title, "text": c.text, "score": s}
            for c, s in idx.search(question, cfg.top_k) if s >= cfg.min_score
        ]
        sp["output"] = [{"id": h["id"], "score": h["score"]} for h in hits]
    return hits


def build_user_message(question: str, hits: list[dict]) -> str:
    docs = "\n".join(
        f'<doc id="{i}" source="{h["source"]}">{h["text"]}</doc>' for i, h in enumerate(hits, 1)
    )
    return f"<context>\n{docs}\n</context>\n\nQuestion: {question}"


def answer(question: str, cfg: RagConfig) -> dict:
    t0 = time.perf_counter()
    hits = retrieve(question, cfg)
    reply = llm.chat(cfg.system_prompt, [{"role": "user", "content": build_user_message(question, hits)}],
                     max_tokens=8000, label="rag.generate")
    return {
        "question": question,
        "answer": reply.text,
        "contexts": hits,
        "latency_ms": round((time.perf_counter() - t0) * 1000),
        "tokens": reply.input_tokens + reply.output_tokens,
    }


def retrieve_for_agent(query: str) -> list[dict]:
    return [{"source": h["source"], "text": h["text"]} for h in retrieve(query, AGENT_RAG)] or "No policy text matched."
