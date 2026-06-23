from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session

from account_store import (
    authenticate_user,
    create_user,
    digest_payload_for_user,
    get_preferences,
    get_user_by_id,
    public_digest_payload,
    save_preferences,
    serialise_user,
)


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.secret_key = os.getenv("SESSION_SECRET", "dev-session-secret-change-me")


def json_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def current_user() -> dict[str, Any] | None:
    user_id = session.get("user_id")

    if not user_id:
        return None

    return get_user_by_id(str(user_id))


def require_user():
    user = current_user()

    if not user:
        return None, (jsonify({"error": "Authentication required."}), 401)

    return user, None


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/digest")
@app.get("/digest.html")
def digest():
    return send_from_directory(BASE_DIR, "digest.html")


@app.get("/login")
@app.get("/login.html")
def login_page():
    return send_from_directory(BASE_DIR, "login.html")


@app.get("/api/auth/me")
def auth_me():
    user = current_user()

    if not user:
        return jsonify({"authenticated": False, "user": None})

    return jsonify({"authenticated": True, "user": serialise_user(user)})


@app.post("/api/auth/register")
def auth_register():
    payload = json_payload()

    try:
        user = create_user(
            str(payload.get("email", "")),
            str(payload.get("password", "")),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    session["user_id"] = user["id"]
    return jsonify({"authenticated": True, "user": serialise_user(user)}), 201


@app.post("/api/auth/login")
def auth_login():
    payload = json_payload()
    user = authenticate_user(
        str(payload.get("email", "")),
        str(payload.get("password", "")),
    )

    if not user:
        return jsonify({"error": "Invalid email or password."}), 401

    session["user_id"] = user["id"]
    return jsonify({"authenticated": True, "user": serialise_user(user)})


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"authenticated": False})


@app.get("/api/preferences")
def preferences_get():
    user, error_response = require_user()

    if error_response:
        return error_response

    return jsonify(get_preferences(user["id"]))


@app.put("/api/preferences")
def preferences_put():
    user, error_response = require_user()

    if error_response:
        return error_response

    return jsonify(save_preferences(user["id"], json_payload()))


@app.get("/api/digest")
def digest_get():
    user = current_user()

    if not user:
        return jsonify(public_digest_payload())

    return jsonify(digest_payload_for_user(user["id"]))


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").lower() == "true",
    )
