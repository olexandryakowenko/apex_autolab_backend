"""One SQLite connection per request; explicit write transactions."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from flask import current_app, g

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')

def connect(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.create_function('casefold', 1, lambda value: str(value or '').casefold(), deterministic=True)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    return db

def get_db():
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'])
    return g.db

def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def initialize(path):
    db = connect(path)
    try:
        db.executescript(Path(__file__).with_name('schema.sql').read_text())
        if db.execute('SELECT version FROM meta').fetchone()[0] != 1:
            raise RuntimeError('Unsupported database schema')
    finally:
        db.close()

@contextmanager
def transaction():
    db = get_db()
    db.execute('BEGIN IMMEDIATE')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise

def one(table, ident):
    from .validation import identifier
    identifier(ident)
    # Table identifiers are internal constants, never HTTP input.
    assert table in {'clients','vehicles','orders','attachments'}
    row = get_db().execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone()
    if row is None:
        from .validation import Problem
        raise Problem('not_found', 'Запис не знайдено.', 404)
    return dict(row)
