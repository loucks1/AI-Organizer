#!/usr/bin/env python3
"""Quick CLI search of the drawer inventory (smoke-test helper).

Usage: python3 search.py "torx" [--db inventory.db]
Env: INVENTORY_DB
"""
import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import search_inventory  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    print(json.dumps(search_inventory(args.query, args.limit), indent=2))
