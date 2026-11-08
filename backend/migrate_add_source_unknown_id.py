"""
One-time migration: adds source_unknown_id column to face_embeddings
to track which UnknownPerson identity a promoted photo originally came from.

Run once, from the backend/ directory, with your venv active:
    cd backend
    python migrate_add_source_unknown_id.py

Safe to re-run: checks for column existence first.
"""
from sqlalchemy import create_engine, text
from app.config import settings

STATEMENTS = [
    "ALTER TABLE face_embeddings ADD COLUMN IF NOT EXISTS source_unknown_id INTEGER;",
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
