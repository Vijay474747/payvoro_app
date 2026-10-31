"""
Database connection for Payvoro.

- On Vercel (live): Neon Postgres. Vercel's Neon integration sets DATABASE_URL (or POSTGRES_URL) by itself.
- On your PC (testing): a SQLite file (PAYVORO_DB, default payvoro.db). No setup needed.

core.py writes SQL once with "?" placeholders. This file changes it for Postgres.
"""
import os
import re
import sqlite3
from contextlib import contextmanager


def database_url() -> str:
    for k in ("DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL"):
        v = (os.getenv(k) or "").strip()
        if v.startswith(("postgres://", "postgresql://")):
            return v
    return ""


def is_postgres() -> bool:
    return bool(database_url())


def on_vercel() -> bool:
    return os.getenv("VERCEL") == "1"


def sqlite_path(default: str) -> str:
    # Vercel's disk is read-only except /tmp (and /tmp is wiped often). Only used if no database is connected.
    if on_vercel() and not os.path.isabs(default):
        return os.path.join("/tmp", os.path.basename(default))
    return default


class Row(dict):
    """A dict row that also allows row[0], like sqlite3.Row."""

    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return super().__getitem__(k)


def _pg_row_factory(cursor):
    names = [d.name for d in cursor.description] if cursor.description else []

    def make(values):
        return Row(zip(names, values))
    return make


class Conn:
    """Same small interface for SQLite and Postgres: execute(), insert()."""

    def __init__(self, raw, pg: bool):
        self.raw = raw
        self.pg = pg

    def execute(self, sql: str, args=()):
        if self.pg:
            sql = sql.replace("%", "%%").replace("?", "%s")
        return self.raw.execute(sql, tuple(args))

    def insert(self, sql: str, args=()) -> int:
        """INSERT ... and return the new row id."""
        return int(self.execute(sql + " RETURNING id", args).fetchone()["id"])

    def executescript(self, script: str):
        for stmt in [s.strip() for s in script.split(";")]:
            if stmt:
                self.execute(stmt)


@contextmanager
def connect(sqlite_file: str):
    url = database_url()
    if url:
        import psycopg
        raw = psycopg.connect(url, row_factory=_pg_row_factory, prepare_threshold=None, connect_timeout=10)
        try:
            yield Conn(raw, True)
            raw.commit()
        finally:
            raw.close()          # not committed = rolled back
    else:
        raw = sqlite3.connect(sqlite_path(sqlite_file))
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        try:
            yield Conn(raw, False)
            raw.commit()
        finally:
            raw.close()


def to_postgres_schema(sqlite_schema: str) -> str:
    """Times are stored in milliseconds, which need BIGINT in Postgres."""
    s = re.sub(r"\bINTEGER PRIMARY KEY\b", "BIGSERIAL PRIMARY KEY", sqlite_schema)
    s = re.sub(r"\bINTEGER\b", "BIGINT", s)
    s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)
    return s
