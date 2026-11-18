#!/usr/bin/env python3
"""Drawer inventory — MCP server over stdio (Python stdlib only, no deps).

Implements the MCP JSON-RPC surface a client needs: initialize,
tools/list, tools/call. Tools:
  search_inventory(query, limit) — name/category/tags/location match
  list_location(location, limit) — items in a location path
  get_item(item_id)              — item + its photo file
  check_parts(parts)             — project parts list vs owned inventory
  list_pending_photos()          — photos awaiting categorization

Run:  python3 mcp_server.py        (reads JSON-RPC lines on stdin)
Env:  INVENTORY_DB (default inventory.db next to this file)
"""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("INVENTORY_DB", os.path.join(HERE, "inventory.db"))


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def item_dict(r):
    d = dict(r)
    try:
        d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
    except (ValueError, TypeError):
        d["tags"] = []
    return d


def search_inventory(query, limit=20):
    like = f"%{query}%"
    with db() as conn:
        rows = conn.execute(
            "SELECT i.*, l.path AS location, p.filename AS photo_file "
            "FROM items i JOIN locations l ON l.id = i.location_id "
            "JOIN photos p ON p.id = i.photo_id "
            "WHERE i.name LIKE ? OR i.category LIKE ? OR i.tags LIKE ? OR l.path LIKE ? "
            "ORDER BY i.confidence DESC LIMIT ?",
            (like, like, like, like, limit)).fetchall()
    return [item_dict(r) for r in rows]


def list_location(location, limit=50):
    with db() as conn:
        rows = conn.execute(
            "SELECT i.*, l.path AS location, p.filename AS photo_file "
            "FROM items i JOIN locations l ON l.id = i.location_id "
            "JOIN photos p ON p.id = i.photo_id "
            "WHERE l.path LIKE ? ORDER BY i.name LIMIT ?",
            (f"%{location}%", limit)).fetchall()
    return [item_dict(r) for r in rows]


def get_item(item_id):
    with db() as conn:
        row = conn.execute(
            "SELECT i.*, l.path AS location, p.filename AS photo_file "
            "FROM items i JOIN locations l ON l.id = i.location_id "
            "JOIN photos p ON p.id = i.photo_id WHERE i.id = ?",
            (item_id,)).fetchone()
    return item_dict(row) if row else None


def check_parts(parts):
    return [{"part": p, "matches": search_inventory(p, limit=5)} for p in parts]


def list_pending_photos():
    with db() as conn:
        rows = conn.execute(
            "SELECT p.id, p.filename, p.hint, l.path AS location "
            "FROM photos p JOIN locations l ON l.id = p.location_id "
            "WHERE p.status = 'pending' ORDER BY p.id").fetchall()
    return [dict(r) for r in rows]


TOOLS = [
    {"name": "search_inventory",
     "description": "Search the drawer inventory by name, category, tag, or location.",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"},
                                    "limit": {"type": "integer", "default": 20}},
                     "required": ["query"]}},
    {"name": "list_location",
     "description": "List everything stored in a location, e.g. 'Garage / Parts cabinet / Drawer 3'.",
     "inputSchema": {"type": "object",
                     "properties": {"location": {"type": "string"},
                                    "limit": {"type": "integer", "default": 50}},
                     "required": ["location"]}},
    {"name": "get_item",
     "description": "Get one item with its location and photo file.",
     "inputSchema": {"type": "object",
                     "properties": {"item_id": {"type": "integer"}},
                     "required": ["item_id"]}},
    {"name": "check_parts",
     "description": "Check a project parts list against owned inventory; returns matches per part.",
     "inputSchema": {"type": "object",
                     "properties": {"parts": {"type": "array", "items": {"type": "string"}}},
                     "required": ["parts"]}},
    {"name": "list_pending_photos",
     "description": "List photos uploaded but not yet categorized.",
     "inputSchema": {"type": "object", "properties": {}}},
]

DISPATCH = {
    "search_inventory": lambda a: search_inventory(a.get("query", ""), a.get("limit", 20)),
    "list_location": lambda a: list_location(a.get("location", ""), a.get("limit", 50)),
    "get_item": lambda a: get_item(a["item_id"]),
    "check_parts": lambda a: check_parts(a.get("parts", [])),
    "list_pending_photos": lambda a: list_pending_photos(),
}


def reply(req_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n")
    sys.stdout.flush()


def reply_error(req_id, code, message):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id,
                                 "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


def handle(msg):
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        reply(req_id, {"protocolVersion": "2024-11-05",
                       "capabilities": {"tools": {}},
                       "serverInfo": {"name": "drawer-inventory", "version": "0.1.0"}})
    elif method == "notifications/initialized":
        pass  # notification: no reply
    elif method == "tools/list":
        reply(req_id, {"tools": TOOLS})
    elif method == "tools/call":
        params = msg.get("params", {})
        name, args = params.get("name"), params.get("arguments", {})
        if name not in DISPATCH:
            reply_error(req_id, -32602, f"unknown tool: {name}")
            return
        try:
            result = DISPATCH[name](args)
        except Exception as exc:  # noqa: BLE001 — surface as a tool error
            reply(req_id, {"content": [{"type": "text", "text": f"error: {exc}"}],
                           "isError": True})
            return
        reply(req_id, {"content": [{"type": "text",
                                     "text": json.dumps(result, indent=2)}]})
    elif req_id is not None:
        reply_error(req_id, -32601, f"method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except ValueError as exc:
            reply_error(None, -32700, f"parse error: {exc}")


if __name__ == "__main__":
    main()
