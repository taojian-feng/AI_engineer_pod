"""Chunking + a dependency-free BM25 index over the company policy docs.

BM25 keeps the app tiny and free to host. Swapping in embeddings / a vector DB
(Azure AI Search, pgvector, ...) is a good talking point and a stretch exercise:
everything downstream only depends on `search()` returning scored chunks.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs"
STOP = set("a an the of to and or in on for is are be by with at as it this that from any all may must not no".split())


@dataclass
class Chunk:
    id: str
    source: str
    title: str
    text: str


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9$%.]+", text.lower().replace(",", "")) if t not in STOP]


def load_docs() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(DOCS_DIR.glob("*.md"))}


def chunk_doc(name: str, text: str, chunk_size: int, overlap: int, split_on_headings: bool) -> list[Chunk]:
    title = text.splitlines()[0].lstrip("# ").strip()
    sections: list[tuple[str, str]]
    if split_on_headings:
        parts = re.split(r"\n(?=## )", text)
        sections = []
        for p in parts:
            head = p.splitlines()[0].lstrip("# ").strip()
            sections.append((head, p))
    else:
        sections = [("", text)]
    chunks: list[Chunk] = []
    step = max(1, chunk_size - overlap)
    for head, body in sections:
        words = body.split()
        for i in range(0, max(1, len(words)), step):
            piece = " ".join(words[i:i + chunk_size])
            if not piece:
                continue
            prefix = f"[{title}{' > ' + head if head and head != title else ''}] "
            chunks.append(Chunk(f"{name}#{len(chunks)}", name, title, prefix + piece))
            if i + chunk_size >= len(words):
                break
    return chunks


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.toks = [tokenize(c.text) for c in chunks]
        self.tf = [Counter(t) for t in self.toks]
        self.avgdl = sum(len(t) for t in self.toks) / max(1, len(self.toks))
        df: Counter = Counter()
        for t in self.toks:
            df.update(set(t))
        n = len(chunks)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.toks[i])
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append((s, i))
        scores.sort(reverse=True)
        return [(self.chunks[i], round(s, 3)) for s, i in scores[:k] if s > 0]


@lru_cache(maxsize=32)
def build_index(chunk_size: int, overlap: int, split_on_headings: bool) -> BM25Index:
    chunks: list[Chunk] = []
    for name, text in load_docs().items():
        chunks.extend(chunk_doc(name, text, chunk_size, overlap, split_on_headings))
    return BM25Index(chunks)
