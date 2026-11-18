#!/usr/bin/env python3
"""Drawer inventory — capture server (Python stdlib only).

Serves capture.html, accepts photo uploads into the photos directory,
records them in the SQLite DB as status='pending' for categorization.
Also accepts the writes an AI categorizer needs so a deployment can be
populated over HTTP alone: POST /locations creates a location, and
POST /photos/<id>/categorization files a categorization (the JSON
contract in CATEGORIZE.md, same validation as categorize.py). An upload
may name its location as location_path text ("Room / bin-or-drawer")
instead of a location_id; missing tiers are created on the spot.
Run:  python3 server.py        # http://127.0.0.1:8765
Env:  INVENTORY_HOST (default 127.0.0.1), INVENTORY_PORT (default 8765),
      INVENTORY_DB (default inventory.db), INVENTORY_PHOTOS (default photos/)
The database is created from schema.sql on startup when it is missing
or is missing a table. An existing database is left as it is.
"""
import json
import os
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from categorize import CategorizationError, file_categorization
from inventory_config import connect, db_path, ensure_db, listen_host, listen_port, photos_dir

HERE = os.path.dirname(os.path.abspath(__file__))


def db():
    return connect()


def ensure_location_path(conn, raw):
    """Resolve 'Tier 1 / Tier 2' text to a location, creating tiers.

    Locations are two-tier by convention (a Home Assistant area, then a
    bin/drawer/furniture piece), so the text must be one or two non-empty
    segments. Returns (location_id, path); raises ValueError with a
    user-facing message otherwise. Runs in the caller's transaction.
    """
    segments = [s.strip() for s in (raw or "").split("/")]
    segments = [s for s in segments if s]
    if not segments or len(segments) > 2:
        raise ValueError("location must be 'Room' or 'Room / bin-or-drawer'")
    parent_id = None
    path = None
    location_id = None
    for seg in segments:
        path = seg if parent_id is None else f"{path} / {seg}"
        row = conn.execute("SELECT id FROM locations WHERE path = ?",
                           (path,)).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO locations (name, parent_id, path) VALUES (?, ?, ?)",
                (seg, parent_id, path))
            location_id = cur.lastrowid
        else:
            location_id = row["id"]
        parent_id = location_id
    return location_id, path


def parse_multipart(body, boundary):
    """Minimal multipart/form-data parser. Returns {field: value} where a
    file field is (filename, bytes) and a text field is str."""
    parts = {}
    for chunk in body.split(b"--" + boundary):
        if not chunk.strip() or chunk.strip() == b"--":
            continue
        head, _, payload = chunk.partition(b"\r\n\r\n")
        if not payload:
            continue
        payload = payload.rstrip(b"\r\n")
        headers = head.decode("latin-1", "replace")
        name = None
        filename = None
        for line in headers.split("\r\n"):
            if "Content-Disposition" in line:
                for seg in line.split(";"):
                    seg = seg.strip()
                    if seg.startswith("name="):
                        name = seg[5:].strip('"')
                    elif seg.startswith("filename="):
                        filename = seg[9:].strip('"')
        if name is None:
            continue
        parts[name] = (filename, payload) if filename else payload.decode("utf-8", "replace")
    return parts


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep stdout clean

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            try:
                with db() as conn:
                    conn.execute("SELECT COUNT(*) FROM locations").fetchone()
            except sqlite3.Error:
                self._send_json({"ok": False}, 503)
                return
            self._send_json({"ok": True})
        elif parsed.path == "/":
            with open(os.path.join(HERE, "capture.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/locations":
            with db() as conn:
                rows = conn.execute("SELECT id, path FROM locations ORDER BY path").fetchall()
            self._send_json([dict(r) for r in rows])
        elif parsed.path == "/photos":
            with db() as conn:
                rows = conn.execute(
                    "SELECT p.id, p.filename, p.hint, p.status, l.path AS location "
                    "FROM photos p JOIN locations l ON l.id = p.location_id "
                    "ORDER BY p.id DESC LIMIT 50").fetchall()
            self._send_json([dict(r) for r in rows])
        elif parsed.path.startswith("/photo/"):
            filename = os.path.basename(parsed.path[len("/photo/"):])
            path = os.path.join(photos_dir(), filename)
            if not os.path.isfile(path):
                self.send_error(404, "no such photo")
                return
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def _read_json(self):
        """Parse the request body as JSON. On failure, sends a 400 and
        returns None."""
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._send_json({"error": "expected a JSON body"}, 400)
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self._send_json({"error": "body is not valid JSON"}, 400)
            return None

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/upload":
            self._handle_upload()
        elif path == "/locations":
            self._handle_create_location()
        elif path.startswith("/photos/") and path.endswith("/categorization"):
            self._handle_categorization(path)
        else:
            self.send_error(404)

    def _handle_create_location(self):
        data = self._read_json()
        if data is None:
            return
        name = (data.get("name") or "").strip()
        if not name:
            self._send_json({"error": "name is required"}, 400)
            return
        if "/" in name:
            self._send_json({"error": "name must not contain '/'"}, 400)
            return
        parent_id = data.get("parent_id")
        with db() as conn:
            if parent_id is None:
                path = name
            else:
                parent = conn.execute("SELECT path FROM locations WHERE id = ?",
                                      (parent_id,)).fetchone()
                if parent is None:
                    self._send_json({"error": f"no location with id {parent_id}"}, 400)
                    return
                path = f"{parent['path']} / {name}"
            try:
                cur = conn.execute(
                    "INSERT INTO locations (name, parent_id, path) VALUES (?, ?, ?)",
                    (name, parent_id, path))
            except sqlite3.IntegrityError:
                self._send_json({"error": f"location already exists: {path}"}, 409)
                return
            location_id = cur.lastrowid
        self._send_json({"id": location_id, "name": name,
                         "parent_id": parent_id, "path": path}, 201)

    def _handle_categorization(self, path):
        try:
            photo_id = int(path[len("/photos/"):-len("/categorization")].strip("/"))
        except ValueError:
            self.send_error(404)
            return
        data = self._read_json()
        if data is None:
            return
        categorizer = data.get("categorizer") or "muse"
        with db() as conn:
            try:
                filed = file_categorization(conn, photo_id, data.get("items"),
                                            categorizer)
            except CategorizationError as e:
                status = 404 if str(e).startswith("no photo with id") else 400
                self._send_json({"error": str(e)}, status)
                return
        self._send_json({"photo_id": photo_id, "filed": filed,
                         "status": "categorized", "categorizer": categorizer})

    def _handle_upload(self):
        length = int(self.headers.get("Content-Length", 0))
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype or length <= 0:
            self._send_json({"error": "expected multipart/form-data upload"}, 400)
            return
        boundary = ctype.split("boundary=")[-1].encode()
        parts = parse_multipart(self.rfile.read(length), boundary)
        if "photo" not in parts or not isinstance(parts["photo"], tuple):
            self._send_json({"error": "no photo file in upload"}, 400)
            return
        filename, data = parts["photo"]
        ext = os.path.splitext(filename or "")[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".heic", ".webp"):
            ext = ".jpg"
        stored = f"{uuid.uuid4().hex[:12]}{ext}"
        stored_path = os.path.join(photos_dir(), stored)
        os.makedirs(photos_dir(), exist_ok=True)
        with open(stored_path, "wb") as f:
            f.write(data)
        hint = parts.get("hint", "") or None
        location_path = (parts.get("location_path") or "").strip()
        try:
            with db() as conn:
                if location_path:
                    location_id, path = ensure_location_path(conn, location_path)
                else:
                    try:
                        location_id = int(parts.get("location_id", 3))
                    except (TypeError, ValueError):
                        raise ValueError("location_id must be a number")
                    loc = conn.execute("SELECT path FROM locations WHERE id = ?",
                                       (location_id,)).fetchone()
                    if loc is None:
                        raise ValueError(f"no location with id {location_id}")
                    path = loc["path"]
                cur = conn.execute(
                    "INSERT INTO photos (location_id, filename, hint, status) "
                    "VALUES (?, ?, ?, 'pending')", (location_id, stored, hint))
                photo_id = cur.lastrowid
        except ValueError as e:
            os.remove(stored_path)  # don't orphan the file on a bad request
            self._send_json({"error": str(e)}, 400)
            return
        self._send_json({"photo_id": photo_id, "filename": stored,
                         "location": path, "status": "pending"})


if __name__ == "__main__":
    ensure_db()
    host, port = listen_host(), listen_port()
    print(f"drawer-inventory capture server on http://{host}:{port} "
          f"(db: {db_path()}, photos: {photos_dir()})", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
