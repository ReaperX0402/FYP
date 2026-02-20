from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, flash
from sqlalchemy import select

from src.db.session import SessionLocal
from src.db.models import ImportSession, Media
from src.core.ingestion_service import run_ingestion_for_session
from src.web.auth import login_required, get_current_operator_id

bp = Blueprint("ingestion", __name__)


@bp.get("/dashboard")
@login_required
def dashboard():
    operator_id = get_current_operator_id()
    with SessionLocal() as db:
        sessions = db.scalars(
            select(ImportSession).order_by(ImportSession.import_session_id.desc()).limit(20)
        ).all()
    return render_template("dashboard.html", operator_id=operator_id, sessions=sessions)


@bp.get("/sessions/<int:import_session_id>/ingest")
@login_required
def ingest_page(import_session_id: int):
    with SessionLocal() as db:
        session_row = db.get(ImportSession, import_session_id)
        if not session_row:
            flash("Import session not found", "error")
            return redirect(url_for("ingestion.dashboard"))

        media_count = db.query(Media).filter(
            Media.import_session_id == import_session_id
        ).count()

    return render_template(
        "sessions_ingest.html",
        session=session_row,
        media_count=media_count,
    )


@bp.post("/sessions/<int:import_session_id>/ingest/run")
@login_required
def run_ingest(import_session_id: int):
    try:
        result = run_ingestion_for_session(import_session_id)
        flash(
            f"Ingestion completed. Imported: {result.get('imported', 0)}, "
            f"Skipped: {result.get('skipped', 0)}, "
            f"Failed: {result.get('failed', 0)}",
            "success",
        )
    except Exception as e:
        flash(f"Ingestion failed: {str(e)}", "error")

    return redirect(url_for("ingestion.ingest_page", import_session_id=import_session_id))
