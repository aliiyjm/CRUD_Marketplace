"""Flask application (Python 3.13): user management.

Screen 1 (/)              -> list, search by name or ID, edit and delete.
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
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def generate_id():
    """Automatic unique ID (10 hex characters). Needs no database read."""
    return uuid.uuid4().hex[:10]


def user_name(user):
    """Records created before the English rename store the name as 'nombre'."""
    return user.get("name") or user.get("nombre", "")


def read_form():
    return {
        "id": request.form.get("id", "").strip(),
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
    }


def validate(data):
    errors = []
    if not ID_RE.fullmatch(data["id"]):
        errors.append("Invalid ID.")
    if not 1 <= len(data["name"]) <= 80:
        errors.append("Name is required (maximum 80 characters).")
    if len(data["email"]) > 120 or not EMAIL_RE.fullmatch(data["email"]):
        errors.append("Enter a valid email address.")
    return errors


# ---------- Screen 1: list and search ----------
@app.get("/")
def index():
    q = request.args.get("q", "").strip()[:80]
    try:
        users = [dict(u, name=user_name(u)) for u in api.list_users() if u.get("id")]
    except api.ApiError as e:
        flash(str(e), "error")
        users = []
    if q:
        n = normalize(q)
        users = [u for u in users
                 if n in normalize(u["id"]) or n in normalize(u["name"])]
    users.sort(key=lambda u: str(u["id"]))
    return render_template("list.html", users=users, q=q)


@app.get("/delete/<user_id>")
def confirm_delete(user_id):
    """Screen 3: shows the user and asks for confirmation before deleting."""
    if not ID_RE.fullmatch(user_id):
        abort(404)
    try:
        existing = api.get_user(user_id)
    except api.ApiError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))
    if existing is None:
        flash("That user no longer exists.", "error")
        return redirect(url_for("index"))
    user = {"id": user_id, "name": user_name(existing), "email": existing.get("email", "")}
    return render_template("confirm_delete.html", user=user)


@app.post("/delete/<user_id>")
def delete_user(user_id):
    if not ID_RE.fullmatch(user_id):
        abort(404)
    try:
        api.delete_user(user_id)
        flash("User deleted.", "ok")
    except api.ApiError as e:
        flash(str(e), "error")
    return redirect(url_for("index"))


# ---------- Screen 2: form (add / edit) ----------
@app.route("/new", methods=["GET", "POST"])
def new_user():
    data, errors = {"id": "", "name": "", "email": ""}, []
    if request.method == "POST":
        data = read_form()
        data["id"] = generate_id()  # the ID is never typed by the user
        errors = validate(data)
        if not errors:
            try:
                # A single POST. If the Lambda reports a repeated ID (very rare),
                # generate another one and retry.
                for _ in range(3):
                    try:
                        api.add_user(data)
                        break
                    except api.DuplicateId:
                        data["id"] = generate_id()
                else:
                    raise api.ApiError("Could not generate a unique ID. Please try again.")
                flash(f"User added with ID {data['id']}.", "ok")
                return redirect(url_for("index"))
            except api.ApiError as e:
                errors.append(str(e))
    return render_template("form.html", title="Add user", button="Add user",
                           editing=False, data=data, errors=errors)


@app.route("/edit/<user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if not ID_RE.fullmatch(user_id):
        abort(404)
    try:
        existing = api.get_user(user_id)
    except api.ApiError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))
    if existing is None:
        flash("That user no longer exists.", "error")
        return redirect(url_for("index"))

    data = {"id": user_id, "name": user_name(existing),
            "email": existing.get("email", "")}
    errors = []
    if request.method == "POST":
        data = read_form()
        data["id"] = user_id  # the ID cannot be changed
        errors = validate(data)
        if not errors:
            # The Lambda uses put_item (replaces the whole record): send the full
            # user back so fields such as password or numero are not wiped.
            existing.pop("nombre", None)  # migrate legacy field name
            existing.update(name=data["name"], email=data["email"])
            try:
                api.update_user(existing)
                flash("Changes saved.", "ok")
                return redirect(url_for("index"))
            except api.ApiError as e:
                errors.append(str(e))
    return render_template("form.html", title="Edit user", button="Save changes",
                           editing=True, data=data, errors=errors)


if __name__ == "__main__":
    print(f"API in use: {api.API_URL}")
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
