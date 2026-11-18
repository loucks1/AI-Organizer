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
and photos stay local (gitignored) — a fresh clone or container builds
an empty DB from `schema.sql` on startup.

## Layout

| File | What it is |
|---|---|
| `schema.sql` / `inventory.db` | SQLite store: `locations`, `photos`, `items` (items carry a bounding box as fractions of the photo, so the item can be shown highlighted) |
| `capture.html` | Mobile-friendly capture page: pick a location — or type a new one as `Room / bin-or-drawer` and it's created on upload — snap photo, optional hint, upload |
| `server.py` | Stdlib-only HTTP server (port 8765, `127.0.0.1` unless `INVENTORY_HOST` is set): serves the capture page, accepts uploads into the photos directory, lists pending photos; also `POST /locations` and `POST /photos/<id>/categorization` so a deployment can be populated over HTTP alone |
| `inventory_config.py` | Shared paths (`INVENTORY_DB`, `INVENTORY_PHOTOS`) and schema bootstrap |
| `mcp_server.py` | Stdlib-only MCP server over stdio: `search_inventory`, `list_location`, `get_item`, `check_parts`, `list_pending_photos` |
| `categorize.py` | Files a categorization JSON (from Muse, Grok, or any vision API) into the DB; its validation/filing function is shared with the server's categorization endpoint |
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
python3 server.py                        # capture page at http://127.0.0.1:8765
python3 search.py "torx"                 # CLI search
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 mcp_server.py
```

The first run creates `inventory.db` from `schema.sql` when the file is
missing or is missing a table (starter locations, no items). A database
that already has the tables is not modified. The `sqlite3` CLI is not required.

File a categorization (after Muse / an API returns the JSON):

```sh
python3 categorize.py --photo-id 1 --json categorization.json --categorizer muse
```

Or against a running server, over HTTP — same contract, same validation:

```sh
curl -X POST localhost:8765/locations -d '{"name": "Storage Room"}'
curl -X POST localhost:8765/photos/1/categorization -d @categorization.json
```

`POST /locations` takes `{"name": ..., "parent_id": ...}` (`parent_id`
optional; a duplicate path is a 409). The categorization endpoint takes
the CATEGORIZE.md JSON plus an optional `"categorizer"` field and replies
with how many items were filed.

Environment (defaults are a local checkout; the Docker image overrides them):

| Variable | Local default | In the image |
|---|---|---|
| `INVENTORY_HOST` | `127.0.0.1` | `0.0.0.0` |
| `INVENTORY_PORT` | `8765` | `8765` |
| `INVENTORY_DB` | `inventory.db` next to the scripts | `/data/inventory.db` |
| `INVENTORY_PHOTOS` | `photos/` next to the scripts | `/data/photos` |

## Run in Docker

The image builds from this repo's root, including when Dockhand builds
straight from the public git URL. It is stdlib Python on `python:3.13-slim`,
runs as uid 1000, listens on `0.0.0.0:8765`, and keeps the database and
photos under `/data` so one volume is the whole backup. On a fresh volume
the server loads `schema.sql` (the three starter locations, no items).
An existing database is left alone.

```yaml
services:
  ai-organizer:
    build:
      context: https://github.com/loucks1/AI-Organizer.git#main
    ports:
      - "8765:8765"
    volumes:
      - organizer-data:/data
    restart: unless-stopped

volumes:
  organizer-data:
```

A named volume picks up uid 1000 from the image. A bind mount has to be
writable by that user. There is no login on the capture page; reach it
through the Docker host (LAN or Tailscale) the same way as the other stacks.

The MCP server stays on stdio inside the container:

```sh
docker exec -i <container> python3 mcp_server.py
```

## Not done / open

1. **Hosting** — the image is in this repo. Compose for the home-lab
   Dockhand host lives in `loucks1/DockhandStacks` and builds from the
   public git URL (see above). Tailscale exposure is the host's job,
   same pattern as the Neurio stack.
2. **Provider choice** — Muse-first (no key) is the current setup. A
   Grok/xAI API key (or other vision API) only matters if he wants
   automatic, instant categorization; the JSON contract doesn't change.
3. **Staleness habit** — how items get marked used-up, and re-photos
   superseding a drawer's old items, not yet decided.
4. **No fake inventory** — a fresh DB ships with locations only, zero
   items. Jason's real inventory lives only in his local DB.
