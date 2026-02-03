from __future__ import annotations

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from src.db.base import Base, DB_SCHEMA

def timestamptz():
    return TIMESTAMP(timezone=True)

class Jobs(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('open','closed','cancelled')", name="jobs_status_chk"),
        {"schema": DB_SCHEMA},
    )

    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")

    import_sessions: Mapped[list["ImportSession"]] = relationship(back_populates="job")


class Operators(Base):
    __tablename__ = "operators"
    __table_args__ = ({"schema": DB_SCHEMA},)

    operator_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())

    import_sessions: Mapped[list["ImportSession"]] = relationship(back_populates="operator")
    deliveries: Mapped[list["ExportDeliveries"]] = relationship(back_populates="operator")


class ImportSession(Base):
    __tablename__ = "import_session"
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','failed')", name="import_session_status_chk"),
        CheckConstraint("session_purpose IN ('initial','retake','rework','other')", name="import_session_purpose_chk"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="import_session_time_chk"),
        Index("idx_import_session_operator_id", "operator_id"),
        Index("idx_import_session_job_id", "job_id"),
        Index("idx_import_session_uut_serial", "uut_serial"),
        {"schema": DB_SCHEMA},
    )

    import_session_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    operator_id: Mapped[str] = mapped_column(
        Text, ForeignKey(f"{DB_SCHEMA}.operators.operator_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey(f"{DB_SCHEMA}.jobs.job_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )

    started_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())
    ended_at: Mapped[object | None] = mapped_column(timestamptz())
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    uut_serial: Mapped[str] = mapped_column(Text, nullable=False)
    session_purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default="initial")

    operator: Mapped["Operators"] = relationship(back_populates="import_sessions")
    job: Mapped["Jobs"] = relationship(back_populates="import_sessions")
    media: Mapped[list["Media"]] = relationship(back_populates="import_session")
    exports: Mapped[list["Exports"]] = relationship(back_populates="import_session")


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        UniqueConstraint("adapter", "vendor_id", name="media_dedupe_uq"),
        Index("idx_media_import_session_id", "import_session_id"),
        Index("idx_media_imported_at", "imported_at"),
        {"schema": DB_SCHEMA},
    )

    media_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    import_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{DB_SCHEMA}.import_session.import_session_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )
    adapter: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_id: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    captured_at: Mapped[object | None] = mapped_column(timestamptz())
    imported_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())
    local_path: Mapped[str] = mapped_column(Text, nullable=False)

    import_session: Mapped["ImportSession"] = relationship(back_populates="media")
    decision: Mapped["Decisions | None"] = relationship(back_populates="media", uselist=False)


class Decisions(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("media_id", name="decisions_one_per_media_uq"),
        CheckConstraint("status IN ('accepted','rejected')", name="decisions_status_chk"),
        {"schema": DB_SCHEMA},
    )

    decision_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{DB_SCHEMA}.media.media_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)

    media: Mapped["Media"] = relationship(back_populates="decision")


class Exports(Base):
    __tablename__ = "exports"
    __table_args__ = (
        CheckConstraint("status IN ('created','archived','ready','failed')", name="exports_status_chk"),
        Index("idx_exports_import_session_id", "import_session_id"),
        {"schema": DB_SCHEMA},
    )

    export_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    import_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{DB_SCHEMA}.import_session.import_session_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )
    export_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="created")
    created_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())

    import_session: Mapped["ImportSession"] = relationship(back_populates="exports")
    local_archive: Mapped["LocalArchives | None"] = relationship(back_populates="export", uselist=False)
    deliveries: Mapped[list["ExportDeliveries"]] = relationship(back_populates="export")


class LocalArchives(Base):
    __tablename__ = "local_archives"
    __table_args__ = (
        UniqueConstraint("export_id", name="local_archives_one_per_export_uq"),
        CheckConstraint("verify_status IN ('pending','verified','failed')", name="local_archives_verify_status_chk"),
        {"schema": DB_SCHEMA},
    )

    archive_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    export_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{DB_SCHEMA}.exports.export_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )
    archive_path: Mapped[str] = mapped_column(Text, nullable=False)
    verify_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())

    export: Mapped["Exports"] = relationship(back_populates="local_archive")


class ExportDeliveries(Base):
    __tablename__ = "export_deliveries"
    __table_args__ = (
        CheckConstraint("result IN ('succeeded','failed')", name="export_deliveries_result_chk"),
        Index("idx_export_deliveries_export_id", "export_id"),
        Index("idx_export_deliveries_delivered_by", "delivered_by"),
        Index("idx_export_deliveries_delivered_at", "delivered_at"),
        {"schema": DB_SCHEMA},
    )

    delivery_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    export_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{DB_SCHEMA}.exports.export_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )
    delivered_by: Mapped[str] = mapped_column(
        Text, ForeignKey(f"{DB_SCHEMA}.operators.operator_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False
    )
    destination_path: Mapped[str] = mapped_column(Text, nullable=False)
    delivered_at: Mapped[object] = mapped_column(timestamptz(), nullable=False, server_default=func.now())
    result: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    export: Mapped["Exports"] = relationship(back_populates="deliveries")
    operator: Mapped["Operators"] = relationship(back_populates="deliveries")
