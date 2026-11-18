import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def run_migrations():
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (481752,))

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        applied_files = {
            filename
            for (filename,) in conn.execute("SELECT filename FROM schema_migrations")
        }

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied_files:
                continue

            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)",
                (path.name,),
            )
            print(f"Applied migration: {path.name}", flush=True)


if __name__ == "__main__":
    run_migrations()