"""
One-time migration: adds the columns required by the Known/Unknown
Identification feature to an existing database that was created via
Base.metadata.create_all() (no Alembic in this project).

Run once, from the backend/ directory, with your venv active:

    cd backend
    python migrate_add_person_review_fields.py

Safe to re-run: every statement checks for column existence first.
"""
from sqlalchemy import create_engine, text
from app.config import settings

STATEMENTS = [
    "ALTER TABLE known_faces ADD COLUMN IF NOT EXISTS company VARCHAR;",
    "ALTER TABLE known_faces ADD COLUMN IF NOT EXISTS branch VARCHAR;",
    "ALTER TABLE known_faces ADD COLUMN IF NOT EXISTS role VARCHAR;",
    "ALTER TABLE face_embeddings ADD COLUMN IF NOT EXISTS added_at TIMESTAMP DEFAULT now();",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS known_face_id INTEGER REFERENCES known_faces(id);",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS confirmed_by VARCHAR;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP;",
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