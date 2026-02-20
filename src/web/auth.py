# src/web/auth.py
from __future__ import annotations

from functools import wraps
from flask import session, redirect, url_for, flash, request

SESSION_OPERATOR_KEY = "operator_id"


def get_current_operator_id() -> str | None:
    return session.get(SESSION_OPERATOR_KEY)


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not get_current_operator_id():
            flash("Please log in first.", "error")
            return redirect(url_for("auth.login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapper
