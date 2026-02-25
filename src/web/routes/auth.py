# src/web/routes/auth.py
from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from src.db.session import SessionLocal
from src.web.auth import SESSION_OPERATOR_KEY

bp = Blueprint("auth", __name__)


@bp.get("/login")
def login():
    next_url = request.args.get("next") or url_for("ingestion.dashboard")
    return render_template("login.html", next_url=next_url)


@bp.post("/login")
def login_post():
    operator_id = (request.form.get("operator_id") or "").strip()
    next_url = (request.form.get("next_url") or "").strip() or url_for("ingestion.dashboard")

    if not operator_id:
        flash("Operator ID is required.", "error")
        return redirect(url_for("auth.login", next=next_url))
    try:
        from src.db.models import Operators  # type: ignore
        with SessionLocal() as db:
            op = db.get(Operators, operator_id)
            if not op:
                flash("Invalid Operator ID (not found in DB).", "error")
                return redirect(url_for("auth.login", next=next_url))
    except Exception:
        pass

    session[SESSION_OPERATOR_KEY] = operator_id
    flash(f"Logged in as {operator_id}", "success")
    return redirect(next_url)


@bp.get("/logout")
def logout():
    session.clear()  
    flash("Logged out.", "success")
    return redirect(url_for("auth.login"))
