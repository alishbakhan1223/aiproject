"""
One-time migration: adds quality_score column to face_embeddings,
unknown_embeddings, and unknown_sightings tables.

Run once, from the backend/ directory, with your venv active:
    cd backend
    python migrate_add_quality_score.py

Safe to re-run: checks for column existence first.
"""
from sqlalchemy import create_engine, text
from app.config import settings

STATEMENTS = [
    "ALTER TABLE face_embeddings ADD COLUMN IF NOT EXISTS quality_score FLOAT;",
    "ALTER TABLE unknown_embeddings ADD COLUMN IF NOT EXISTS quality_score FLOAT;",
    "ALTER TABLE unknown_sightings ADD COLUMN IF NOT EXISTS quality_score FLOAT;",
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
