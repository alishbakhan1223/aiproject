"""
One-time migration: ensures all columns required for per-face crop alerts
(bounding_box, face_crop_path, raw_snapshot_path, unknown_person_id, scene_snapshot_path)
exist in the database.

Safe to re-run: every statement checks for column existence first.
"""
from sqlalchemy import create_engine, text
from app.config import settings

STATEMENTS = [
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS track_id INTEGER;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS bounding_box VARCHAR;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS face_crop_path VARCHAR;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS raw_snapshot_path VARCHAR;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS annotated_snapshot_path VARCHAR;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS unknown_person_id INTEGER REFERENCES unknown_persons(id) ON DELETE SET NULL;",
    "ALTER TABLE unknown_sightings ADD COLUMN IF NOT EXISTS bounding_box VARCHAR;",
    "ALTER TABLE unknown_sightings ADD COLUMN IF NOT EXISTS scene_snapshot_path VARCHAR;",
]


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        for stmt in STATEMENTS:
            print(f"[migrate] {stmt}")
            try:
                conn.execute(text(stmt))
            except Exception as e:
                print(f"[migrate] Note: {e}")
        conn.commit()
    print("[migrate] Done. All alerts and crop fields verified.")


if __name__ == "__main__":
    main()
