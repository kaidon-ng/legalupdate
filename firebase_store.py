from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


DEFAULT_COLLECTION = "cases"


def firebase_configured() -> bool:
    return bool(
        os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        or os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    )


def storage_configured() -> bool:
    return bool(os.getenv("FIREBASE_STORAGE_BUCKET"))


def _service_account_credential():
    from firebase_admin import credentials

    raw_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if raw_json:
        info = json.loads(raw_json)
        return credentials.Certificate(info)

    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

    if not service_account_path:
        raise RuntimeError("Firebase service account credentials are not configured")

    return credentials.Certificate(service_account_path)


def _storage_bucket_name() -> str:
    bucket = os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()
    return bucket.removeprefix("gs://").rstrip("/")


def get_firebase_app():
    import firebase_admin

    if firebase_admin._apps:
        return firebase_admin.get_app()

    options: dict[str, str] = {}
    bucket_name = _storage_bucket_name()

    if bucket_name:
        options["storageBucket"] = bucket_name

    return firebase_admin.initialize_app(
        _service_account_credential(),
        options or None,
    )


def firestore_client():
    if not firebase_configured():
        return None

    get_firebase_app()

    from firebase_admin import firestore

    return firestore.client()


def storage_bucket():
    if not firebase_configured() or not storage_configured():
        return None

    get_firebase_app()

    from firebase_admin import storage

    return storage.bucket()


def safe_id(value: str, default: str = "case") -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return cleaned[:80] or default


def case_document_id(case: dict[str, Any]) -> str:
    key = case.get("source_url") or case.get("case_ref") or case.get("folder_name") or "case"
    digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:24]
    prefix = safe_id(case.get("case_ref") or case.get("folder_name") or "case")
    return f"{prefix}-{digest}"


def upload_file(local_path: Path, storage_path: str) -> dict[str, str] | None:
    bucket = storage_bucket()

    if bucket is None or not local_path.exists():
        return None

    content_type, _ = mimetypes.guess_type(local_path.name)
    blob = bucket.blob(storage_path)
    blob.upload_from_filename(str(local_path), content_type=content_type)

    return {
        "bucket": bucket.name,
        "path": storage_path,
        "gs_url": f"gs://{bucket.name}/{storage_path}",
        "content_type": content_type or "application/octet-stream",
    }


def upload_case_files(case: dict[str, Any], files: dict[str, Path]) -> dict[str, dict[str, str]]:
    uploaded: dict[str, dict[str, str]] = {}
    folder_name = safe_id(case.get("folder_name") or case_document_id(case))

    for label, path in files.items():
        if not path or not path.exists():
            continue

        storage_path = f"judgments/{folder_name}/{path.name}"
        file_record = upload_file(path, storage_path)

        if file_record:
            uploaded[label] = file_record

    return uploaded


def save_case(
    case: dict[str, Any],
    summary: dict[str, Any],
    files: dict[str, Path] | None = None,
) -> str | None:
    db = firestore_client()

    if db is None:
        return None

    uploaded_files = upload_case_files(case, files or {})
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    doc_id = case_document_id(case)
    collection_name = os.getenv("FIREBASE_CASES_COLLECTION", DEFAULT_COLLECTION)
    payload = {
        **case,
        "summary": summary,
        "files": uploaded_files,
        "long_summary_pdf": uploaded_files.get("long_summary_pdf", {}),
        "updated_at": now,
    }

    payload.setdefault("created_at", now)

    db.collection(collection_name).document(doc_id).set(payload, merge=True)
    return doc_id
