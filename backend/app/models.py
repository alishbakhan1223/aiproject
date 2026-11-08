from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from datetime import datetime

from app.database import Base

# InsightFace 'buffalo_l' produces 512-d embeddings
EMBEDDING_DIM = 512


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # admin | user
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class KnownFace(Base):
    __tablename__ = "known_faces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    photo_path = Column(String, nullable=True)  # cover/highest-quality photo
    # Profile fields (CCTV Known/Unknown Identification spec, Section 2)
    company = Column(String, nullable=True)
    branch = Column(String, nullable=True)
    role = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # one person can have MULTIPLE embeddings (multi-photo registration)
    embeddings = relationship(
        "FaceEmbedding", back_populates="face", cascade="all, delete-orphan"
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    face_id = Column(Integer, ForeignKey("known_faces.id"))
    vector = Column(Vector(EMBEDDING_DIM))
    photo_path = Column(String, nullable=True)
    quality_score = Column(Float, nullable=True)  # computed face quality / sharpness score
    source_unknown_id = Column(Integer, nullable=True)  # original unknown_person.id if promoted
    # Insertion timestamp — required for FIFO reference-image replacement
    # (Known/Unknown Identification spec, Section 7: FIFO must be based on
    # stored insertion timestamp, not filename).
    added_at = Column(DateTime, default=datetime.utcnow)

    face = relationship("KnownFace", back_populates="embeddings")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)  # rtsp url / device index / video file
    is_active = Column(Boolean, default=False)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), unique=True)
    # polygon stored as JSON string: "[[x1,y1],[x2,y2],...]" in source-frame pixel coords
    polygon = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String)
    # "unknown_person" | "known_person" | "restricted_object" | "forensic_confirmation"
    camera_name = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    snapshot_path = Column(String, nullable=True)
    person_name = Column(String, nullable=True)
    is_unknown = Column(Boolean, default=False)
    object_name = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    in_zone = Column(Boolean, nullable=True)  # True=inside, False=outside, None=zone off

    # Known/Unknown identification workflow (manual "Make Known" confirmation)
    known_face_id = Column(Integer, ForeignKey("known_faces.id"), nullable=True)
    confirmed_by = Column(String, nullable=True)   # operator username
    confirmed_at = Column(DateTime, nullable=True)


class UnknownPerson(Base):
    __tablename__ = "unknown_persons"

    id = Column(Integer, primary_key=True, index=True)
    reference_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    representative_snapshot_path = Column(String, nullable=True)
    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    # "active" -> currently/recently seen (shows in live Unknowns list)
    # "inactive" -> deactualized (left camera view) — history stays, just hidden
    status = Column(String, nullable=False, default="active")
    # Set only when this identity was created by reverting a KnownFace
    # back to unknown, so we can tell it apart from a brand-new unknown.
    reverted_from_name = Column(String, nullable=True)

    embeddings = relationship(
        "UnknownEmbedding",
        back_populates="unknown_person",
        cascade="all, delete-orphan",
        order_by="UnknownEmbedding.id",
    )
    sightings = relationship(
        "UnknownSighting",
        back_populates="unknown_person",
        cascade="all, delete-orphan",
        order_by="UnknownSighting.id",
    )


class UnknownEmbedding(Base):
    __tablename__ = "unknown_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    unknown_person_id = Column(Integer, ForeignKey("unknown_persons.id"))
    vector = Column(Vector(EMBEDDING_DIM), nullable=True)
    snapshot_path = Column(String, nullable=True)
    quality_score = Column(Float, nullable=True)  # computed face quality / sharpness score
    created_at = Column(DateTime, nullable=True)

    unknown_person = relationship("UnknownPerson", back_populates="embeddings")


class UnknownSighting(Base):
    __tablename__ = "unknown_sightings"

    id = Column(Integer, primary_key=True, index=True)
    unknown_person_id = Column(Integer, ForeignKey("unknown_persons.id"))
    camera_name = Column(String, nullable=False)
    snapshot_path = Column(String, nullable=True)
    quality_score = Column(Float, nullable=True)  # computed face quality / sharpness score
    timestamp = Column(DateTime, nullable=True)

    unknown_person = relationship("UnknownPerson", back_populates="sightings")