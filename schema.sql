-- Drawer / parts inventory — SQLite schema
-- The photo is the asset; categorization is just an index over it.
-- Re-running categorization later only rewrites `items`, never the photos.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    parent_id  INTEGER REFERENCES locations(id),
    -- Human path, e.g. "Garage / Parts cabinet / Drawer 3"
    path       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    filename    TEXT NOT NULL,          -- file under photos/
    hint        TEXT,                   -- capture hint, e.g. "left bin is M4 screws"
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','categorized')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id           INTEGER NOT NULL REFERENCES photos(id),
    location_id        INTEGER NOT NULL REFERENCES locations(id),
    name               TEXT NOT NULL,
    category           TEXT,
    tags               TEXT,            -- JSON array of strings
    quantity_estimate  TEXT,            -- e.g. "~30", "1", "a handful" — never pretend precision
    confidence         REAL,            -- 0.0–1.0, from the categorizer
    -- Bounding box as fractions of the photo (0–1), so Muse can show
    -- the item highlighted/cropped: "go get this, it's here in the photo".
    bbox_x             REAL,
    bbox_y             REAL,
    bbox_w             REAL,
    bbox_h             REAL,
    notes              TEXT,
    categorizer        TEXT,            -- 'muse' | 'grok' | 'gemini' | ... — who filed it
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_items_name     ON items(name);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_location ON items(location_id);
CREATE INDEX IF NOT EXISTS idx_photos_status  ON photos(status);

-- Starter location tree. Add more with:
--   INSERT INTO locations (name, parent_id, path) VALUES ('Drawer 4', 2, 'Garage / Parts cabinet / Drawer 4');
INSERT OR IGNORE INTO locations (id, name, parent_id, path) VALUES
  (1, 'Garage',        NULL, 'Garage'),
  (2, 'Parts cabinet', 1,    'Garage / Parts cabinet'),
  (3, 'Drawer 3',      2,    'Garage / Parts cabinet / Drawer 3');
