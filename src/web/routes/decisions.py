from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash

from src.db.session import SessionLocal  
from src.core.decision_service import DecisionService, DecisionServiceError

bp = Blueprint("decision_service", __name__)

@bp.get("/sessions/<int:import_session_id>/decide")
def decide_page(import_session_id: int):
    with SessionLocal() as db:
        rows = DecisionService.list_media_for_session(db, import_session_id)
    return render_template("sessions_decide.html", import_session_id=import_session_id, rows=rows)

@bp.post("/sessions/<int:import_session_id>/decide/bulk")
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

