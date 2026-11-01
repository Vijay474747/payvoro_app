"""
Copy your old SQLite data (payvoro.db) into Neon Postgres. Run once on your PC:

    pip install "psycopg[binary]"
    DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" python migrate_sqlite_to_postgres.py payvoro.db

Safe to run on an empty Neon database. Rows that already exist are skipped.
"""
import sqlite3
import sys

import core
import database

TABLES = ["merchants", "sessions", "events", "payments", "plan_settings", "rzp_plans", "subscriptions"]
KEYS = {"sessions": "token_hash", "events": "id", "plan_settings": "plan_id", "rzp_plans": "rzp_plan_id"}


def main(path: str):
    if not database.is_postgres():
        sys.exit("Set DATABASE_URL to your Neon Postgres URL first")
    old_path, core.DB_PATH = core.DB_PATH, path
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    core.init_db()                              # makes the tables in Postgres
    with core.db() as c:
        for t in TABLES:
            try:
                rows = src.execute(f"SELECT * FROM {t}").fetchall()
            except sqlite3.OperationalError:
                continue                        # table not in the old file
            if not rows:
                continue
            pg_cols = {r["column_name"] for r in c.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=?", (t,)).fetchall()}
            cols = [k for k in rows[0].keys() if k in pg_cols]
            sql = (f"INSERT INTO {t}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
                   f" ON CONFLICT({KEYS.get(t, 'id')}) DO NOTHING")
            for r in rows:
                c.execute(sql, [r[k] for k in cols])
            if "id" in cols:                    # next new id continues after the copied ones
                c.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT COALESCE(MAX(id), 1) FROM {t}))")
            print(f"{t}: {len(rows)} rows")
    core.DB_PATH = old_path
    print("Done")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "payvoro.db")
