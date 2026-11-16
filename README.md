# Pod Simulator: AI Engineer interview practice in a live system

Pod Simulator is a working web app where AI Engineer applicants practise the
job's real tasks inside a simulated enterprise. It is built around a typical
enterprise "AI pod" job description: agentic workflows for Supply Chain,
Finance and HR, RAG, evaluation frameworks, observability, and explaining how
trust was established.

Applicants join the AI pod at **Meridian Basin Energy Services**, a fictional
oilfield services company with policy documents, an ERP-like system of record,
suppliers and purchase orders. Every lab uses live Claude calls, a real
LangGraph agent, real eval suites and real traces.

| Module | What the applicant does | JD requirement |
|---|---|---|
| **RAG lab** | Tune chunking, top-k, score threshold and prompt on a live policy assistant, then run a 16-case eval (accuracy, groundedness, hallucination rate, abstention, citations, latency, tokens) | Build RAG systems; evaluate accuracy and hallucination |
| **Agent lab** | Fix a deliberately weak LangGraph procurement agent (system prompt, tool descriptions, step budget, memory) until 6 business scenarios pass: policy thresholds, a supplier on probation, duplicate POs, **prompt injection via tool data**, out-of-scope requests and multi-step bulk work | Agents, tool calling, memory, multi-step reasoning, decision logic, reliability |
| **Coding lab** | Write Python against hidden tests that run in an **isolated Azure sandbox**: chunking, hybrid search (RRF), retrieval metrics, a robust agent loop and a PII guardrail | Strong Python fundamentals |
| **Mock interview** | A Claude interviewer runs one of 7 tracks (RAG, agents, evals, production/MLOps, ownership, Microsoft AI stack, system design), then scores answers against a rubric | Explain what you built, why, and how trust was established |
| **Stakeholder role-play** | A discovery meeting with a procurement manager, AP lead or HR ops manager who has hidden facts; scoring shows which facts you uncovered | Partner with business stakeholders |
| **Code review** | Review a teammate's PR (RAG endpoint, agent loop, eval script) seeded with production issues; get graded on what you caught | Production readiness and evaluation rigour |
| **Traces** | Inspect every LLM call, retrieval, tool call, graph node and sandbox run with latency and tokens | Monitoring and observability |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and the
reasoning behind it, which is good material to discuss in an interview.

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # add ANTHROPIC_API_KEY; .env is git-ignored
SANDBOX=local uvicorn app.main:app --reload
# open http://localhost:8000
```

Without `ANTHROPIC_API_KEY` the app runs in **offline demo mode** with a fake
model, which is useful for UI work and for the test suite (`python -m pytest`).

`SANDBOX=local` runs coding-lab code in a resource-limited subprocess. Use it
**for development only**: the child process runs as the same OS user as the web
server. Production uses Azure dynamic sessions (below). With `SANDBOX=off`
the coding lab is disabled.

## Deploy to Azure (small account)

The target is close to $0 when idle:

* **Azure Container Apps, consumption plan**, 0.5 vCPU / 1 GiB, `min-replicas 0`.
  It scales to zero between practice sessions, and the monthly free grant usually
  covers light use.
* **Container Apps dynamic sessions** (PythonLTS pool, egress disabled) for the
  coding lab. It is billed only while a sandbox session is allocated.
* **No Log Analytics** and **no Azure Container Registry**: the image is built by
  GitHub Actions and pushed to GitHub Container Registry for free.

Steps:

1. Merge to `main`. The `image` workflow pushes `ghcr.io/<owner>/ai_engineer_pod:latest`.
   Either make the package public (it contains no secrets) or pass
   `GHCR_USER`/`GHCR_TOKEN` (a PAT with `read:packages`) to the deploy script.
2. From a shell logged in with `az login`:

   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...      # never commit this
   export ACCESS_CODE=pick-a-shared-code    # applicants type this to get in
   export IMAGE=ghcr.io/<owner>/ai_engineer_pod:latest
   ./infra/deploy.sh
   ```

   The script creates the resource group, environment, session pool and app.
   It stores the key and access code as **Container App secrets** and grants the
   app's **managed identity** permission to run code in the pool only.
3. Delete everything later with `./infra/teardown.sh`.

### Protecting your Claude key and budget

* The key lives only in a Container App secret, never in the repo or the image.
* Applicant code runs in the Azure sandbox, which never receives the key and has no network egress.
* An **access code** gates the site, with a login rate limit.
* `SESSION_TOKEN_BUDGET` (default 400k tokens) caps each applicant session, and
  `DAILY_TOKEN_BUDGET` (default 5M) caps the whole site per day.
* `MODEL` defaults to `claude-opus-5-5` at `EFFORT=low`. For a much cheaper site,
  set `MODEL=claude-haiku-5-5`. As a rough guide on Opus 5.5, one full RAG eval
  costs about $0.40 and one full agent eval about $0.80. Haiku 5.5 is roughly 40x cheaper.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | (none) | Claude API key (secret) |
| `ACCESS_CODE` | empty (no gate) | Shared sign-in code |
| `MODEL` / `EFFORT` | `claude-opus-5-5` / `low` | Model and effort for every call |
| `FALLBACKS` | `default` | Server-side refusal fallback on models that support it (`off` to disable) |
| `LLM_PROVIDER` | `anthropic` if a key is set, else `fake` | `fake` = offline demo |
| `SANDBOX` | `off` | `azure`, `local` (dev only) or `off` |
| `AZURE_SESSION_POOL_ENDPOINT` | (none) | Pool management endpoint (set by deploy.sh) |
| `SESSION_TOKEN_BUDGET` / `DAILY_TOKEN_BUDGET` | 400000 / 5000000 | Spend caps |
| `DB_PATH` | `./podsim.db` | SQLite file for sessions, usage, traces and attempts |

## Known limits (v1)

* State lives in SQLite inside the container and in memory, so it resets when the
  app scales to zero or redeploys. `max-replicas` is 1 for this reason.
* Agent and interview conversations are kept in memory per replica.
* Grading uses an LLM judge for open-ended answers; scores are guidance, not a hiring decision.
