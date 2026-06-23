from __future__ import annotations

import json
import os
from pathlib import Path

from apify import Actor

import main as pipeline


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILES = {
    "DIGEST_DATA": ("digest_data.js", "application/javascript; charset=utf-8"),
    "CASES_SUMMARY": ("cases_summary.json", "application/json"),
    "SCRAPER_STATUS": ("scraper_status.json", "application/json"),
    "TOKEN_LOG": ("token_log.json", "application/json"),
    "LEGAL_DIGEST_DB": ("legal_digest.db", "application/vnd.sqlite3"),
}


def apply_actor_input(actor_input: dict) -> None:
    demo_date = actor_input.get("demoDate")
    summary_detail = actor_input.get("summaryDetail")
    openai_model = actor_input.get("openaiModel")

    if demo_date:
        os.environ["DEMO_DATE"] = str(demo_date)

    if summary_detail:
        os.environ["SUMMARY_DETAIL"] = str(summary_detail)

    if openai_model:
        os.environ["OPENAI_MODEL"] = str(openai_model)

    os.environ.setdefault("CI", "true")


def read_json_file(path: Path, default):
    if not path.exists():
        return default

    return json.loads(path.read_text(encoding="utf-8"))


async def publish_file_outputs() -> dict:
    published = {}

    for key, (filename, content_type) in OUTPUT_FILES.items():
        path = BASE_DIR / filename

        if not path.exists():
            Actor.log.warning("Output file missing: %s", filename)
            continue

        if content_type == "application/json":
            value = read_json_file(path, {})
        elif content_type == "application/vnd.sqlite3":
            value = path.read_bytes()
        else:
            value = path.read_text(encoding="utf-8")

        await Actor.set_value(key, value, content_type=content_type)
        published[key] = filename

    return published


async def publish_cases_to_dataset(cases: list[dict]) -> None:
    if not cases:
        return

    dataset = await Actor.open_dataset()

    for case in cases:
        await dataset.push_data(case)


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}

        if not isinstance(actor_input, dict):
            actor_input = {}

        apply_actor_input(actor_input)
        Actor.log.info("Starting legal digest pipeline")

        pipeline.main()

        cases_summary = read_json_file(BASE_DIR / "cases_summary.json", {"cases": []})
        cases = cases_summary.get("cases", [])

        if not isinstance(cases, list):
            cases = []

        published = await publish_file_outputs()
        await publish_cases_to_dataset(cases)

        await Actor.set_value(
            "OUTPUT",
            {
                "case_count": len(cases),
                "published_files": published,
            },
            content_type="application/json",
        )

        Actor.log.info("Legal digest pipeline finished with %d cases", len(cases))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
