# Architecture

```
Browser (vanilla JS SPA)
   │  HTTPS, session cookie (access-code login)
   ▼
FastAPI app  (Azure Container Apps, scale-to-zero)
   ├── llm.py ──────────────► Claude API (Anthropic SDK)
   │      budget checks · token accounting · trace spans · fake provider for tests
   ├── rag/      BM25 index over policy docs → grounded prompt with citations
   ├── agent/    LangGraph state machine: agent ⇄ tools → halt; tools act on a per-run World
   ├── evals/    RAG eval (deterministic checks + LLM judge) · agent scenario eval (end-state checks)
   ├── interview/ interviewer · stakeholder role-play · code-review grader (structured outputs)
   ├── coding/   exercise harness ──────► Azure Container Apps dynamic sessions (PythonLTS,
   │                                       Hyper-V isolated, egress disabled, managed identity auth)
   └── tracing.py + db.py   SQLite: sessions, usage, spans, attempts
```

## Key decisions (and the trade-offs worth discussing)

**One gateway for every model call (`llm.py`).** Budgets, token accounting,
tracing and the offline fake all live in one place. This is the usual
"LLM gateway" pattern; in a larger org it would be a shared service (APIM,
LiteLLM or a platform team's proxy).

**BM25 instead of a vector database.** It keeps the app dependency-free and
free to host, and makes retrieval behaviour easy to reason about. Everything
downstream depends only on `retrieve()`, so swapping in Azure AI Search
(hybrid plus semantic ranker) or pgvector is a contained change. That swap is
a good stretch exercise and interview topic.

**The baseline configs are deliberately bad.** The RAG baseline uses
400-word chunks, top-1 and a prompt with no grounding or abstention rules. It
hallucinates on unanswerable questions and misses multi-fact answers. The agent
baseline uses a two-line prompt, one-line tool descriptions and a step budget
of 4. The applicant's job is the real job: measure, diagnose, fix and re-measure.

**Agent evals check the system of record, not the prose.** Each scenario runs
against a fresh copy of the ERP (`World`). Checks look at which POs exist,
their quantities and suppliers, the trajectory (step limit) and the final text
(fabricated PO numbers, approval disclosure). Tool *implementations* enforce
only what a real ERP would, such as blocked suppliers and approval statuses.
Policy judgement (probation, duplicates, injection) is the agent's
responsibility, which is the point of the lab.

**Prompt injection is in the data, not the user message.** One supplier
record's free-text notes contain instructions to the AI. This mirrors the most
common real-world agent attack path: untrusted tool output.

**Mixed evaluation strategy.** Deterministic checks (keyword facts, retrieval
hit, abstention regex, ERP state) are used wherever possible because they are
cheap and reproducible. An LLM judge with structured output is used only for
groundedness, where string checks can't work. Judge errors count as failures
instead of being silently skipped.

**Memory.** Chat mode keeps recent turns verbatim and, past `memory_turns`,
folds them into a running summary that seeds a fresh conversation. It never
edits earlier messages in place, which keeps the history append-only.

**Untrusted code never runs in the web process.** Coding-lab submissions are
wrapped in a harness (base64-embedded source, per-run random result marker) and
executed in Azure dynamic sessions with a fresh session identifier per run.
The web app authenticates with its managed identity, so no sandbox credential
is stored anywhere. The local subprocess backend exists only for development.

**Cost controls by default.** Claude Opus 5.5 runs at low effort, with
per-session and per-day token budgets. Container Apps scales to zero, there is
no Log Analytics workspace, and images live in GitHub Container Registry
instead of ACR.

## Extending

* Add RAG cases in `app/evals/rag_dataset.json` and agent scenarios in `app/evals/agent_eval.py`.
* Add interview tracks, personas and review snippets in `app/interview/tracks.py`.
* Add coding exercises in `app/coding/exercises.py`, with a reference solution in `tests/solutions.py`.
  The test suite checks that every reference solution passes and every starter fails.
