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
