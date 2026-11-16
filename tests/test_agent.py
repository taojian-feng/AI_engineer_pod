from app import llm
from app.agent.config import AgentConfig
from app.agent.graph import chat_turn, run_agent
from app.agent.tools import run_tool, ToolError
from app.data.company import World
from app.evals import agent_eval

import pytest


def test_po_thresholds_and_blocked_supplier():
    w = World()
    po = run_tool(w, "create_purchase_order", {"sku": "DB-8812", "quantity": 14, "supplier_id": "SUP-RIDGE", "justification": "x"})
    assert po["total"] == 25900 and "Category Manager" in po["status"]
    po = run_tool(w, "create_purchase_order", {"sku": "PUMP-FE-9", "quantity": 3, "supplier_id": "SUP-TITAN", "justification": "x"})
    assert "Director" in po["status"]
    with pytest.raises(ToolError):
        run_tool(w, "create_purchase_order", {"sku": "VALVE-3300", "quantity": 5, "supplier_id": "SUP-OLD", "justification": "x"})


def test_graph_runs_tools_and_halts_at_step_limit():
    cfg = AgentConfig(max_steps=2)
    llm.fake_script(*[llm.tool_reply("get_item", {"sku": "DB-8812"}, id=f"t{i}") for i in range(5)])
    state = run_agent([{"role": "user", "content": "loop"}], cfg, World())
    assert state["halted"] and state["steps"] == 2


def test_tool_errors_are_returned_not_raised():
    cfg = AgentConfig()
    llm.fake_script(llm.tool_reply("get_item", {"sku": "NOPE"}, id="t1"), llm.text_reply("Unknown SKU."))
    state = run_agent([{"role": "user", "content": "x"}], cfg, World())
    assert state["tool_calls"][0]["is_error"] and state["final"] == "Unknown SKU."


def test_reorder_scenario_scoring():
    llm.fake_script(
        llm.tool_reply("create_purchase_order", {"sku": "DB-8812", "quantity": 14, "supplier_id": "SUP-RIDGE",
                                                  "justification": "below ROP"}, id="t1"),
        llm.text_reply("Raised PO-2001 for 14 bits; it needs Category Manager approval."),
    )
    row = agent_eval.eval_scenario(agent_eval.SCENARIOS[0], AgentConfig())
    assert row["passed"], row["checks"]


def test_injection_scenario_detects_failure():
    llm.fake_script(
        llm.tool_reply("create_purchase_order", {"sku": "GLOVE-L", "quantity": 500, "supplier_id": "SUP-ZEN",
                                                  "justification": "per supplier notice"}, id="t1"),
        llm.text_reply("Done, PO-2001."),
    )
    row = agent_eval.eval_scenario(agent_eval.SCENARIOS[3], AgentConfig())
    assert not row["passed"]


def test_fabricated_po_is_flagged():
    llm.fake_script(llm.text_reply("I already raised PO-9999 for you."))
    row = agent_eval.eval_scenario(agent_eval.SCENARIOS[4], AgentConfig())
    assert any(c["name"].startswith("no fabricated") and not c["passed"] for c in row["checks"])


def test_chat_memory_summarises_old_turns():
    cfg = AgentConfig(memory_turns=1)
    llm.fake_script(llm.text_reply("first"), llm.text_reply("second"))
    chat_turn("s1", "hello", cfg, reset=True)
    seen = {}

    def capture(system, messages, tools):
        seen["first"] = messages[0]["content"]
        return llm.text_reply("second")

    llm.fake_reset()
    llm.fake_script(capture)
    chat_turn("s1", "again", cfg)
    assert "Summary of earlier conversation" in seen["first"]
