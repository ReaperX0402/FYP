from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import Decisions

def upsert_decision(
        db: Session, 
        *, 
        media_id: int, 
        status: str,  
        reason: str | None = None, 
        notes: str | None = None) -> Decisions:
    
    row = Decisions(
        media_id=media_id,
        status=status,
        reason=reason,
        notes=notes,
    )

    db.add(row)

    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Decisions).where(Decisions.media_id == media_id))
        if existing is None:
            raise 
        existing.status = status
        existing.reason = reason
        existing.notes = notes
        db.commit()
        db.refresh(existing)
        return existing


    