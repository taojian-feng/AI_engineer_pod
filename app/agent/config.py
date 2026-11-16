"""What the applicant can change in the Agent lab.

The defaults are a deliberately weak *baseline* - like a hurried prototype - so
there is something real to diagnose and fix with the eval suite.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

BASELINE_SYSTEM_PROMPT = """You are a procurement assistant for Meridian Basin Energy Services.
Help users order parts quickly."""

BASELINE_TOOL_DESCRIPTIONS = {
    "search_items": "Search items.",
    "get_item": "Get an item.",
    "list_open_pos": "List POs.",
    "get_supplier": "Get supplier info.",
    "list_suppliers_for_item": "List suppliers.",
    "search_policies": "Search documents.",
    "create_purchase_order": "Create a PO.",
}


class AgentConfig(BaseModel):
    system_prompt: str = BASELINE_SYSTEM_PROMPT
    tool_descriptions: dict[str, str] = Field(default_factory=lambda: dict(BASELINE_TOOL_DESCRIPTIONS))
    max_steps: int = Field(4, ge=1, le=25, description="Max tool-execution rounds before the graph halts")
    memory_turns: int = Field(6, ge=1, le=30, description="Chat turns kept verbatim before older turns are summarised")
