import pytest

from app.coding.exercises import EXERCISES
from app.coding.runner import run_exercise

from .solutions import SOLUTIONS


@pytest.mark.parametrize("ex", EXERCISES, ids=lambda e: e["id"])
def test_reference_solution_passes(ex):
    r = run_exercise(ex["id"], SOLUTIONS[ex["id"]])
    assert r["total"] >= 5
    assert r["passed"] == r["total"], [t for t in r["tests"] if not t["passed"]]


@pytest.mark.parametrize("ex", EXERCISES, ids=lambda e: e["id"])
def test_starter_fails(ex):
    r = run_exercise(ex["id"], ex["starter"])
    assert r["total"] >= 5 and r["passed"] == 0


def test_syntax_error_reported():
    r = run_exercise("rrf", "def rrf(:\n")
    assert r["passed"] == 0 and "failed to load" in r["tests"][0]["error"]


def test_sandbox_has_no_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    code = SOLUTIONS["rrf"] + "\nimport os\nprint('KEY=' + os.environ.get('ANTHROPIC_API_KEY', 'none'))\n"
    r = run_exercise("rrf", code)
    assert "KEY=none" in r["stdout"]


def test_infinite_loop_times_out():
    r = run_exercise("rrf", "while True:\n    pass\n")
    assert r["passed"] == 0
