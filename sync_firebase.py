from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from account_store import DATABASE_FILE, normalise_case
from firebase_store import firebase_configured, save_case
from scraper_utils import BASE_DIR


def load_local_cases() -> list[tuple[dict, dict]]:
    if not DATABASE_FILE.exists():
        return []

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
                tags_json,
                summary_json,
                long_summary_json
            FROM cases
            ORDER BY id ASC
            """
        ).fetchall()

    cases: list[tuple[dict, dict]] = []

    for row in rows:
        raw_case = dict(row)

        try:
            raw_case["tags"] = json.loads(raw_case.pop("tags_json") or "[]")
        except json.JSONDecodeError:
            raw_case["tags"] = []

        try:
            summary = json.loads(raw_case.pop("summary_json") or "{}")
        except json.JSONDecodeError:
            summary = {}

        try:
            long_summary = json.loads(raw_case.pop("long_summary_json") or "{}")
        except json.JSONDecodeError:
            long_summary = {}

        if "long" not in summary:
            summary = {
                "short": {
                    "summary": raw_case.get("short_summary", ""),
                },
                "long": long_summary,
            }

        cases.append((normalise_case(raw_case), summary))

    return cases


def summary_pdf_path(case: dict) -> Path | None:
    summary_pdf = case.get("summary_pdf")

    if not summary_pdf:
        return None

    path = BASE_DIR / summary_pdf
    return path if path.exists() else None


def main() -> None:
    if not firebase_configured():
        raise SystemExit(
            "Firebase is not configured. Set FIREBASE_SERVICE_ACCOUNT_JSON "
            "or FIREBASE_SERVICE_ACCOUNT_PATH first."
        )

    cases = load_local_cases()
    saved = 0

    for case, summary in cases:
        files = {}
        long_pdf = summary_pdf_path(case)

        if long_pdf:
            files["long_summary_pdf"] = long_pdf

        doc_id = save_case(case, summary, files)

        if doc_id:
            saved += 1
            print(f"[firebase] saved {doc_id}")

    print(f"[firebase] synced {saved} cases")


if __name__ == "__main__":
    main()
