"""Flask application (Python 3.13): user management.

Screen 1 (/)      -> list, search by name or ID, edit and delete.
Screen 2 (/edit/<id>)     -> edit form (/new reuses the same template).
Screen 3 (/delete/<id>)   -> delete confirmation page.

Run from the project root:  python View/MainViews/PY/app.py
"""
import hmac
import os
import re
import secrets
import sys
import unicodedata
import uuid
from pathlib import Path

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)

BASE = Path(__file__).resolve().parent.parent  # View/MainViews
sys.path.insert(0, str(BASE))
from Utils import api_client as api  # noqa: E402

app = Flask(__name__, template_folder=str(BASE / "HTML"), static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

ID_RE = re.compile(r"[A-Za-z0-9_-]{1,30}")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# ---------- Security ----------
def _csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = _csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "").encode()
        expected = session.get("csrf", "").encode()
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400)


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    return resp


# ---------- Static files (only the CSS and JS folders) ----------
@app.get("/static/css/<path:filename>")
def static_css(filename):
    return send_from_directory(BASE / "CSS", filename)


@app.get("/static/js/<path:filename>")
def static_js(filename):
    return send_from_directory(BASE / "JS", filename)


# ---------- Helpers ----------
def normalize(text):
    """Lowercase and strip accents: 'maria' matches 'María'."""
    base = unicodedata.normalize("NFD", str(text).lower())
    return