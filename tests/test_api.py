from fastapi.testclient import TestClient

from app import llm
from app.interview.sessions import CriterionScore, ReviewGrade, Scorecard
from app.main import app

client = TestClient(app)


def login():
    r = client.post("/api/login", json={"code": "test-code", "name": "Tester"})
    assert r.status_code == 200


def test_requires_login():
    c = TestClient(app)
    assert c.get("/api/me").status_code == 401
    assert c.post("/api/login", json={"code": "wrong"}).status_code == 401


def test_me_and_company():
    login()
    me = client.get("/api/me").json()
    assert me["name"] == "Tester" and me["provider"] == "fake"
    assert "DB-8812" in client.get("/api/company").json()["items"]


def test_rag_ask_creates_trace():
    login()
    r = client.post("/api/rag/ask", json={"question": "What is the hotel cap per night?"}).json()
    spans = client.get(f"/api/traces/{r['trace_id']}").json()
    assert {s["kind"] for s in spans} >= {"retrieval", "llm"}


def test_interview_flow():
    login()
    cat = client.get("/api/interview/catalog").json()
    assert "agents" in cat["tracks"] and "procurement" in cat["personas"]
    s = client.post("/api/interview/start", json={"topic": "agents"}).json()
    client.post("/api/conversation/reply", json={"id": s["id"], "text": "I built a LangGraph agent..."})
    llm.fake_parse_script(Scorecard(criteria=[CriterionScore(criterion="x", score=4, evidence="e", improvement="i")],
                                    overall=4.0, recommendation="hire", strengths=[], improvements=[], model_answer=""))
    f = client.post("/api/conversation/finish", json={"id": s["id"]}).json()
    assert f["scorecard"]["recommendation"] == "hire"
    assert any(a["module"] == "interview" for a in client.get("/api/attempts").json())


def test_review_grade():
    login()
    llm.fake_parse_script(ReviewGrade(issues_found=["a"], issues_missed=[], valid_extra_points=[], incorrect_claims=[],
                                      score=70, feedback="ok"))
    r = client.post("/api/review/grade", json={"review_id": "agent_loop", "text": "No step limit; eval() is unsafe."})
    assert r.json()["score"] == 70


def test_coding_run():
    login()
    from tests.solutions import SOLUTIONS
    r = client.post("/api/coding/run", json={"exercise_id": "rrf", "code": SOLUTIONS["rrf"]}).json()
    assert r["passed"] == r["total"]


def test_budget_enforced(monkeypatch):
    login()
    monkeypatch.setenv("SESSION_TOKEN_BUDGET", "0")
    r = client.post("/api/rag/ask", json={"question": "What is the hotel cap per night?"})
    assert r.status_code == 429


def test_interview_start_returns_first_question():
    login()
    llm.fake_script(llm.text_reply("Hi, I'm Sam. Tell me about an agent you shipped."))
    s = client.post("/api/interview/start", json={"topic": "agents"}).json()
    assert s["id"] and "agent you shipped" in s["message"]


def test_empty_model_reply_is_an_error_not_a_blank_bubble():
    login()
    llm.fake_script(llm.Reply([{"type": "thinking", "thinking": "", "signature": "s"}], "", stop_reason="max_tokens"))
    r = client.post("/api/interview/start", json={"topic": "agents"})
    assert r.status_code == 502 and "empty reply" in r.json()["detail"]


def test_claude_api_errors_explain_the_config_problem(monkeypatch):
    import anthropic
    import httpx2

    from app.config import get_settings

    login()
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def boom(*_):
        raise anthropic.AuthenticationError("invalid x-api-key", response=httpx2.Response(401, request=req), body=None)

    monkeypatch.setattr(llm, "_real_chat", boom)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert get_settings().provider == "anthropic"
    r = client.post("/api/interview/start", json={"topic": "agents"})
    assert r.status_code == 502 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_reply_failure_keeps_history_valid(monkeypatch):
    from app.interview import sessions

    login()
    s = client.post("/api/interview/start", json={"topic": "agents"}).json()
    before = len(sessions._STORE[s["id"]]["messages"])
    llm.fake_script(llm.text_reply(""))
    r = client.post("/api/conversation/reply", json={"id": s["id"], "text": "answer"})
    assert r.status_code == 502
    assert len(sessions._STORE[s["id"]]["messages"]) == before


def test_survives_restart():
    """Scale-to-zero wipes process memory and the local SQLite file; sign-in and conversations must survive."""
    from app import db
    from app.interview import sessions

    login()
    s = client.post("/api/interview/start", json={"topic": "agents"}).json()
    assert s["state"]
    # Simulate a cold start: empty conversation cache and an empty sessions table.
    sessions._STORE.clear()
    with db.tx() as c:
        c.execute("DELETE FROM sessions")
    assert client.get("/api/me").json()["name"] == "Tester"
    r = client.post("/api/conversation/reply", json={"id": s["id"], "text": "my answer", "state": s["state"]})
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    sessions._STORE.clear()
    llm.fake_parse_script(Scorecard(criteria=[CriterionScore(criterion="x", score=3, evidence="e", improvement="i")],
                                    overall=3.0, recommendation="lean hire", strengths=[], improvements=[], model_answer=""))
    f = client.post("/api/conversation/finish", json={"id": s["id"], "state": state})
    assert f.status_code == 200 and "my answer" in f.json()["transcript"]


def test_forged_tokens_rejected():
    from app.interview import sessions

    login()
    s = client.post("/api/stakeholder/start", json={"topic": "procurement"}).json()
    sessions._STORE.clear()
    bad = s["state"][:-3] + ("AAA" if not s["state"].endswith("AAA") else "BBB")
    r = client.post("/api/conversation/reply", json={"id": s["id"], "text": "hi", "state": bad})
    assert r.status_code == 404
    c = TestClient(app)
    c.cookies.set("podsim_session", "made-up-session-id")
    assert c.get("/api/me").status_code == 401


def test_restored_conversation_rebuilds_system_prompt():
    from app.interview import sessions

    login()
    s = client.post("/api/stakeholder/start", json={"topic": "procurement"}).json()
    st = sessions._load(s["id"], s["state"])
    assert st["system"] == sessions._STORE[s["id"]]["system"] and "stakeholder" in st["system"]
    assert sessions.signing.loads("session", s["state"]) is None  # tokens are bound to their purpose
