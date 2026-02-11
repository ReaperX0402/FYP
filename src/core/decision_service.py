from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Media, ImportSession
from src.db.repo_decisions import upsert_decision

class DecisionServiceError(Exception):
    pass

@dataclass(frozen=True)
class MediaDecisionView:
    media_id: int
    local_path: str
    captured_at: object | None
    decision_status: str | None
    decision_reason: str | None
    decision_notes: str | None

class DecisionService:
    VALID = {"accepted", "rejected"}

    @staticmethod
    def list_media_for_session(db: Session, import_session_id: int) -> list[MediaDecisionView]:
        rows = db.scalars(
            select(Media)
            .where(Media.import_session_id == import_session_id)
            .order_by(Media.media_id.asc())
        ).all()

        out: list[MediaDecisionView] = []
        for m in rows:
            d = m.decision
            out.append(
                MediaDecisionView(
                    media_id=m.media_id,
                    local_path=m.local_path,
                    captured_at=m.captured_at,
                    decision_status=(d.status if d else None),
                    decision_reason=(d.reason if d else None),
                    decision_notes=(d.notes if d else None)
                )
            )
        return out
    
    @staticmethod
    def bulk_set_decisions_for_session(
        db: Session,
        *,
        import_session_id: int,
        media_ids: list[int],
        status: str,
        reason: str | None = None,
        notes: str | None = None
    ) -> int:
        """
        Enforces: only media inside this import_session_id can be decided here.
        Operator is derived from ImportSession.operator_id.
        """
        if status not in DecisionService.VALID:
            raise DecisionServiceError("Invalid decision status. Must be 'accepted' or 'rejected'.")
         
        media_ids = [int(x) for x in media_ids if str(x).strip()]
        media_ids = list(dict.fromkeys(media_ids))  # de-dupe keep order
        if not media_ids:
            return 0
        
        sess = db.scalar(select(ImportSession).where(ImportSession.import_session_id == import_session_id))
        if not sess:
            raise DecisionServiceError(f"ImportSession not found: {import_session_id}")

        # Validate ownership: all media must belong to this session
        valid_ids = set(
            db.scalars(
                select(Media.media_id).where(
                    Media.import_session_id == import_session_id,
                    Media.media_id.in_(media_ids),
                )
            ).all()
        )

        missing_or_wrong_session = [mid for mid in media_ids if mid not in valid_ids]
        if missing_or_wrong_session:
            raise DecisionServiceError(
                f"Some media IDs are not in this session: {missing_or_wrong_session}"
            )
        
        for mid in media_ids:
            upsert_decision(
                db,
                media_id=mid,
                status=status,
                reason=reason,
                notes=notes,
            )

        return len(media_ids)
        
