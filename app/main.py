"""Pod Simulator - FastAPI entry point."""
from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, llm, tracing
from .agent import graph as agent_graph
from .agent.config import AgentConfig
from .coding import exercises as coding_ex
from .coding import runner as coding_runner
from .coding import sandbox
from .config import get_settings
from .data.company import ITEMS, OPEN_POS, SUPPLIERS
from .evals import agent_eval, rag_eval
from .interview import sessions as iv
from .interview.tracks import PERSONAS, REVIEWS, TRACKS
from .rag.index import load_docs
from .rag.pipeline import RagConfig, answer

STATIC = Path(__file__).parent / "static"
COOKIE = "podsim_session"

app = FastAPI(title="Pod Simulator", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------------------------------------------------------------- errors

@app.exception_handler(llm.BudgetExceeded)
async def _budget(_, e):
    return JSONResponse({"detail": str(e)}, status_code=429)


@app.exception_handler(llm.ModelRefused)
async def _refused(_, e):
    return JSONResponse({"detail": str(e)}, status_code=422)


@app.exception_handler(sandbox.SandboxUnavailable)
async def _nosandbox(_, e):
    return JSONResponse({"detail": str(e)}, status_code=503)


@app.exception_handler(llm.LLMError)
async def _llm_error(_, e):
    return JSONResponse({"detail": str(e)}, status_code=e.status)


@app.exception_handler(Exception)
async def _unexpected(_, e):
    # Always answer JSON so the page can show the reason instead of a bare "Request failed (500)".
    return JSONResponse({"detail": f"Server error: {type(e).__name__}: {e}"[:500]}, status_code=500)


@app.exception_handler(KeyError)
async def _notfound(_, e):
    return JSONResponse({"detail": str(e).strip("'\"")}, status_code=404)


# ---------------------------------------------------------------- sessions / auth

_login_failures: dict[str, list[float]] = defaultdict(list)


class Login(BaseModel):
    code: str = ""
    name: str = Field("", max_length=60)


def _new_session(name: str) -> str:
    sid = secrets.token_urlsafe(24)
    with db.tx() as c:
        c.execute("INSERT INTO sessions VALUES (?,?,?)", (sid, time.time(), name or "Applicant"))
    return sid


def _set_cookie(resp: Response, request: Request, sid: str) -> None:
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=https, max_age=7 * 24 * 3600)


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    s = get_settings()
    ip = request.client.host if request.client else "?"
    recent = [t for t in _login_failures[ip] if t > time.time() - 600]
    _login_failures[ip] = recent
    if len(recent) >= 10:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    if s.access_code and not hmac.compare_digest(body.code.encode(), s.access_code.encode()):
        _login_failures[ip].append(time.time())
        raise HTTPException(401, "Wrong access code.")
    sid = _new_session(body.name.strip())
    _set_cookie(response, request, sid)
    return {"ok": True}


def session_id(request: Request) -> str:
    sid = request.cookies.get(COOKIE)
    if sid and db.conn().execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
        return sid
    raise HTTPException(401, "Please sign in with the access code.")


def begin(sid: str) -> str:
    """Bind this request to the applicant's session and start a new trace."""
    tracing.current_session.set(sid)
    return tracing.new_trace()


@app.get("/api/me")
def me(sid: str = Depends(session_id)):
    s = get_settings()
    row = db.conn().execute("SELECT display_name, created FROM sessions WHERE id=?", (sid,)).fetchone()
    return {
        "name": row["display_name"], "tokens_used": db.session_tokens(sid), "token_budget": s.session_token_budget,
        "model": s.model, "effort": s.effort, "provider": s.provider, "sandbox": sandbox.backend(),
        "access_code_required": bool(s.access_code),
    }


@app.get("/api/config")
def public_config():
    s = get_settings()
    return {"access_code_required": bool(s.access_code), "provider": s.provider}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


# ---------------------------------------------------------------- company data & docs

@app.get("/api/company")
def company(sid: str = Depends(session_id)):
    return {"items": ITEMS, "suppliers": SUPPLIERS, "open_pos": OPEN_POS,
            "docs": {name: text for name, text in load_docs().items()}}


# ---------------------------------------------------------------- RAG lab

class RagAsk(BaseModel):
    config: RagConfig = Field(default_factory=RagConfig)
    question: str = Field(min_length=3, max_length=1000)


class RagEval(BaseModel):
    config: RagConfig = Field(default_factory=RagConfig)
    use_judge: bool = True
    case_ids: list[str] | None = None


@app.get("/api/rag/baseline")
def rag_baseline():
    return {"config": RagConfig().model_dump(), "dataset": rag_eval.DATASET}


@app.post("/api/rag/ask")
def rag_ask(body: RagAsk, sid: str = Depends(session_id)):
    tid = begin(sid)
    return {**answer(body.question, body.config), "trace_id": tid}


@app.post("/api/rag/eval")
def rag_run_eval(body: RagEval, sid: str = Depends(session_id)):
    tid = begin(sid)
    res = rag_eval.run(body.config, body.use_judge, body.case_ids)
    if not body.case_ids:
        db.save_attempt(sid, "rag", body.config.model_dump(), {"metrics": res["metrics"]}, res["score"])
    return {**res, "trace_id": tid}


# ---------------------------------------------------------------- Agent lab

class AgentChat(BaseModel):
    config: AgentConfig = Field(default_factory=AgentConfig)
    message: str = Field(min_length=1, max_length=2000)
    reset: bool = False


class AgentEval(BaseModel):
    config: AgentConfig = Field(default_factory=AgentConfig)
    scenario_ids: list[str] | None = None


@app.get("/api/agent/baseline")
def agent_baseline():
    return {"config": AgentConfig().model_dump(),
            "scenarios": [{"id": s["id"], "title": s["title"], "prompt": s["prompt"]} for s in agent_eval.SCENARIOS]}


@app.post("/api/agent/chat")
def agent_chat(body: AgentChat, sid: str = Depends(session_id)):
    tid = begin(sid)
    return {**agent_graph.chat_turn(sid, body.message, body.config, body.reset), "trace_id": tid}


@app.post("/api/agent/eval")
def agent_run_eval(body: AgentEval, sid: str = Depends(session_id)):
    tid = begin(sid)
    res = agent_eval.run(body.config, body.scenario_ids)
    if not body.scenario_ids:
        db.save_attempt(sid, "agent", body.config.model_dump(), {"metrics": res["metrics"]}, res["score"])
    return {**res, "trace_id": tid}


# ---------------------------------------------------------------- Coding labs

class CodeRun(BaseModel):
    exercise_id: str
    code: str = Field(max_length=30000)
    feedback: bool = False


@app.get("/api/coding/exercises")
def coding_list():
    return [{k: e[k] for k in ("id", "title", "skill", "minutes", "prompt", "starter")} for e in coding_ex.EXERCISES]


@app.post("/api/coding/run")
def coding_run(body: CodeRun, sid: str = Depends(session_id)):
    tid = begin(sid)
    ex = coding_ex.BY_ID[body.exercise_id]
    with tracing.span("sandbox", f"coding.{body.exercise_id}", {"chars": len(body.code)}) as sp:
        res = coding_runner.run_exercise(body.exercise_id, body.code)
        sp["output"] = {"passed": res["passed"], "total": res["total"], "backend": res["backend"]}
    if body.feedback:
        res["feedback"] = iv.coding_feedback(ex, body.code, res)
    db.save_attempt(sid, "coding", {"exercise": body.exercise_id}, {"passed": res["passed"], "total": res["total"]},
                    res["score"])
    return {**res, "trace_id": tid}


# ---------------------------------------------------------------- Interview, stakeholder, review

class Start(BaseModel):
    topic: str
    coach: bool = False


class Turn(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=6000)


class Finish(BaseModel):
    id: str


class ReviewIn(BaseModel):
    review_id: str
    text: str = Field(min_length=10, max_length=8000)


@app.get("/api/interview/catalog")
def iv_catalog():
    return {
        "tracks": {k: {"title": v["title"], "jd": v["jd"], "rubric": v["rubric"]} for k, v in TRACKS.items()},
        "personas": {k: {"title": v["title"], "function": v["function"], "persona": v["persona"]} for k, v in PERSONAS.items()},
        "reviews": {k: {"title": v["title"], "context": v["context"], "code": v["code"]} for k, v in REVIEWS.items()},
    }


@app.post("/api/interview/start")
def iv_start(body: Start, sid: str = Depends(session_id)):
    begin(sid)
    return iv.start_interview(body.topic, body.coach)


@app.post("/api/stakeholder/start")
def sh_start(body: Start, sid: str = Depends(session_id)):
    begin(sid)
    return iv.start_stakeholder(body.topic)


@app.post("/api/conversation/reply")
def conv_reply(body: Turn, sid: str = Depends(session_id)):
    begin(sid)
    return iv.reply(body.id, body.text)


@app.post("/api/conversation/finish")
def conv_finish(body: Finish, sid: str = Depends(session_id)):
    begin(sid)
    res = iv.finish(body.id)
    card = res["scorecard"]
    db.save_attempt(sid, res["kind"], {"topic": res["topic"]}, {"recommendation": card.get("recommendation")},
                    round(float(card.get("overall") or 0) * 20, 1))
    return res


@app.post("/api/review/grade")
def review_grade(body: ReviewIn, sid: str = Depends(session_id)):
    begin(sid)
    g = iv.grade_review(body.review_id, body.text)
    db.save_attempt(sid, "review", {"review": body.review_id}, {"found": len(g["issues_found"])}, g["score"])
    return g


# ---------------------------------------------------------------- Observability & history

@app.get("/api/traces")
def traces(sid: str = Depends(session_id)):
    return tracing.recent_traces(sid)


@app.get("/api/traces/{trace_id}")
def trace(trace_id: str, sid: str = Depends(session_id)):
    spans = [s for s in tracing.get_trace(trace_id) if s["session_id"] == sid]
    if not spans:
        raise HTTPException(404, "Trace not found")
    return spans


@app.get("/api/attempts")
def attempts(sid: str = Depends(session_id)):
    return db.list_attempts(sid)


@app.get("/healthz")
def health():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
