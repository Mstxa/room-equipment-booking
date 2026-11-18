import os

import psycopg
from pwdlib import PasswordHash

DEMO_USERS = (
    ("alice@example.com", "DemoAlice123!"),
    ("bob@example.com", "DemoBob123!"),
)

DEMO_RESOURCES = (
    ("ห้องประชุมใหญ่", "room"),
    ("ห้องประชุมเล็ก", "room"),
    ("โปรเจกเตอร์", "equipment"),
)


def seed_demo_data():
    password_hash = PasswordHash.recommended()

    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as conn:
        for email, password in DEMO_USERS:
            conn.execute(
                """
                INSERT INTO users (email, password_hash)
                VALUES (%s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (email, password_hash.hash(password)),
            )

        for name, resource_type in DEMO_RESOURCES:
            conn.execute(
                """
                INSERT INTO resources (name, type)
                VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (name, resource_type),
            )

    print("Demo data ready.", flush=True)


if __name__ == "__main__":
    seed_demo_data()