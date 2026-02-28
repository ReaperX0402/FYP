from __future__ import annotations

from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file

from src.db.session import SessionLocal
from src.db.models import Media
from src.core.decision_service import DecisionService, DecisionServiceError
from src.web.auth import login_required

bp = Blueprint("decisions", __name__)

ALLOWED_MEDIA_ROOTS = [
    Path("data/incoming").resolve()
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

def _is_under_allowed_root(p: Path) -> bool:
    p = p.resolve()
    for root in ALLOWED_MEDIA_ROOTS:
        root = root.resolve()
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False

@bp.get("/media/<int:media_id>/file")
@login_required
def media_file(media_id: int):
    with SessionLocal() as db:
        m = db.get(Media, media_id)
        if not m:
            abort(404)

        if not m.local_path:
            abort(404)

        p = Path(m.local_path)

    if not _is_under_allowed_root(p):
        abort(403)

    if not p.exists() or not p.is_file():
        abort(404)

    return send_file(p, conditional=True)

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