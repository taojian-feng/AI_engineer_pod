"""Tools the procurement agent can call. They act on a per-run `World`.

The *implementations* are fixed. Applicants can edit the *descriptions* that the
model sees (see `DEFAULT_TOOL_DESCRIPTIONS` in config.py) - writing good tool
descriptions is a core agent-engineering skill.
"""
from __future__ import annotations

import math

from ..data.company import World
from ..rag.pipeline import retrieve_for_agent

READ_ONLY = {"search_items", "get_item", "list_open_pos", "get_supplier", "list_suppliers_for_item",
             "search_policies"}
WRITE = {"create_purchase_order"}

SCHEMAS = {
    "search_items": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Free text, e.g. 'drill bit' or 'critical'."}},
        "required": ["query"], "additionalProperties": False,
    },
    "get_item": {
        "type": "object", "properties": {"sku": {"type": "string"}},
        "required": ["sku"], "additionalProperties": False,
    },
    "list_open_pos": {
        "type": "object", "properties": {"sku": {"type": "string", "description": "Optional SKU filter; empty string for all."}},
        "required": ["sku"], "additionalProperties": False,
    },
    "get_supplier": {
        "type": "object", "properties": {"supplier_id": {"type": "string"}},
        "required": ["supplier_id"], "additionalProperties": False,
    },
    "list_suppliers_for_item": {
        "type": "object", "properties": {"sku": {"type": "string"}},
        "required": ["sku"], "additionalProperties": False,
    },
    "search_policies": {
        "type": "object", "properties": {"query": {"type": "string"}},
        "required": ["query"], "additionalProperties": False,
    },
    "create_purchase_order": {
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
            "quantity": {"type": "integer"},
            "supplier_id": {"type": "string"},
            "justification": {"type": "string"},
        },
        "required": ["sku", "quantity", "supplier_id", "justification"], "additionalProperties": False,
    },
}


class ToolError(Exception):
    pass


def tool_definitions(descriptions: dict[str, str]) -> list[dict]:
    return [
        {"name": name, "description": descriptions.get(name, name), "input_schema": schema, "strict": True}
        for name, schema in SCHEMAS.items()
    ]


def _item(world: World, sku: str) -> dict:
    sku = sku.strip().upper()
    if sku not in world.items:
        raise ToolError(f"Unknown SKU '{sku}'. Use search_items to find valid SKUs.")
    return world.items[sku]


def run_tool(world: World, name: str, args: dict):
    if name == "search_items":
        q = args.get("query", "").lower()
        out = []
        for sku, it in world.items.items():
            hay = f"{sku} {it['description']} {it['category']} {'critical' if it['critical'] else ''}".lower()
            if not q or any(tok in hay for tok in q.split()):
                out.append({"sku": sku, "description": it["description"], "critical": it["critical"]})
        return out or "No items matched."
    if name == "get_item":
        sku = args["sku"].strip().upper()
        return {"sku": sku, **_item(world, sku)}
    if name == "list_open_pos":
        sku = (args.get("sku") or "").strip().upper()
        return [p for p in world.pos if not sku or p["sku"] == sku] or "No open POs."
    if name == "get_supplier":
        sid = args["supplier_id"].strip().upper()
        if sid not in world.suppliers:
            raise ToolError(f"Unknown supplier '{sid}'.")
        return {"supplier_id": sid, **world.suppliers[sid]}
    if name == "list_suppliers_for_item":
        sku = args["sku"].strip().upper()
        _item(world, sku)
        return [
            {"supplier_id": sid, "name": s["name"], "status": s["status"], "unit_price": world.price(sid, sku)}
            for sid, s in world.suppliers.items() if sku in s["supplies"]
        ]
    if name == "search_policies":
        return retrieve_for_agent(args["query"])
    if name == "create_purchase_order":
        sku = args["sku"].strip().upper()
        _item(world, sku)
        sid = args["supplier_id"].strip().upper()
        qty = int(args["quantity"])
        if sid not in world.suppliers:
            raise ToolError(f"Unknown supplier '{sid}'.")
        sup = world.suppliers[sid]
        if sku not in sup["supplies"]:
            raise ToolError(f"{sid} is not an approved source for {sku}.")
        if sup["status"] == "blocked":
            raise ToolError(f"{sid} is blocked and cannot receive purchase orders.")
        if qty <= 0:
            raise ToolError("Quantity must be positive.")
        total = round(qty * world.price(sid, sku), 2)
        if total > 50000:
            status = "pending_approval: Director of Supply Chain (3 quotes required)"
        elif total > 10000:
            status = "pending_approval: Category Manager"
        else:
            status = "issued"
        po = dict(po_id=f"PO-{world.next_po}", sku=sku, quantity=qty, supplier_id=sid, status=status,
                  total=total, justification=args.get("justification", ""))
        world.next_po += 1
        world.pos.append(po)
        world.created.append(po)
        return po
    raise ToolError(f"Unknown tool '{name}'.")


def replenishment_qty(item: dict, open_qty: int) -> int:
    """Reference calculation from STD-SCM-007 section 2 (used by the evals)."""
    need = item["target_level"] - (item["on_hand"] + open_qty)
    if need <= 0:
        return 0
    return int(math.ceil(need / item["moq"]) * item["moq"])
