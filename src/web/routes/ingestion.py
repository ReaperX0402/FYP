from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, flash, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.session import SessionLocal
from src.db.models import ImportSession, Media, Jobs
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

@bp.get("/sessions/new")
@login_required
def new_session_page():
    operator_id = get_current_operator_id()

    with SessionLocal() as db:
        stmt = select(Jobs).order_by(Jobs.job_id.desc())
        jobs = db.scalars(stmt).all()

    # If your Jobs has a status field, filter to open only.
    # If not, show all jobs.
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
        return redirect(url_for("ingestion.new_session_page"))

    if not uut_serial:
        flash("UUT Serial is required.", "error")
        return redirect(url_for("ingestion.new_session_page"))

    with SessionLocal() as db:
        # Validate job exists
        job = db.get(Jobs, job_id)
        if not job:
            flash("Selected job does not exist.", "error")
            return redirect(url_for("ingestion.new_session_page"))

        # Optional: block closed jobs (if status exists)
        if hasattr(job, "status") and (job.status or "").lower() in ("closed", "ended"):
            flash("Cannot create session under a closed job.", "error")
            return redirect(url_for("ingestion.new_session_page"))

        # Create session
        new_session = ImportSession(
            job_id=job_id,
            uut_serial=uut_serial,
            operator_id=operator_id,
        )

        # Optional: if your ImportSession has status and no default, set it
        if hasattr(new_session, "status") and not getattr(new_session, "status", None):
            new_session.status = "running"

        db.add(new_session)
        db.commit()
        db.refresh(new_session)

    flash(f"Import Session {new_session.import_session_id} created under Job {job_id}.", "success")
    return redirect(url_for("ingestion.ingest_page", import_session_id=new_session.import_session_id))
    
@bp.get("/jobs/new")
@login_required
def new_job_page():
    return render_template("job_new.html")

@bp.post("/jobs/new")
@login_required
def create_job():
    job_id = (request.form.get("job_id") or "").strip()

    if not job_id:
        flash("Job ID is required.", "error")
        return redirect(url_for("ingestion.new_job_page"))

    with SessionLocal() as db:
        try:
            # Minimal insert: assumes job_id is required and other fields have defaults or nullable
            job = Jobs(job_id=job_id)
            db.add(job)
            db.commit()
            flash(f"Job created: {job_id}", "success")
            return redirect(url_for("ingestion.dashboard"))

        except IntegrityError as e:
            db.rollback()
            # Most common: duplicate job_id or missing required columns
            flash(f"Failed to create job: {str(e.orig)}", "error")
            return redirect(url_for("ingestion.new_job_page"))

@bp.get("/jobs")
@login_required
def jobs_page():
    with SessionLocal() as db:
        jobs = db.scalars(select(Jobs).order_by(Jobs.job_id.desc()).limit(200)).all()
    return render_template("jobs.html", jobs=jobs)

@bp.post("/jobs/<job_id>/close")
@login_required
def close_job(job_id: str):
    with SessionLocal() as db:
        job = db.get(Jobs, job_id)
        if not job:
            flash("Job not found.", "error")
            return redirect(url_for("ingestion.jobs_page"))

        # Optional: block closing if any running sessions exist for this job
        # Adjust status string if yours differs
        active_sessions = db.query(ImportSession).filter(
            ImportSession.job_id == job_id,
            ImportSession.status == "running",
        ).count()

        if active_sessions > 0:
            flash(f"Cannot close job. There are {active_sessions} running session(s).", "error")
            return redirect(url_for("ingestion.jobs_page"))

        # ---- Close job (best effort depending on columns) ----
        # If your Jobs model has these fields, set them. If not, it will raise AttributeError and you'll fix it once.
        if hasattr(job, "status"):
            job.status = "closed"

        db.commit()
        flash(f"Job closed: {job_id}", "success")
        return redirect(url_for("ingestion.jobs_page"))