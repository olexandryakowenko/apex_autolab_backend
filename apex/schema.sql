PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta (version INTEGER NOT NULL);
INSERT INTO meta SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM meta);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (address TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
CREATE TABLE IF NOT EXISTS clients (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicles (
 id INTEGER PRIMARY KEY, plate_original TEXT NOT NULL, plate TEXT NOT NULL UNIQUE,
 vin TEXT, make TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
 client_id INTEGER REFERENCES clients(id) ON DELETE RESTRICT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL UNIQUE,
 vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
 client_id INTEGER REFERENCES clients(id) ON DELETE RESTRICT,
 plate_snapshot TEXT NOT NULL, client_name TEXT, client_phone TEXT,
 description TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','ready','in_progress','completed','cancelled')),
 confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 CHECK(status NOT IN ('ready','in_progress','completed') OR
 (client_id IS NOT NULL AND length(trim(COALESCE(client_name,'')))>0 AND length(COALESCE(client_phone,''))>=7 AND length(trim(description))>0 AND confirmed=1))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_order ON orders(vehicle_id)
 WHERE status IN ('draft','ready','in_progress');
CREATE INDEX IF NOT EXISTS orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS orders_vehicle ON orders(vehicle_id);
CREATE INDEX IF NOT EXISTS clients_phone ON clients(phone);
CREATE INDEX IF NOT EXISTS vehicles_vin ON vehicles(vin);
CREATE TABLE IF NOT EXISTS status_history (
 id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
 previous_status TEXT, new_status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments (
 id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
 filename TEXT NOT NULL UNIQUE, mime_type TEXT NOT NULL, bytes INTEGER NOT NULL, created_at TEXT NOT NULL
);
