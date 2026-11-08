"""
One-time migration: adds Unknown-person lifecycle columns (Additional
Unknowns Management + Unknown Deactualization) to an existing database.

Run once, from the backend/ directory, with your venv active:
    cd backend
    python migrate_add_deactualization_fields.py

Safe to re-run: every statement checks for column existence first.
"""
from sqlalchemy import create_engine, text
from app.config import settings

STATEMENTS = [
    "ALTER TABLE unknown_persons ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'active';",
    "ALTER TABLE unknown_persons ADD COLUMN IF NOT EXISTS reverted_from_name VARCHAR;",
]


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        for stmt in STATEMENTS:
            print(f"[migrate] {stmt}")
            conn.execute(text(stmt))
        conn.commit()
    print("[migrate] Done. No existing data was modified or deleted.")


if __name__ == "__main__":
    main()