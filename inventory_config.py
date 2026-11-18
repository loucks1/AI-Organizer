#!/usr/bin/env python3
"""Shared paths and SQLite bootstrap for the drawer inventory tools.

Local defaults match a checkout: bind 127.0.0.1, port 8765, inventory.db
and photos/ next to these scripts. The container image overrides the
environment so the server is reachable and both the database and photos
live under /data.

Env:
  INVENTORY_HOST    bind address (default 127.0.0.1)
  INVENTORY_PORT    listen port (default 8765)
  INVENTORY_DB      SQLite file (default inventory.db next to these scripts)
  INVENTORY_PHOTOS  directory photo files are stored in (default photos/)
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")
REQUIRED_TABLES = ("locations", "photos", "items")


def db_path():
    return os.environ.get("INVENTORY_DB", os.path.join(HERE, "inventory.db"))


def photos_dir():
    return os.environ.get("INVENTORY_PHOTOS", os.path.join(HERE, "photos"))


def listen_host():
    return os.environ.get("INVENTORY_HOST", "127.0.0.1")


def listen_port():
    return int(os.environ.get("INVENTORY_PORT", "8765"))


class _ClosingConnection(sqlite3.Connection):
    """Commit or roll back like a normal connection, then close it.

    The server handles one connection per request. Closing here keeps a
    long-running container from leaking file descriptors.
    """

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def connect():
    conn = sqlite3.connect(db_path(), factory=_ClosingConnection)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db():
    """Create the DB from schema.sql when it is missing or lacks tables.

    Safe to call on every startup. When locations, photos, and items
    already exist, the schema is not applied and no rows are changed.
    """
    path = db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    os.makedirs(photos_dir(), exist_ok=True)

    new_file = not os.path.exists(path)
    conn = sqlite3.connect(path)
    try:
        if not new_file:
            found = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name IN (?, ?, ?)",
                    REQUIRED_TABLES,
                )
            }
            if found == set(REQUIRED_TABLES):
                return
        if not os.path.isfile(SCHEMA_PATH):
            raise FileNotFoundError(f"schema not found: {SCHEMA_PATH}")
        with open(SCHEMA_PATH, encoding="utf-8") as schema:
            conn.executescript(schema.read())
    finally:
        conn.close()
