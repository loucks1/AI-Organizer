#!/usr/bin/env python3
"""File a categorization JSON into the drawer inventory DB.

Usage:
  python3 categorize.py --photo-id 1 --json categorization.json --categorizer muse
Validates the contract in CATEGORIZE.md (bbox 0–1, confidence 0–1), inserts
one item row per entry, marks the photo 'categorized'. Re-running for a
photo replaces its items; the original photo file is never touched.
Env: INVENTORY_DB (default inventory.db next to this file)
The database is created from schema.sql when it is missing or is missing a table.
"""
import argparse
import json
import sys

from inventory_config import connect, ensure_db


def fail(msg):
    print(f"categorize: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo-id", type=int, required=True)
    ap.add_argument("--json", required=True, help="categorization JSON file")
    ap.add_argument("--categorizer", default="muse")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items")
    if not isinstance(items, list):
        fail("JSON must have an 'items' array (see CATEGORIZE.md)")

    ensure_db()
    conn = connect()
    photo = conn.execute("SELECT id, location_id FROM photos WHERE id = ?",
                         (args.photo_id,)).fetchone()
    if photo is None:
        fail(f"no photo with id {args.photo_id}")
    location_id = photo["location_id"]

    rows = []
    for i, it in enumerate(items):
        name = (it.get("name") or "").strip()
        if not name:
            fail(f"item {i}: missing name")
        bbox = it.get("bbox") or [None, None, None, None]
        if len(bbox) != 4 or any(v is not None and not (0 <= v <= 1) for v in bbox):
            fail(f"item {i} ({name}): bbox must be [x, y, w, h] fractions in 0–1")
        conf = it.get("confidence")
        if conf is not None and not (0 <= conf <= 1):
            fail(f"item {i} ({name}): confidence must be 0–1")
        rows.append((args.photo_id, location_id, name,
                     it.get("category"),
                     json.dumps(it.get("tags") or []),
                     it.get("quantity_estimate"),
                     conf, bbox[0], bbox[1], bbox[2], bbox[3],
                     it.get("notes"), args.categorizer))

    with conn:
        conn.execute("DELETE FROM items WHERE photo_id = ?", (args.photo_id,))
        conn.executemany(
            "INSERT INTO items (photo_id, location_id, name, category, tags, "
            "quantity_estimate, confidence, bbox_x, bbox_y, bbox_w, bbox_h, "
            "notes, categorizer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows)
        conn.execute("UPDATE photos SET status = 'categorized' WHERE id = ?",
                     (args.photo_id,))
    print(f"filed {len(rows)} item(s) for photo {args.photo_id} (categorizer: {args.categorizer})")


if __name__ == "__main__":
    main()
