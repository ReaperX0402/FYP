from flask import Blueprint, render_template, redirect, url_for, flash
from sqlalchemy import select, func
from pathlib import Path

from src.db.session import SessionLocal
from src.db.models import ImportSession, Media, Decisions, Exports
from src.web.auth import login_required
from src.core.export_zip import export_session_to_zip

bp = Blueprint("exports", __name__)

EXPORT_ROOT = Path("data/exports")
ARCHIVE_ROOT = Path("data/archive")

@bp.get("/sessions/<int:import_session_id>/export")
@login_required
def export_page(import_session_id: int):
    with SessionLocal() as db:
        sess = db.get(ImportSession, import_session_id)
        if not sess:
            flash("Import session not found.", "error")
            return redirect(url_for("ingestion.dashboard"))

        total = db.scalar(
            select(func.count()).select_from(Media)
            .where(Media.import_session_id == import_session_id)
        ) or 0

        accepted = db.scalar(
            select(func.count())
            .select_from(Media)
            .join(Decisions, Decisions.media_id == Media.media_id)
            .where(Media.import_session_id == import_session_id)
            .where(Decisions.status == "accepted")
        ) or 0

        rejected = db.scalar(
            select(func.count())
            .select_from(Media)
            .join(Decisions, Decisions.media_id == Media.media_id)
            .where(Media.import_session_id == import_session_id)
            .where(Decisions.status == "rejected")
        ) or 0

        undecided = total - accepted - rejected

        latest_export = db.scalar(
            select(Exports)
            .where(Exports.import_session_id == import_session_id)
            .order_by(Exports.created_at.desc())
            .limit(1)
        )

    return render_template(
        "sessions_export.html",
        sess=sess,
        total=total,
        accepted=accepted,
        rejected=rejected,
        undecided=undecided,
        latest_export=latest_export,
    )

@bp.post("/sessions/<int:import_session_id>/export/run")
@login_required
def export_run(import_session_id: int):
    with SessionLocal() as db:
        try:
            result = export_session_to_zip(
                db=db,
                import_session_id=import_session_id,
                export_root=EXPORT_ROOT,
                archive_root=ARCHIVE_ROOT,
            )
            flash(f"Export complete. Status: archived", "success")
        except Exception as e:
            flash(f"Export failed: {str(e)}", "error")

    return redirect(url_for("exports.export_page", import_session_id=import_session_id))