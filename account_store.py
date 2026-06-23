from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from firebase_store import firestore_client
from scraper_utils import BASE_DIR, STATUS_FILE, get_today, read_json


DATABASE_FILE = BASE_DIR / "legal_digest.db"
USERS_COLLECTION = "users"
PREFERENCES_COLLECTION = "preferences"
DEFAULT_CASES_COLLECTION = "cases"

SOURCE_VALUE_TO_ID = {
    "elitigation": "singapore",
    "bailii-uksc": "bailii_uksc",
    "bailii-ewhc-commercial": "bailii_comm",
    "bailii-ewhc-admiralty": "bailii_admlty",
}
DEFAULT_SOURCES = ["elitigation", "bailii-uksc", "bailii-ewhc-commercial", "bailii-ewhc-admiralty"]
DEFAULT_TOPICS = ["criminal", "family", "employment", "contract", "data-protection", "shipping"]
VALID_READER_TYPES = {"regular", "lawyer"}


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def normalise_email(email: str) -> str:
    return email.strip().lower()


def user_id_for_email(email: str) -> str:
    return hashlib.sha256(normalise_email(email).encode("utf-8")).hexdigest()[:32]


def firebase_db():
    try:
        return firestore_client()
    except Exception:
        return None


def init_local_tables() -> None:
    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                user_id TEXT PRIMARY KEY,
                reader_type TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                topics_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        ensure_case_artifact_columns(connection)


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if table_name not in tables:
        return

    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def ensure_case_artifact_columns(connection: sqlite3.Connection) -> None:
    ensure_column(connection, "cases", "short_summary", "TEXT")
    ensure_column(connection, "cases", "regular_summary", "TEXT")
    ensure_column(connection, "cases", "lawyer_summary", "TEXT")
    ensure_column(connection, "cases", "summary_pdf_path", "TEXT")
    ensure_column(connection, "cases", "summary_pdf_name", "TEXT")
    ensure_column(connection, "cases", "long_summary_json", "TEXT")
    connection.execute(
        """
        UPDATE cases
        SET regular_summary = COALESCE(NULLIF(regular_summary, ''), NULLIF(short_summary, ''), NULLIF(judgment, ''), ''),
            lawyer_summary = COALESCE(NULLIF(lawyer_summary, ''), NULLIF(holding, ''), NULLIF(short_summary, ''), NULLIF(judgment, ''), '')
        """
    )


def default_preferences() -> dict[str, Any]:
    return {
        "readerType": "regular",
        "sources": DEFAULT_SOURCES,
        "topics": DEFAULT_TOPICS,
    }


def clean_preferences(payload: dict[str, Any]) -> dict[str, Any]:
    reader_type = payload.get("readerType") or payload.get("reader_type") or "regular"
    sources = payload.get("sources")
    topics = payload.get("topics")

    if reader_type not in VALID_READER_TYPES:
        reader_type = "regular"

    if not isinstance(sources, list):
        sources = DEFAULT_SOURCES

    if not isinstance(topics, list):
        topics = DEFAULT_TOPICS

    clean_sources = [source for source in sources if source in SOURCE_VALUE_TO_ID]
    clean_topics = [topic for topic in topics if topic in DEFAULT_TOPICS]

    return {
        "readerType": reader_type,
        "sources": clean_sources or DEFAULT_SOURCES,
        "topics": clean_topics or DEFAULT_TOPICS,
    }


def serialise_user(user: dict[str, Any]) -> dict[str, str]:
    return {
        "id": user["id"],
        "email": user["email"],
    }


def valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def get_user_by_email(email: str) -> dict[str, Any] | None:
    init_local_tables()
    email = normalise_email(email)
    user_id = user_id_for_email(email)
    db = firebase_db()

    if db is not None:
        document = db.collection(USERS_COLLECTION).document(user_id).get()

        if document.exists:
            return document.to_dict()

        return None

    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    init_local_tables()
    db = firebase_db()

    if db is not None:
        document = db.collection(USERS_COLLECTION).document(user_id).get()
        return document.to_dict() if document.exists else None

    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    return dict(row) if row else None


def create_user(email: str, password: str) -> dict[str, Any]:
    init_local_tables()
    email = normalise_email(email)

    if not valid_email(email):
        raise ValueError("Enter a valid email address.")

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    if get_user_by_email(email):
        raise ValueError("An account with this email already exists.")

    user_id = user_id_for_email(email)
    timestamp = now_iso()
    user = {
        "id": user_id,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    db = firebase_db()

    if db is not None:
        db.collection(USERS_COLLECTION).document(user_id).set(user)
    else:
        with sqlite3.connect(DATABASE_FILE) as connection:
            connection.execute(
                """
                INSERT INTO users (id, email, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user["id"], user["email"], user["password_hash"], timestamp, timestamp),
            )

    save_preferences(user_id, default_preferences())
    return user


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(email)

    if not user:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return user


def get_preferences(user_id: str) -> dict[str, Any]:
    init_local_tables()
    db = firebase_db()

    if db is not None:
        document = db.collection(PREFERENCES_COLLECTION).document(user_id).get()

        if document.exists:
            return clean_preferences(document.to_dict())

        return default_preferences()

    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT reader_type, sources_json, topics_json FROM preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return default_preferences()

    return clean_preferences(
        {
            "readerType": row["reader_type"],
            "sources": json.loads(row["sources_json"]),
            "topics": json.loads(row["topics_json"]),
        }
    )


def save_preferences(user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
    init_local_tables()
    cleaned = clean_preferences(preferences)
    timestamp = now_iso()
    db = firebase_db()

    if db is not None:
        db.collection(PREFERENCES_COLLECTION).document(user_id).set(
            {
                **cleaned,
                "user_id": user_id,
                "updated_at": timestamp,
            },
            merge=True,
        )
    else:
        with sqlite3.connect(DATABASE_FILE) as connection:
            connection.execute(
                """
                INSERT INTO preferences (user_id, reader_type, sources_json, topics_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    reader_type = excluded.reader_type,
                    sources_json = excluded.sources_json,
                    topics_json = excluded.topics_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    cleaned["readerType"],
                    json.dumps(cleaned["sources"]),
                    json.dumps(cleaned["topics"]),
                    timestamp,
                ),
            )

    return cleaned


def normalise_case(case: dict[str, Any]) -> dict[str, Any]:
    tags = case.get("tags", [])
    files = case.get("files", {})

    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

    if not isinstance(tags, list):
        tags = []

    if not isinstance(files, dict):
        files = {}

    summary_pdf_file = case.get("long_summary_pdf") or files.get("long_summary_pdf", {})

    if not isinstance(summary_pdf_file, dict):
        summary_pdf_file = {}

    summary_pdf = case.get("summary_pdf") or case.get("summary_pdf_path") or summary_pdf_file.get("gs_url", "")
    regular_summary = case.get("regular_summary") or case.get("short_summary") or case.get("judgment", "")
    lawyer_summary = case.get("lawyer_summary") or case.get("holding") or regular_summary
    short_summary = case.get("short_summary") or regular_summary

    return {
        "folder_name": case.get("folder_name", ""),
        "source_id": case.get("source_id", ""),
        "case_name": case.get("case_name", ""),
        "parties": case.get("parties", ""),
        "case_ref": case.get("case_ref", ""),
        "date": case.get("date", ""),
        "court": case.get("court", ""),
        "regular_summary": regular_summary,
        "lawyer_summary": lawyer_summary,
        "short_summary": short_summary,
        "summary_pdf": summary_pdf,
        "summary_pdf_name": case.get("summary_pdf_name", ""),
        "judgment": case.get("judgment") or regular_summary,
        "holding": case.get("holding", ""),
        "source_url": case.get("source_url", ""),
        "tags": [tag for tag in tags if tag in DEFAULT_TOPICS],
    }


def load_cases_from_firestore() -> list[dict[str, Any]] | None:
    db = firebase_db()

    if db is None:
        return None

    collection = os.getenv("FIREBASE_CASES_COLLECTION", DEFAULT_CASES_COLLECTION)
    documents = db.collection(collection).stream()
    return [normalise_case(document.to_dict()) for document in documents]


def load_cases_from_sqlite() -> list[dict[str, Any]]:
    init_local_tables()

    if not DATABASE_FILE.exists():
        return []

    try:
        with sqlite3.connect(DATABASE_FILE) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT
                    folder_name,
                    source_id,
                    case_name,
                    parties,
                    case_ref,
                    date,
                    court,
                judgment,
                holding,
                source_url,
                short_summary,
                regular_summary,
                lawyer_summary,
                summary_pdf_path,
                summary_pdf_name,
                tags_json
            FROM cases
            ORDER BY date DESC, id DESC
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return []

    cases: list[dict[str, Any]] = []

    for row in rows:
        case = dict(row)

        try:
            case["tags"] = json.loads(case.pop("tags_json") or "[]")
        except json.JSONDecodeError:
            case["tags"] = []

        cases.append(normalise_case(case))

    return cases


def load_all_cases() -> list[dict[str, Any]]:
    firestore_cases = load_cases_from_firestore()

    if firestore_cases is not None:
        return firestore_cases

    return load_cases_from_sqlite()


def source_ids_for_preferences(preferences: dict[str, Any]) -> set[str]:
    selected = preferences.get("sources") or DEFAULT_SOURCES
    return {SOURCE_VALUE_TO_ID[source] for source in selected if source in SOURCE_VALUE_TO_ID}


def filter_cases_for_preferences(
    cases: list[dict[str, Any]],
    preferences: dict[str, Any],
) -> list[dict[str, Any]]:
    source_ids = source_ids_for_preferences(preferences)
    topics = set(preferences.get("topics") or DEFAULT_TOPICS)
    all_topics_selected = topics == set(DEFAULT_TOPICS)
    filtered: list[dict[str, Any]] = []

    for case in cases:
        if source_ids and case["source_id"] not in source_ids:
            continue

        if not all_topics_selected and not set(case["tags"]).intersection(topics):
            continue

        filtered.append(case)

    return filtered


def source_warnings() -> dict[str, str]:
    status = read_json(STATUS_FILE, {})
    warnings: dict[str, str] = {}

    for source_id, entry in status.items():
        if not isinstance(entry, dict):
            continue

        if entry.get("status") not in {"ok", "pending", "running"}:
            warnings[source_id] = entry.get("message") or entry.get("status", "unknown")

    return warnings


def digest_payload_for_user(user_id: str) -> dict[str, Any]:
    preferences = get_preferences(user_id)
    return digest_payload_for_preferences(preferences)


def digest_payload_for_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    cases = filter_cases_for_preferences(load_all_cases(), preferences)

    return {
        "today_str": get_today().strftime("%d %B %Y").lstrip("0"),
        "source_warnings": source_warnings(),
        "file_map": file_map_for_cases(cases),
        "preferences": preferences,
        "cases": cases,
    }


def public_digest_payload() -> dict[str, Any]:
    payload = digest_payload_for_preferences(default_preferences())
    payload["preferences"] = None
    return payload


def file_map_for_cases(cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    file_map: dict[str, list[str]] = {}

    for case in cases:
        summary_pdf = case.get("summary_pdf")

        if summary_pdf:
            file_map[case["folder_name"]] = [summary_pdf]

    return file_map
