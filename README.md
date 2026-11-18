# Drawer / parts inventory — prototype

**Idea (Jason, 2026-11-18):** a database of what's in his drawers, built
primarily as a store for AI to see — not for him to browse. The payoff is
Muse saying "go get this part" and showing him the photo of it, with the
item marked, plus where it lives (garage → cabinet → drawer).

**Status (2026-11-18): working prototype. Calibration test PASSED** —
Muse as categorizer itemized three real photos (boxed/labeled items to
model level; loose bulk as type + rough quantity; unidentifiable items
flagged, never invented). First real entries filed locally: 37 items
across 3 photos in 2 locations. Muse is the categorizer for now (no API
key). Published to the lab as `loucks1/AI-Organizer`; the live database
and photos stay local (gitignored) — a fresh clone builds an empty DB
from `schema.sql`.

## Layout

| File | What it is |
|---|---|
| `schema.sql` / `inventory.db` | SQLite store: `locations`, `photos`, `items` (items carry a bounding box as fractions of the photo, so the item can be shown highlighted) |
| `capture.html` | Mobile-friendly capture page: pick location, snap photo, optional hint, upload |
| `server.py` | Stdlib-only HTTP server (port 8765): serves the capture page, accepts uploads into `photos/`, lists pending photos |
| `mcp_server.py` | Stdlib-only MCP server over stdio: `search_inventory`, `list_location`, `get_item`, `check_parts`, `list_pending_photos` |
| `categorize.py` | Files a categorization JSON (from Muse, Grok, or any vision API) into the DB |
| `search.py` | Quick CLI search, for smoke tests |
| `CATEGORIZE.md` | The exact JSON contract + prompt any categorizer must return |

## Design decisions (from the 2026-11-18 chat)

- **SQLite + image files on disk.** A file Muse can query directly, trivial
  to back up, no service lock-in. Under the MCP layer it's just a REST-ish
  API + the SQLite file, so nothing depends on MCP surviving as a fad.
- **The original photo is the asset; categorization is just an index.**
  Re-running categorization later rewrites `items` only — originals are
  never thrown away or tagged in place.
- **Categorizer is provider-pluggable.** The JSON contract in
  `CATEGORIZE.md` is the same whether the caller is Muse (in chat, no key),
  Grok via the xAI API, or another vision API. `items.categorizer` records
  who filed each row.
- **Muse-first to start.** No API key needed: photos sent in chat get
  categorized by Muse and filed with `categorize.py`. If Jason later wants
  photos searchable the second they're taken, plug an API key into the
  same slot — the index format doesn't change.
- **Known weak spot, no provider fixes it:** reading screw sizes, thread
  pitch, resistor values, or exact counts out of a jumbled drawer photo.
  The capture hint ("left bin is M5 bolts, ~30") is the cheap fix — Muse
  files it under Jason's label instead of guessing.

## Run it (local prototype only)

```sh
cd <repo clone>
sqlite3 inventory.db < schema.sql        # creates DB + starter locations
python3 server.py                        # capture page at http://localhost:8765
python3 search.py "torx"                 # CLI search
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 mcp_server.py
```

File a categorization (after Muse / an API returns the JSON):

```sh
python3 categorize.py --photo-id 1 --json categorization.json --categorizer muse
```

Environment: `INVENTORY_DB` overrides the DB path (default
`inventory.db` next to the scripts); `INVENTORY_PORT` overrides 8765.

## Not done / open

1. **Hosting** — Docker on Jason's home network, reachable over Tailscale,
   same pattern as the Neurio stack. Not started; prototype runs locally.
2. **Provider choice** — Muse-first (no key) is the current setup. A
   Grok/xAI API key (or other vision API) only matters if he wants
   automatic, instant categorization; the JSON contract doesn't change.
3. **Staleness habit** — how items get marked used-up, and re-photos
   superseding a drawer's old items, not yet decided.
4. **No fake inventory** — a fresh DB ships with locations only, zero
   items. Jason's real inventory lives only in his local DB.
