from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from scraper_utils import (
    BASE_DIR,
    DATA_DIR,
    STATUS_FILE,
    get_today,
    invoke_openai,
    llm_ready,
    read_json,
    write_json,
)


DATA_PROCESSED_DIR = BASE_DIR / "data_processed"
SUMMARY_PDFS_DIR = BASE_DIR / "summary_pdfs"
CASES_SUMMARY_FILE = BASE_DIR / "cases_summary.json"
DIGEST_DATA_FILE = BASE_DIR / "digest_data.js"
DATABASE_FILE = BASE_DIR / "legal_digest.db"

LEGAL_TAGS = {
    "criminal": "Criminal law, criminal procedure, offences, bail, sentencing, appeals against conviction or sentence.",
    "family": "Family law, divorce, custody, care and control, matrimonial assets, maintenance, adoption, child welfare.",
    "employment": "Employment law, workplace disputes, termination, restraint of trade, employee duties, wages, discrimination.",
    "contract": "Contract law, commercial contracts, sale of goods, agency, arbitration, trade finance, commodities, business disputes.",
    "data-protection": "Data protection, privacy, personal data, confidentiality, cybersecurity, regulatory privacy duties.",
    "shipping": "Shipping, admiralty, maritime, carriage of goods by sea, bills of lading, charterparties, marine insurance, collision, salvage, demurrage, laytime.",
}

SHORT_PROMPT = """
Convert the supplied court decision text into structured JSON for a legal digest for a regular non-lawyer reader.

Use only the supplied text. Do not add external information.
Use plain English. Avoid legal jargon where possible. If a legal term is necessary, explain it briefly.

Return only valid JSON in this shape:

{
  "case_name": "",
  "parties": "",
  "case_ref": "",
  "date": "",
  "court": "",
  "regular_summary": "",
  "key_facts": "",
  "significance": "",
  "tags": []
}

Field guidance:
- regular_summary: 3-5 plain-English sentences explaining what happened, who won or lost, and why it matters.
- key_facts: 3-5 sentences on the background and dispute.
- significance: 2-3 plain-English sentences on practical importance.
- tags: zero or more of these exact strings only: criminal, family, employment, contract, data-protection, shipping.
""".strip()

LONG_PROMPT = """
Convert the supplied court decision text into a detailed structured case note.

Use only the supplied text. If a field is not addressed, return an empty string.
Return only valid JSON in this shape:

{
  "case_name": "",
  "parties": "",
  "case_ref": "",
  "date": "",
  "court": "",
  "jurisdiction": "",
  "area_of_law": "",
  "legal_question": "",
  "key_facts": "",
  "holding": "",
  "lawyer_summary": "",
  "significance": "",
  "precedent_impact": "",
  "dissent": "",
  "tags": []
}

Field guidance:
- legal_question: 2-4 sentences.
- key_facts: 6-10 sentences.
- holding: 5-8 sentences on the decision and reasoning.
- lawyer_summary: 4-6 sentences written for lawyers, covering the outcome, reasoning, legal issue, and practical significance.
- significance: 3-5 sentences on practical legal importance.
- dissent: empty string if there is no dissent.
- tags: zero or more of these exact strings only: criminal, family, employment, contract, data-protection, shipping.
""".strip()


def extract_pdf_text(pdf_path: Path) -> str:
    import fitz

    text_parts: list[str] = []

    with fitz.open(pdf_path) as document:
        for page in document:
            text_parts.append(page.get_text())

    return "\n\n".join(text_parts).strip()


def strip_markdown_fences(value: str) -> str:
    cleaned = value.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    return cleaned.strip()


def parse_model_json(value: str) -> dict:
    cleaned = strip_markdown_fences(value)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

        if not match:
            raise

        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("OpenAI response was not a JSON object")

    return parsed


def prompt_with_tags(prompt_template: str, text: str) -> str:
    tag_guidance = "\n".join(f"- {tag}: {description}" for tag, description in LEGAL_TAGS.items())
    return (
        f"{prompt_template}\n\n"
        "Legal digest tag vocabulary:\n"
        f"{tag_guidance}\n\n"
        "Only include a tag if the supplied judgment text supports it.\n\n"
        f"Court decision text:\n{text[:65000]}"
    )


def summarize_with_prompt(prompt_template: str, text: str, max_output_tokens: int) -> dict:
    if not llm_ready():
        raise RuntimeError("No AI provider is configured")

    response = invoke_openai(
        prompt_with_tags(prompt_template, text),
        max_output_tokens=max_output_tokens,
    )
    return parse_model_json(response)


def summarize_judgment(text: str) -> tuple[dict, dict]:
    short_summary = summarize_with_prompt(SHORT_PROMPT, text, 1200)
    long_summary = summarize_with_prompt(LONG_PROMPT, text, 3200)
    return short_summary, long_summary


def infer_source_id(source_url: str) -> str:
    lowered = source_url.lower()

    if "/uksc/" in lowered:
        return "bailii_uksc"

    if "/ewhc/comm/" in lowered:
        return "bailii_comm"

    if "/ewhc/admlty/" in lowered:
        return "bailii_admlty"

    if "elitigation.sg" in lowered:
        return "singapore"

    return "singapore"


def slugify(value: str, default: str = "case") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or default


def make_folder_name(summary: dict, pdf_path: Path) -> str:
    return slugify(summary.get("case_ref") or summary.get("case_name") or pdf_path.stem)


def first_sentences(value: str, count: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", value.strip())
    return " ".join(sentence for sentence in sentences[:count] if sentence)


def normalise_tags(raw_tags) -> list[str]:
    valid_tags = set(LEGAL_TAGS)

    if isinstance(raw_tags, str):
        raw_tags = re.split(r"[,;/\n]+", raw_tags)

    if not isinstance(raw_tags, list):
        return []

    tags: list[str] = []

    for raw_tag in raw_tags:
        tag = str(raw_tag).strip().lower().replace("_", "-")

        if tag in valid_tags and tag not in tags:
            tags.append(tag)

    return tags


def merge_tags(*summaries: dict) -> list[str]:
    tags: list[str] = []

    for summary in summaries:
        for tag in normalise_tags(summary.get("tags", [])):
            if tag not in tags:
                tags.append(tag)

    return tags


def short_summary_text(summary: dict) -> str:
    if summary.get("regular_summary"):
        return str(summary["regular_summary"]).strip()

    parts = [
        summary.get("judgment", ""),
        summary.get("key_facts", ""),
        summary.get("significance", ""),
    ]
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def build_case(
    short_summary: dict,
    long_summary: dict,
    folder_name: str,
    source_url: str,
) -> dict:
    holding = long_summary.get("holding", "")
    regular_summary = short_summary_text(short_summary) or first_sentences(holding, 2)
    lawyer_summary = (
        long_summary.get("lawyer_summary")
        or long_summary.get("holding")
        or long_summary.get("significance")
        or regular_summary
    )

    return {
        "folder_name": folder_name,
        "source_id": infer_source_id(source_url),
        "case_name": short_summary.get("case_name") or long_summary.get("case_name", ""),
        "parties": short_summary.get("parties") or long_summary.get("parties", ""),
        "case_ref": short_summary.get("case_ref") or long_summary.get("case_ref", ""),
        "date": short_summary.get("date") or long_summary.get("date", ""),
        "court": short_summary.get("court") or long_summary.get("court", ""),
        "regular_summary": regular_summary,
        "lawyer_summary": lawyer_summary,
        "short_summary": regular_summary,
        "summary_pdf": "",
        "summary_pdf_name": "",
        "judgment": regular_summary,
        "holding": holding,
        "source_url": source_url,
        "tags": merge_tags(short_summary, long_summary),
    }


def long_summary_sections(summary: dict) -> list[tuple[str, str]]:
    return [
        ("Jurisdiction", summary.get("jurisdiction", "")),
        ("Area of law", summary.get("area_of_law", "")),
        ("Legal question", summary.get("legal_question", "")),
        ("Key facts", summary.get("key_facts", "")),
        ("Holding", summary.get("holding", "")),
        ("Significance", summary.get("significance", "")),
        ("Precedent impact", summary.get("precedent_impact", "")),
        ("Dissent", summary.get("dissent", "")),
    ]


def generate_long_summary_pdf(case: dict, long_summary: dict) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    summary_dir = SUMMARY_PDFS_DIR / case["folder_name"]
    summary_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_summary_pdf_name(case)
    pdf_path = summary_dir / filename
    styles = getSampleStyleSheet()
    story = [
        Paragraph(case.get("case_name") or "Long Summary", styles["Title"]),
        Paragraph(case.get("case_ref") or "", styles["Heading3"]),
        Paragraph(case.get("court") or "", styles["Normal"]),
        Spacer(1, 12),
    ]

    for heading, value in long_summary_sections(long_summary):
        if not value:
            continue

        story.extend(
            [
                Paragraph(heading, styles["Heading2"]),
                Paragraph(str(value).replace("\n", "<br/>"), styles["BodyText"]),
                Spacer(1, 10),
            ]
        )

    if case.get("source_url"):
        story.extend(
            [
                Paragraph("Full judgment URL", styles["Heading2"]),
                Paragraph(case["source_url"], styles["BodyText"]),
            ]
        )

    document = SimpleDocTemplate(str(pdf_path), pagesize=A4)
    document.build(story)
    return pdf_path


def safe_summary_pdf_name(case: dict) -> str:
    base = case.get("case_ref") or case.get("case_name") or case["folder_name"]
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", base)
    filename = re.sub(r"\s+", " ", filename).strip().rstrip(" .")
    return f"{filename or 'case'} - long summary.pdf"


def init_database() -> None:
    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_key TEXT NOT NULL UNIQUE,
                folder_name TEXT NOT NULL,
                source_id TEXT NOT NULL,
                case_name TEXT,
                parties TEXT,
                case_ref TEXT,
                date TEXT,
                court TEXT,
                judgment TEXT,
                holding TEXT,
                source_url TEXT,
                tags_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_column(connection, "cases", "short_summary", "TEXT")
        ensure_column(connection, "cases", "regular_summary", "TEXT")
        ensure_column(connection, "cases", "lawyer_summary", "TEXT")
        ensure_column(connection, "cases", "summary_pdf_path", "TEXT")
        ensure_column(connection, "cases", "summary_pdf_name", "TEXT")
        ensure_column(connection, "cases", "long_summary_json", "TEXT")
        backfill_audience_summaries(connection)


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def backfill_audience_summaries(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE cases
        SET regular_summary = COALESCE(NULLIF(regular_summary, ''), NULLIF(short_summary, ''), NULLIF(judgment, ''), ''),
            lawyer_summary = COALESCE(NULLIF(lawyer_summary, ''), NULLIF(holding, ''), NULLIF(short_summary, ''), NULLIF(judgment, ''), '')
        """
    )


def save_case_to_database(case: dict, short_summary: dict, long_summary: dict) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    case_key = case.get("source_url") or case["folder_name"]
    summary_payload = {
        "short": short_summary,
        "long": long_summary,
    }

    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute(
            """
            INSERT INTO cases (
                case_key,
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
                long_summary_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_key) DO UPDATE SET
                folder_name = excluded.folder_name,
                source_id = excluded.source_id,
                case_name = excluded.case_name,
                parties = excluded.parties,
                case_ref = excluded.case_ref,
                date = excluded.date,
                court = excluded.court,
                judgment = excluded.judgment,
                holding = excluded.holding,
                source_url = excluded.source_url,
                short_summary = excluded.short_summary,
                regular_summary = excluded.regular_summary,
                lawyer_summary = excluded.lawyer_summary,
                summary_pdf_path = excluded.summary_pdf_path,
                summary_pdf_name = excluded.summary_pdf_name,
                tags_json = excluded.tags_json,
                summary_json = excluded.summary_json,
                long_summary_json = excluded.long_summary_json,
                updated_at = excluded.updated_at
            """,
            (
                case_key,
                case["folder_name"],
                case["source_id"],
                case["case_name"],
                case["parties"],
                case["case_ref"],
                case["date"],
                case["court"],
                case["judgment"],
                case["holding"],
                case["source_url"],
                case["short_summary"],
                case["regular_summary"],
                case["lawyer_summary"],
                case["summary_pdf"],
                case["summary_pdf_name"],
                json.dumps(case["tags"]),
                json.dumps(summary_payload, ensure_ascii=True),
                json.dumps(long_summary, ensure_ascii=True),
                now,
                now,
            ),
        )


def save_case_to_firebase(
    case: dict,
    short_summary: dict,
    long_summary: dict,
    summary_pdf_path: Path,
) -> None:
    try:
        from firebase_store import save_case

        doc_id = save_case(
            case,
            {
                "short": short_summary,
                "long": long_summary,
            },
            {
                "long_summary_pdf": summary_pdf_path,
            },
        )
    except Exception as error:
        print(f"[firebase] Failed to save {case.get('case_ref') or case['folder_name']}: {error}", flush=True)
        return

    if doc_id:
        print(f"[firebase] Saved {doc_id}", flush=True)


def load_cases_from_database() -> list[dict]:
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
                tags_json
            FROM cases
            ORDER BY date DESC, created_at DESC, id DESC
            """
        ).fetchall()

    cases: list[dict] = []

    for row in rows:
        case = dict(row)
        case["summary_pdf"] = case.pop("summary_pdf_path") or ""

        try:
            case["tags"] = json.loads(case.pop("tags_json") or "[]")
        except json.JSONDecodeError:
            case["tags"] = []

        cases.append(case)

    return cases


def read_source_url(pdf_path: Path) -> str:
    url_path = pdf_path.with_suffix(".url")

    if not url_path.exists():
        return ""

    return url_path.read_text(encoding="utf-8").strip()


def unique_processed_folder(folder_name: str) -> Path:
    target = DATA_PROCESSED_DIR / folder_name

    if not target.exists():
        return target

    counter = 2

    while True:
        candidate = DATA_PROCESSED_DIR / f"{folder_name}-{counter}"

        if not candidate.exists():
            return candidate

        counter += 1


def move_processed_files(pdf_path: Path, txt_path: Path, url_path: Path, folder_name: str) -> str:
    target_dir = unique_processed_folder(folder_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    for path in (pdf_path, txt_path, url_path):
        if path.exists():
            shutil.move(str(path), str(target_dir / path.name))

    return target_dir.name


def source_warnings() -> dict:
    status = read_json(STATUS_FILE, {})
    warnings = {}

    for source_id, entry in status.items():
        if not isinstance(entry, dict):
            continue

        if entry.get("status") not in {"ok", "pending", "running"}:
            warnings[source_id] = entry.get("message") or entry.get("status", "unknown")

    return warnings


def today_display() -> str:
    return get_today().strftime("%d %B %Y").lstrip("0")


def file_map_for_cases(cases: list[dict]) -> dict[str, list[str]]:
    file_map: dict[str, list[str]] = {}

    for case in cases:
        summary_pdf = case.get("summary_pdf")

        if summary_pdf:
            file_map[case["folder_name"]] = [summary_pdf]

    return file_map


def write_outputs(cases: list[dict]) -> None:
    write_json(CASES_SUMMARY_FILE, {"cases": cases})
    payload = {
        "today_str": today_display(),
        "source_warnings": source_warnings(),
        "file_map": file_map_for_cases(cases),
        "cases": cases,
    }
    DIGEST_DATA_FILE.write_text(
        "window.LEGAL_DIGEST_DATA = "
        + json.dumps(payload, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def process_pdf(pdf_path: Path) -> dict:
    print(f"[summarize] {pdf_path.name}", flush=True)
    source_url = read_source_url(pdf_path)
    text = extract_pdf_text(pdf_path)
    txt_path = pdf_path.with_suffix(".txt")
    txt_path.write_text(text, encoding="utf-8")
    short_summary, long_summary = summarize_judgment(text)
    folder_name = make_folder_name(short_summary or long_summary, pdf_path)
    case = build_case(short_summary, long_summary, folder_name, source_url)
    final_folder_name = move_processed_files(
        pdf_path,
        txt_path,
        pdf_path.with_suffix(".url"),
        folder_name,
    )
    case["folder_name"] = final_folder_name
    processed_dir = DATA_PROCESSED_DIR / final_folder_name
    summary_pdf_path = generate_long_summary_pdf(case, long_summary)
    case["summary_pdf"] = str(summary_pdf_path.relative_to(BASE_DIR)).replace("\\", "/")
    case["summary_pdf_name"] = summary_pdf_path.name
    save_case_to_database(case, short_summary, long_summary)
    save_case_to_firebase(
        case,
        short_summary,
        long_summary,
        summary_pdf_path,
    )
    return case


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    DATA_PROCESSED_DIR.mkdir(exist_ok=True)
    SUMMARY_PDFS_DIR.mkdir(exist_ok=True)
    init_database()
    pdf_paths = sorted(DATA_DIR.glob("*.pdf"))

    if not pdf_paths:
        write_outputs(load_cases_from_database())
        print("[summarize] No PDFs found")
        return

    cases: list[dict] = []

    for pdf_path in pdf_paths:
        try:
            cases.append(process_pdf(pdf_path))
        except Exception as error:
            print(f"[summarize] Failed {pdf_path.name}: {error}", flush=True)
            continue

    write_outputs(load_cases_from_database())
    print(f"[summarize] Wrote {len(cases)} cases")


if __name__ == "__main__":
    main()
