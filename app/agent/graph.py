"""The procurement agent as a LangGraph state machine.

    START -> agent --(tool calls?)--> tools --(steps < max?)--> agent ... -> END
                  \\-> END                   \\-> halt -> END

* Tool calling: Claude chooses tools; we execute them against a per-run World.
* Multi-step reasoning: the loop continues until Claude answers or max_steps.
* Decision logic / guardrails: step limit, tool errors returned to the model as
  is_error results (so it can recover) rather than crashing the run.
* Memory: chat mode keeps recent turns verbatim and folds older ones into a summary.
"""
from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .. import llm, tracing
from ..data.company import World
from .config import AgentConfig
from .tools import ToolError, run_tool, tool_definitions


class AgentState(TypedDict, total=False):
    messages: list[dict]
    steps: int
    final: str
    halted: bool
    tool_calls: list[dict]


def _agent_node(state: AgentState, config) -> dict:
    cfg: AgentConfig = config["configurable"]["agent_config"]
    with tracing.span("node", "agent", {"step": state.get("steps", 0)}):
        reply = llm.chat(cfg.system_prompt, state["messages"], tools=tool_definitions(cfg.tool_descriptions),
                         max_tokens=4096, label="agent.llm")
    messages = state["messages"] + [{"role": "assistant", "content": reply.content}]
    update: dict[str, Any] = {"messages": messages}
    if not reply.tool_uses:
        update["final"] = reply.text
    return update


def _tools_node(state: AgentState, config) -> dict:
    world: World = config["configurable"]["world"]
    last = state["messages"][-1]["content"]
    results, calls = [], list(state.get("tool_calls", []))
    for block in last:
        if block.get("type") != "tool_use":
            continue
        name, args = block["name"], block.get("input") or {}
        with tracing.span("tool", name, args) as sp:
            try:
                out = run_tool(world, name, args)
                content, is_error = json.dumps(out, default=str), False
            except ToolError as e:
                content, is_error = f"Error: {e}", True
            except Exception as e:  # malformed arguments etc.
                content, is_error = f"Error: {type(e).__name__}: {e}", True
            sp["output"] = content
        calls.append({"name": name, "input": args, "is_error": is_error, "output": content[:500]})
        r = {"type": "tool_result", "tool_use_id": block["id"], "content": content}
        if is_error:
            r["is_error"] = True
        results.append(r)
    return {"messages": state["messages"] + [{"role": "user", "content": results}],
            "steps": state.get("steps", 0) + 1, "tool_calls": calls}


def _halt_node(state: AgentState, config) -> dict:
    return {"halted": True,
            "final": "[halted] The agent hit its step limit before finishing. Partial work may have been done."}


def _after_agent(state: AgentState) -> str:
    return END if "final" in state else "tools"


def _after_tools(state: AgentState, config) -> str:
    cfg: AgentConfig = config["configurable"]["agent_config"]
    return "halt" if state.get("steps", 0) >= cfg.max_steps else "agent"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("agent", _agent_node)
    g.add_node("tools", _tools_node)
    g.add_node("halt", _halt_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", _after_agent, {"tools": "tools", END: END})
    g.add_conditional_edges("tools", _after_tools, {"agent": "agent", "halt": "halt"})
    g.add_edge("halt", END)
    return g.compile()


GRAPH = build_graph()


def run_agent(messages: list[dict], cfg: AgentConfig, world: World) -> AgentState:
    return GRAPH.invoke(
        {"messages": messages, "steps": 0, "tool_calls": []},
        config={"configurable": {"agent_config": cfg, "world": world}, "recursion_limit": 4 * cfg.max_steps + 10},
    )


# ---------------------------------------------------------------- chat mode with memory

class ChatMemory:
    """Per-session conversation memory with a summary of older turns."""

    def __init__(self):
        self.world = World()
        self.messages: list[dict] = []
        self.turns = 0
        self.summary: list[str] = []  # one line per older turn


_SESSIONS: dict[str, ChatMemory] = {}


def chat_turn(session_id: str, text: str, cfg: AgentConfig, reset: bool = False) -> dict:
    if reset or session_id not in _SESSIONS:
        _SESSIONS[session_id] = ChatMemory()
    mem = _SESSIONS[session_id]
    if mem.turns >= cfg.memory_turns:
        # Fold the verbatim history into a summary and start a fresh message list.
        mem.messages = []
        mem.turns = 0
    if not mem.messages and mem.summary:
        text = ("Summary of earlier conversation (memory):\n- " + "\n- ".join(mem.summary[-10:])
                + f"\n\nNew request: {text}")
    state = run_agent(mem.messages + [{"role": "user", "content": text}], cfg, mem.world)
    mem.messages = state["messages"]
    if state.get("halted"):
        # Leave the conversation in a valid state (tool results were the last message).
        mem.messages = mem.messages + [{"role": "assistant", "content": [{"type": "text", "text": state["final"]}]}]
    mem.turns += 1
    mem.summary.append(f"User asked: {text[-200:]!r}; agent replied: {state['final'][:200]!r}")
    return {"reply": state["final"], "tool_calls": state.get("tool_calls", []), "steps": state.get("steps", 0),
            "halted": bool(state.get("halted")), "pos_created": mem.world.created}
