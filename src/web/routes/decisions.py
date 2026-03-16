from __future__ import annotations

from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file
from sqlalchemy import select

from src.db.session import SessionLocal
from src.db.models import Media, ImportSession, Decisions
from src.core.decision_service import DecisionService, DecisionServiceError
from src.web.auth import login_required

bp = Blueprint("decisions", __name__)

ALLOWED_MEDIA_ROOTS = [
    Path("data/incoming").resolve(),
    Path("data/archive").resolve(),
]


@bp.get("/sessions/<int:import_session_id>/decide")
@login_required
def decide_page(import_session_id: int):
    with SessionLocal() as db:
        rows = DecisionService.list_media_for_session(db, import_session_id)
    return render_template("sessions_decide.html", import_session_id=import_session_id, rows=rows)


@bp.post("/sessions/<int:import_session_id>/decide/bulk")
@login_required
def bulk_decide(import_session_id: int):
    media_ids = request.form.getlist("media_id")
    action = request.form.get("action", "").strip().lower()
    reason = (request.form.get("reason", "") or "").strip() or None
    notes = (request.form.get("notes", "") or "").strip() or None

    if action not in ("accepted", "rejected"):
        flash("Invalid action", "error")
        return redirect(url_for("decisions.decide_page", import_session_id=import_session_id))

    try:
        with SessionLocal() as db:
            count = DecisionService.bulk_set_decisions_for_session(
                db,
                import_session_id=import_session_id,
                media_ids=media_ids,
                status=action,
                reason=reason,
                notes=notes,
            )
            db.commit()
        flash(f"Updated {count} items -> {action}", "success")
    except DecisionServiceError as e:
        flash(str(e), "error")

    return redirect(url_for("decisions.decide_page", import_session_id=import_session_id))


@bp.post("/media/<int:media_id>/decide")
@login_required
def decide_one(media_id: int):
    action = request.form.get("action", "").strip().lower()
    reason = (request.form.get("reason", "") or "").strip() or None
    notes = (request.form.get("notes", "") or "").strip() or None
    import_session_id = int(request.form.get("import_session_id"))

    try:
        with SessionLocal() as db:
            DecisionService.set_decision_for_media(
                db,
                import_session_id=import_session_id,
                media_id=media_id,
                status=action,
                reason=reason,
                notes=notes,
            )
            db.commit()
        flash(f"Media {media_id} -> {action}", "success")
    except DecisionServiceError as e:
        flash(str(e), "error")

    return redirect(url_for("decisions.decide_page", import_session_id=import_session_id))


def _resolve_media_path(raw: str) -> Path:
    p = Path(raw)

    if not p.is_absolute():
        p = Path.cwd() / p

    try:
        return p.resolve(strict=False)
    except Exception:
        abort(404)


def _is_under_allowed_root(p: Path) -> bool:
    try:
        p = p.resolve(strict=False)
    except Exception:
        return False

    for root in ALLOWED_MEDIA_ROOTS:
        root = root.resolve()
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _build_archive_candidates(*, uut_serial: str, import_session_id: int, filename: str) -> list[Path]:
    archive_base = Path("data/archive") / f"{uut_serial}_{import_session_id}"
    return [
        archive_base / "accepted" / filename,
        archive_base / "rejected" / filename,
        archive_base / filename,  # fallback in case archive was stored flat
    ]


def _find_best_media_path(db, media_id: int) -> Path | None:
    """
    Resolve media path in this order:
    1. current Media.local_path if file still exists
    2. archived accepted path
    3. archived rejected path
    4. flat archive fallback
    """
    stmt = (
        select(Media, ImportSession, Decisions)
        .join(ImportSession, ImportSession.import_session_id == Media.import_session_id)
        .outerjoin(Decisions, Decisions.media_id == Media.media_id)
        .where(Media.media_id == media_id)
    )

    row = db.execute(stmt).first()
    if not row:
        return None

    media, session_row, decision_row = row

    if media.local_path:
        current_path = _resolve_media_path(media.local_path)
        if _is_under_allowed_root(current_path) and current_path.exists() and current_path.is_file():
            return current_path

    candidates = _build_archive_candidates(
        uut_serial=session_row.uut_serial,
        import_session_id=session_row.import_session_id,
        filename=media.filename,
    )

    if decision_row and decision_row.status == "accepted":
        ordered = [
            candidates[0],  # accepted
            candidates[1],  # rejected
            candidates[2],  # flat
        ]
    elif decision_row and decision_row.status == "rejected":
        ordered = [
            candidates[1],  # rejected
            candidates[0],  # accepted
            candidates[2],  # flat
        ]
    else:
        ordered = candidates

    for candidate in ordered:
        resolved = _resolve_media_path(str(candidate))
        if _is_under_allowed_root(resolved) and resolved.exists() and resolved.is_file():
            return resolved

    return None


@bp.get("/media/<int:media_id>/file")
@login_required
def media_file(media_id: int):
    with SessionLocal() as db:
        p = _find_best_media_path(db, media_id)

    if not p:
        abort(404)

    return send_file(p, conditional=True)