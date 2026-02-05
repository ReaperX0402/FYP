from __future__ import annotations 

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import Media

def insert_media_idempotent(
  db: Session,
    *,
    import_session_id: int,
    adapter: str,
    vendor_id: str,
    filename: str | None,
    size_bytes: int,
    captured_at,
    local_path: str,
) -> tuple[Media, bool]:
    
    row = Media(
        import_session_id=import_session_id,
        adapter=adapter,
        vendor_id=vendor_id,
        filename=filename,
        size_bytes=size_bytes,
        captured_at=captured_at,
        local_path=local_path,
    )

    db.add(row)

    try:
        db.commit()
        db.refresh(row)
        return row, True
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(Media).where(Media.adapter == adapter, Media.vendor_id == vendor_id)
        ).scalar_one()
        return existing, False