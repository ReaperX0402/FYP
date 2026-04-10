from __future__ import annotations

import shutil
from pathlib import Path

from flask import Blueprint, render_template, redirect, url_for, flash, request
from sqlalchemy import select, func, case

from src.db.session import SessionLocal
from src.db.models import ImportSession, Jobs, Media, Decisions, Exports
from src.web.auth import login_required, get_current_operator_id

bp = Blueprint("sessions", __name__)

def _safe_delete_session_incoming_dir(import_session_id: int) -> bool:
    incoming_root = Path("data/incoming").resolve()
    target_dir = (incoming_root / f"session_{import_session_id}").resolve()

    try:
        target_dir.relative_to(incoming_root)
    except ValueError:
        return False

    if target_dir.exists():
        if not target_dir.is_dir():
            return False
        shutil.rmtree(target_dir)

    return True

def _get_archive_dir_for_session(session_row) -> Path:
    return Path("data/archive") / f"{session_row.uut_serial}_{session_row.import_session_id}"


@bp.get("/dashboard")
@login_required
def dashboard():
    operator_id = get_current_operator_id()

    with SessionLocal() as db:
        session_rows = db.scalars(
            select(ImportSession)
            .where(ImportSession.status == "running")
            .order_by(ImportSession.import_session_id.desc())
            .limit(20)
        ).all()

        sessions = []

        for s in session_rows:
            export_exists = db.scalar(
                select(Exports.export_id)
                .where(Exports.import_session_id == s.import_session_id)
                .limit(1)
            ) is not None

            sessions.append({
                "session": s,
                "has_export": export_exists,
            })

    return render_template("dashboard.html", operator_id=operator_id, sessions=sessions)


@bp.get("/sessions/new")
@login_required
def new_session_page():
    operator_id = get_current_operator_id()

    with SessionLocal() as db:
        stmt = select(Jobs).order_by(Jobs.job_id.desc())
        jobs = db.scalars(stmt).all()

    open_jobs = []
    for j in jobs:
        if hasattr(j, "status"):
            if (j.status or "").lower() not in ("closed", "ended"):
                open_jobs.append(j)
        else:
            open_jobs.append(j)

    return render_template("session_new.html", operator_id=operator_id, jobs=open_jobs)


@bp.post("/sessions/new")
@login_required
def create_session():
    uut_serial = (request.form.get("uut_serial") or "").strip()
    job_id = (request.form.get("job_id") or "").strip()
    operator_id = get_current_operator_id()

    if not job_id:
        flash("Job is required.", "error")
        return redirect(url_for("sessions.new_session_page"))

    if not uut_serial:
        flash("UUT Serial is required.", "error")
        return redirect(url_for("sessions.new_session_page"))

    with SessionLocal() as db:
        job = db.get(Jobs, job_id)
        if not job:
            flash("Selected job does not exist.", "error")
            return redirect(url_for("sessions.new_session_page"))

        new_session = ImportSession(
            job_id=job_id,
            uut_serial=uut_serial,
            operator_id=operator_id,
            status="running",
        )

        db.add(new_session)
        db.commit()
        db.refresh(new_session)

    flash(
        f"Import Session {new_session.import_session_id} created.",
        "success",
    )

    return redirect(url_for("ingestion.ingest_page", import_session_id=new_session.import_session_id))

@bp.post("/sessions/<int:import_session_id>/complete")
@login_required
def complete_session(import_session_id: int):
    with SessionLocal() as db:
        session_row = db.get(ImportSession, import_session_id)

        if not session_row:
            flash("Session not found.", "error")
            return redirect(url_for("sessions.dashboard"))

        if session_row.status != "running":
            flash("Only running sessions can be completed.", "error")
            return redirect(url_for("sessions.dashboard"))

        has_valid_export = db.scalar(
            select(Exports.export_id)
            .where(Exports.import_session_id == import_session_id)
            .where(Exports.status == "archived")
            .limit(1)
        ) is not None

        if not has_valid_export:
            flash(
                "Session cannot be completed. No successful export found. Please generate an export first.",
                "error"
            )
            return redirect(url_for("sessions.dashboard"))

        # safe delete AFTER validation
        ok = _safe_delete_session_incoming_dir(import_session_id)
        if not ok:
            flash("Unsafe folder deletion blocked.", "error")
            return redirect(url_for("sessions.dashboard"))

        session_row.status = "completed"
        db.commit()

    flash(f"Session {import_session_id} completed.", "success")
    return redirect(url_for("sessions.dashboard"))


@bp.post("/sessions/<int:import_session_id>/cancel")
@login_required
def cancel_session(import_session_id: int):
    with SessionLocal() as db:
        session_row = db.get(ImportSession, import_session_id)

        if not session_row:
            flash("Session not found.", "error")
            return redirect(url_for("sessions.dashboard"))

        if session_row.status != "running":
            flash("Only running sessions can be cancelled.", "error")
            return redirect(url_for("sessions.dashboard"))

        ok = _safe_delete_session_incoming_dir(import_session_id)
        if not ok:
            flash("Unsafe folder deletion blocked.", "error")
            return redirect(url_for("sessions.dashboard"))

        session_row.status = "failed"
        db.commit()

    flash(f"Session {import_session_id} cancelled.", "success")
    return redirect(url_for("sessions.dashboard"))

@bp.get("/sessions/archive")
@login_required
def archive_page():
    operator_id = get_current_operator_id()

    with SessionLocal() as db:
        total_count = func.count(Media.media_id).label("total_count")

        accepted_count = func.coalesce(
            func.sum(case((Decisions.status == "accepted", 1), else_=0)),
            0
        ).label("accepted_count")

        rejected_count = func.coalesce(
            func.sum(case((Decisions.status == "rejected", 1), else_=0)),
            0
        ).label("rejected_count")

        stmt = (
            select(
                ImportSession,
                total_count,
                accepted_count,
                rejected_count,
            )
            .outerjoin(Media, Media.import_session_id == ImportSession.import_session_id)
            .outerjoin(Decisions, Decisions.media_id == Media.media_id)
            .where(ImportSession.status.in_(["completed", "failed"]))
            .group_by(ImportSession.import_session_id)
            .order_by(ImportSession.import_session_id.desc())
        )

        rows = db.execute(stmt).all()

    completed_sessions = []
    cancelled_sessions = []

    for session_row, total_media, accepted_media, rejected_media in rows:
        archive_dir = _get_archive_dir_for_session(session_row)
        item = {
            "session": session_row,
            "total_count": int(total_media or 0),
            "accepted_count": int(accepted_media or 0),
            "rejected_count": int(rejected_media or 0),
            "archive_dir_name": archive_dir.name,
            "archive_exists": archive_dir.exists() and archive_dir.is_dir(),
        }

        if session_row.status == "completed":
            completed_sessions.append(item)
        elif session_row.status == "failed":
            cancelled_sessions.append(item)

    return render_template(
        "archive_sessions.html",
        operator_id=operator_id,
        completed_sessions=completed_sessions,
        cancelled_sessions=cancelled_sessions,
    )

@bp.post("/sessions/<int:import_session_id>/amend")
@login_required
def amend_session(import_session_id: int):
    operator_id = get_current_operator_id()

    with SessionLocal() as db:
        session_row = db.get(ImportSession, import_session_id)

        if not session_row:
            flash("Session not found.", "error")
            return redirect(url_for("sessions.archive_page"))

        if session_row.status != "completed":
            flash("Only completed sessions can be amended.", "error")
            return redirect(url_for("sessions.archive_page"))

        # Reopen session for decision correction
        session_row.status = "running"
        db.commit()

    flash(
        f"Session {import_session_id} reopened for amendment by operator {operator_id}.",
        "success",
    )
    return redirect(url_for("decisions.decide_page", import_session_id=import_session_id))

@bp.post("/sessions/<int:import_session_id>/retake")
@login_required
def create_retake_session(import_session_id: int):
    operator_id = get_current_operator_id()

    with SessionLocal() as db:
        original = db.get(ImportSession, import_session_id)
        if not original:
            flash("Original session not found.", "error")
            return redirect(url_for("sessions.archive_page"))

        if original.status not in ("completed", "failed"):
            flash("Only archived sessions can create a retake session.", "error")
            return redirect(url_for("sessions.archive_page"))

        new_session = ImportSession(
            job_id=original.job_id,
            uut_serial=original.uut_serial,
            operator_id=operator_id,
            status="running",
            session_purpose="retake",
        )

        db.add(new_session)
        db.commit()
        db.refresh(new_session)

    flash(
        f"Retake session {new_session.import_session_id} created from archived session {import_session_id}.",
        "success",
    )
    return redirect(url_for("ingestion.ingest_page", import_session_id=new_session.import_session_id))


@bp.post("/sessions/<int:import_session_id>/rework")
@login_required
def create_rework_session(import_session_id: int):
    operator_id = get_current_operator_id()

    with SessionLocal() as db:
        original = db.get(ImportSession, import_session_id)
        if not original:
            flash("Original session not found.", "error")
            return redirect(url_for("sessions.archive_page"))

        if original.status not in ("completed", "failed"):
            flash("Only archived sessions can create a rework session.", "error")
            return redirect(url_for("sessions.archive_page"))

        new_session = ImportSession(
            job_id=original.job_id,
            uut_serial=original.uut_serial,
            operator_id=operator_id,
            status="running",
            session_purpose="rework",
        )

        db.add(new_session)
        db.commit()
        db.refresh(new_session)

    flash(
        f"Rework session {new_session.import_session_id} created from archived session {import_session_id}.",
        "success",
    )
    return redirect(url_for("ingestion.ingest_page", import_session_id=new_session.import_session_id))