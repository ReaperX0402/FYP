"""
AI Review Manifest Service

Purpose:
--------
This module generates a session-level AI analysis artifact (JSON manifest) for the IPDS decision workflow.

IMPORTANT DESIGN PRINCIPLE:
---------------------------
- This manifest is NON-AUTHORITATIVE
- It is NOT used for audit, export, or decision enforcement
- It exists ONLY for:
    - Operator guidance (during review)
    - Academic traceability (report/evaluation)

Authority Boundary:
-------------------
- Database (MEDIA / DECISIONS) = Source of truth
- AI Manifest (JSON)           = Advisory layer only

Storage:
--------
data/ai_review/session_<import_session_id>_ai_review.json

Lifecycle:
----------
- Generated during decision page load
- Overwritten on each regeneration
- Not included in export pipeline
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ai_model.angle_classifier import AngleClassifier
from src.ai_model.angle_suggester import REQUIRED_ANGLES, suggest_next_angles
from src.ai_model.blur_detector import BlurDetector
from src.db.models import ImportSession, Media, Decisions


# Directory for storing AI manifest files
AI_REVIEW_DIR = Path("data/ai_review")

# Default model configuration (can be externalized later)
DEFAULT_MODEL_PATH = Path("src/ai_model/best_angle_classifier_2.pt")
DEFAULT_MODEL_NAME = "angle_classifier"
DEFAULT_MODEL_VERSION = "v1"

# Default blur config 
DEFAULT_BLUR_THRESHOLD = 42


@dataclass(frozen=True)
class AIReviewMediaRow:
    """
    Lightweight representation of media data for AI processing.

    NOTE:
    This intentionally avoids exposing full ORM objects to keep
    the AI layer decoupled from database implementation details.
    """
    media_id: int
    filename: str | None
    local_path: str
    captured_at: Any | None
    decision_status: str | None


class AIReviewManifestError(Exception):
    """Custom exception for AI manifest-related failures."""
    pass


class AIReviewManifestService:
    """
    Core service responsible for:
    - Running AI inference on session images
    - Aggregating results into a structured JSON manifest
    - Writing manifest to disk

    This service DOES NOT:
    - Modify database state
    - Influence operator decisions
    """

    def __init__(
        self,
        *,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        model_name: str = DEFAULT_MODEL_NAME,
        model_version: str = DEFAULT_MODEL_VERSION,
        blur_threshold: float = DEFAULT_BLUR_THRESHOLD,
    ) -> None:
        self.model_path = Path(model_path)
        self.model_name = model_name
        self.model_version = model_version
        self.blur_threshold = float(blur_threshold)
        # Load YOLO classifier once (expensive operation)
        self.classifier = AngleClassifier(self.model_path)
        self.blur_detector = BlurDetector(threshold=self.blur_threshold)
    # -------------------------------------------------------------------------
    # Utility Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _iso(dt: Any | None) -> str | None:
        """Convert datetime-like object to ISO string."""
        if dt is None:
            return None
        if hasattr(dt, "isoformat"):
            return dt.isoformat()
        return str(dt)

    @staticmethod
    def _now_iso() -> str:
        """Return current timestamp in ISO format."""
        return datetime.now(timezone.utc).astimezone().isoformat()

    @staticmethod
    def _manifest_path(import_session_id: int) -> Path:
        """Compute output path for session manifest."""
        return AI_REVIEW_DIR / f"session_{import_session_id}_ai_review.json"

    # -------------------------------------------------------------------------
    # Media Path Resolution
    # -------------------------------------------------------------------------

    @staticmethod
    def _resolve_path(raw: str) -> Path:
        """Resolve relative or absolute file path safely."""
        p = Path(raw)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve(strict=False)

    @staticmethod
    def _build_archive_candidates(*, uut_serial: str, import_session_id: int, filename: str) -> list[Path]:
        """
        Build possible archive paths.

        WHY:
        Media might have been moved after decision (accepted/rejected).
        We must still support AI analysis after archival.
        """
        archive_base = Path("data/archive") / f"{uut_serial}_{import_session_id}"
        return [
            archive_base / "accepted" / filename,
            archive_base / "rejected" / filename,
            archive_base / filename,
        ]

    @staticmethod
    def _find_existing_media_path(
        *,
        uut_serial: str,
        import_session_id: int,
        filename: str | None,
        local_path: str,
    ) -> Path | None:
        """
        Resolve actual file path.

        Priority:
        1. Current local_path
        2. Archived accepted/rejected paths
        3. Flat archive fallback
        """

        current = AIReviewManifestService._resolve_path(local_path)
        if current.exists() and current.is_file():
            return current

        if not filename:
            return None

        for candidate in AIReviewManifestService._build_archive_candidates(
            uut_serial=uut_serial,
            import_session_id=import_session_id,
            filename=filename,
        ):
            resolved = AIReviewManifestService._resolve_path(str(candidate))
            if resolved.exists() and resolved.is_file():
                return resolved

        return None

    # -------------------------------------------------------------------------
    # Data Loading
    # -------------------------------------------------------------------------

    @staticmethod
    def _load_rows(db: Session, import_session_id: int):
        """
        Load session + media rows.

        IMPORTANT:
        We join Decisions ONLY to expose operator decision state,
        not to influence AI results.
        """

        session_row = db.scalar(
            select(ImportSession).where(ImportSession.import_session_id == import_session_id)
        )
        if not session_row:
            raise AIReviewManifestError(f"ImportSession not found: {import_session_id}")

        stmt = (
            select(Media, Decisions)
            .outerjoin(Decisions, Decisions.media_id == Media.media_id)
            .where(Media.import_session_id == import_session_id)
            .order_by(Media.captured_at.asc().nulls_last(), Media.media_id.asc())
        )

        rows = []
        for media, decision in db.execute(stmt).all():
            rows.append(
                AIReviewMediaRow(
                    media_id=media.media_id,
                    filename=media.filename,
                    local_path=media.local_path,
                    captured_at=media.captured_at,
                    decision_status=(decision.status if decision else None),
                )
            )

        return session_row, rows

    # -------------------------------------------------------------------------
    # Duplicate Detection
    # -------------------------------------------------------------------------

    @staticmethod
    def _compute_duplicate_flags(media_results: list[dict]):
        """
        Mark duplicate angle captures.

        Current Logic:
        - Same (object, angle) appearing more than once
        - Only second+ occurrences flagged

        NOTE:
        This is intentionally simple for prototype.
        """

        counts = Counter()
        for item in media_results:
            if item.get("error") is None:
                key = (item["predicted_object"], item["predicted_angle"])
                counts[key] += 1

        seen = defaultdict(int)
        for item in media_results:
            if item.get("error") is not None:
                item["duplicate_warning"] = False
                continue

            key = (item["predicted_object"], item["predicted_angle"])
            seen[key] += 1
            item["duplicate_warning"] = counts[key] > 1 and seen[key] > 1

    # -------------------------------------------------------------------------
    # Core Manifest Builder
    # -------------------------------------------------------------------------

    def build_manifest(self, db: Session, import_session_id: int) -> dict:
        """
        Main entry point.

        Steps:
        1. Load session + media
        2. Run AI prediction per image
        3. Aggregate session coverage
        4. Build structured JSON
        """

        session_row, rows = self._load_rows(db, import_session_id)

        captured_by_object = defaultdict(set)
        object_counter = Counter()
        media_results = []

        for row in rows:
            resolved = self._find_existing_media_path(
                uut_serial=session_row.uut_serial,
                import_session_id=session_row.import_session_id,
                filename=row.filename,
                local_path=row.local_path,
            )

            if resolved is None:
                media_results.append({
                    "media_id": row.media_id,
                    "filename": row.filename,
                    "predicted_class": None,
                    "predicted_object": None,
                    "predicted_angle": None,
                    "confidence": None,
                    "blur_score": None,
                    "blur_warning": False,
                    "duplicate_warning": False,
                    "target_mismatch_warning": False,
                    "error": "Image not found",
                    "ai_reasons": ["Processing error"],
                })
                continue

            try:
                pred = self.classifier.predict(resolved)
                blur = self.blur_detector.detect(resolved)

                object_counter[pred["object"]] += 1
                captured_by_object[pred["object"]].add(pred["angle"])

                media_results.append({
                    "media_id": row.media_id,
                    "filename": row.filename,
                    "predicted_class": pred["class_name"],
                    "predicted_object": pred["object"],
                    "predicted_angle": pred["angle"],
                    "confidence": round(float(pred["confidence"]), 6),
                    "blur_score": blur["blur_score"],
                    "blur_warning": blur["blur_warning"],
                    "duplicate_warning": False,
                    "target_mismatch_warning": False,
                    "error": None
                })

            except Exception as e:
                media_results.append({
                    "media_id": row.media_id,
                    "filename": row.filename,
                    "predicted_class": None,
                    "predicted_object": None,
                    "predicted_angle": None,
                    "confidence": None,
                    "blur_score": None,
                    "blur_warning": False,
                    "duplicate_warning": False,
                    "target_mismatch_warning": False,
                    "error": str(e)
                })

        self._compute_duplicate_flags(media_results)

        detected_object = object_counter.most_common(1)[0][0] if object_counter else None
        # Mark images whose predicted object differs from the dominant session object.
        for item in media_results:
            if item.get("error") is not None:
                item["target_mismatch_warning"] = False
                continue

            item["target_mismatch_warning"] = (
                detected_object is not None
                and item.get("predicted_object") is not None
                and item.get("predicted_object") != detected_object
            )

        captured_angles = sorted(captured_by_object.get(detected_object, set()))
        missing_angles = (
            suggest_next_angles(detected_object, captured_by_object)
            if detected_object else sorted(REQUIRED_ANGLES)
        )

        # Generate human-readable AI reasons
        for item in media_results:
            reasons = []

            if item.get("error"):
                reasons.append("Processing error")

            if item.get("blur_warning"):
                reasons.append("Retake: image appears blurry (possible motion or focus issue)")

            if item.get("duplicate_warning"):
                reasons.append("Duplicate angle detected")

            if item.get("target_mismatch_warning"):
                reasons.append("Object does not match expected UUT for this session")

            item["ai_reasons"] = reasons

        return {
            "import_session_id": session_row.import_session_id,
            "uut_serial": session_row.uut_serial,
            "model": {
                "name": self.model_name,
                "version": self.model_version,
                "path": str(self.model_path),
            },
            "blur_detection": {
                "method": "variance_of_laplacian",
                "threshold": self.blur_threshold,
            },
            "generated_at": self._now_iso(),
            "required_angles": sorted(REQUIRED_ANGLES),
            "session_summary": {
                "target_object": detected_object,
                "detected_object": detected_object,
                "captured_angles": captured_angles,
                "missing_angles": missing_angles,
                "total_media": len(rows),
            },
            "media_results": media_results,
        }

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def write_manifest(self, import_session_id: int, manifest: dict) -> Path:
        """Write manifest JSON to disk."""
        AI_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        path = self._manifest_path(import_session_id)
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    def build_and_write_manifest(self, db: Session, import_session_id: int):
        """Convenience wrapper."""
        manifest = self.build_manifest(db, import_session_id)
        path = self.write_manifest(import_session_id, manifest)
        return manifest, path