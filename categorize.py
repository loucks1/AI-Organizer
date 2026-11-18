#!/usr/bin/env python3
"""File a categorization JSON into the drawer inventory DB.

Usage:
  python3 categorize.py --photo-id 1 --json categorization.json --categorizer muse
Validates the contract in CATEGORIZE.md (bbox 0–1, confidence 0–1), inserts
one item row per entry, marks the photo 'categorized'. Re-running for a
photo replaces its items; the original photo file is never touched.
Env: INVENTORY_DB (default inventory.db next to this file)
The database is created from schema.sql when it is missing or is missing a table.

The validation and filing live in file_categorization() so the capture
server's POST /photos/<id>/categorization endpoint files items exactly
the same way this CLI does.
"""
import argparse
import json
import sys

from inventory_config import connect, ensure_db


class CategorizationError(ValueError):
    """A categorization payload that violates the CATEGORIZE.md contract."""


def validated_rows(items, photo_id, location_id, categorizer):
    """Validate items against the contract; return INSERT-ready rows."""
    if not isinstance(items, list):
        raise CategorizationError("JSON must have an 'items' array (see CATEGORIZE.md)")
    rows = []
    for i, it in enumerate(items):
        name = (it.get("name") or "").strip()
        if not name:
            raise CategorizationError(f"item {i}: missing name")
        bbox = it.get("bbox") or [None, None, None, None]
        if len(bbox) != 4 or any(v is not None and not (0 <= v <= 1) for v in bbox):
            raise CategorizationError(
                f"item {i} ({name}): bbox must be [x, y, w, h] fractions in 0–1")
        conf = it.get("confidence")
        if conf is not None and not (0 <= conf <= 1):
            raise CategorizationError(f"item {i} ({name}): confidence must be 0–1")
        rows.append((photo_id, location_id, name,
                     it.get("category"),
                     json.dumps(it.get("tags") or []),
                     it.get("quantity_estimate"),
                     conf, bbox[0], bbox[1], bbox[2], bbox[3],
                     it.get("notes"), categorizer))
    return rows


def file_categorization(conn, photo_id, items, categorizer="muse"):
    """Replace a photo's items with a validated categorization.

    Returns the number of items filed and marks the photo 'categorized'.
    Raises CategorizationError for an unknown photo or a bad payload.
    Runs inside the caller's transaction — the caller wraps the call in
    `with conn:` so the delete/insert/update commit or roll back together.
    (The connection class closes on context exit, so this function must
    not open a transaction block of its own inside a caller's block.)
    """
    photo = conn.execute("SELECT id, location_id FROM photos WHERE id = ?",
                         (photo_id,)).fetchone()
    if photo is None:
        raise CategorizationError(f"no photo with id {photo_id}")
    rows = validated_rows(items, photo_id, photo["location_id"], categorizer)
    conn.execute("DELETE FROM items WHERE photo_id = ?", (photo_id,))
    conn.executemany(
        "INSERT INTO items (photo_id, location_id, name, category, tags, "
        "quantity_estimate, confidence, bbox_x, bbox_y, bbox_w, bbox_h, "
        "notes, categorizer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows)
    conn.execute("UPDATE photos SET status = 'categorized' WHERE id = ?",
                 (photo_id,))
    return len(rows)


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

    ensure_db()
    conn = connect()
    try:
        with conn:
            filed = file_categorization(conn, args.photo_id, data.get("items"),
                                        args.categorizer)
    except CategorizationError as e:
        fail(str(e))
    print(f"filed {filed} item(s) for photo {args.photo_id} "
          f"(categorizer: {args.categorizer})")


if __name__ == "__main__":
    main()
