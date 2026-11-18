#!/usr/bin/env python3
"""Drawer inventory — capture server (Python stdlib only).

Serves capture.html, accepts photo uploads into the photos directory,
records them in the SQLite DB as status='pending' for categorization.
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

from inventory_config import connect, db_path, ensure_db, listen_host, listen_port, photos_dir

HERE = os.path.dirname(os.path.abspath(__file__))


def db():
    return connect()


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

    def do_POST(self):
        if urlparse(self.path).path != "/upload":
            self.send_error(404)
            return
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
        os.makedirs(photos_dir(), exist_ok=True)
        with open(os.path.join(photos_dir(), stored), "wb") as f:
            f.write(data)
        location_id = int(parts.get("location_id", 3))
        hint = parts.get("hint", "") or None
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO photos (location_id, filename, hint, status) "
                "VALUES (?, ?, ?, 'pending')", (location_id, stored, hint))
            photo_id = cur.lastrowid
            loc = conn.execute("SELECT path FROM locations WHERE id = ?",
                               (location_id,)).fetchone()
        self._send_json({"photo_id": photo_id, "filename": stored,
                         "location": loc["path"] if loc else None,
                         "status": "pending"})


if __name__ == "__main__":
    ensure_db()
    host, port = listen_host(), listen_port()
    print(f"drawer-inventory capture server on http://{host}:{port} "
          f"(db: {db_path()}, photos: {photos_dir()})", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
