from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scraper_utils import DEFAULT_STATUS, TOKEN_LOG_FILE, write_json, write_status


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_PROCESSED_DIR = BASE_DIR / "data_processed"
SUMMARY_PDFS_DIR = BASE_DIR / "summary_pdfs"
STATUS_FILE = BASE_DIR / "scraper_status.json"

SCRAPER_RUNS = [
    ("singapore_judiciary_scrape.py", ["singapore"]),
    ("bailii_comm.py", ["bailii_comm"]),
    ("bailii_uksc_admlty.py", ["bailii_uksc", "bailii_admlty"]),
]
SUMMARIZER_SCRIPT = "summarizer.py"


def create_folders() -> None:
    for folder in (DATA_DIR, DATA_PROCESSED_DIR, SUMMARY_PDFS_DIR):
        folder.mkdir(exist_ok=True)


def initialize_files() -> None:
    write_json(STATUS_FILE, DEFAULT_STATUS)
    write_json(TOKEN_LOG_FILE, {"input": 0, "output": 0})


def run_scraper(script_name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BASE_DIR / script_name)],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def run_summarizer() -> None:
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / SUMMARIZER_SCRIPT)],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout.strip():
        print(result.stdout.strip())

    if result.returncode != 0:
        message = result.stderr.strip() or f"Exited with code {result.returncode}"
        print(f"[summarize] Failed: {message}")


def mark_failed_if_needed(scraper_keys: list[str], result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode == 0:
        return

    message = result.stderr.strip() or f"Exited with code {result.returncode}"

    for scraper_key in scraper_keys:
        write_status(scraper_key, "failed", message, 0)


def print_status_summary() -> None:
    status = DEFAULT_STATUS

    if STATUS_FILE.exists():
        import json

        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))

    print("\nScraper status summary:")

    for scraper_key, entry in status.items():
        line = f"- {scraper_key}: {entry['status']} ({entry['cases']} cases)"

        if entry.get("message"):
            line += f" - {entry['message']}"

        print(line)


def main() -> None:
    create_folders()
    initialize_files()

    for script_name, scraper_keys in SCRAPER_RUNS:
        for scraper_key in scraper_keys:
            write_status(scraper_key, "running", "", 0)

        try:
            result = run_scraper(script_name)
        except Exception as error:
            for scraper_key in scraper_keys:
                write_status(scraper_key, "failed", str(error), 0)
            continue

        mark_failed_if_needed(scraper_keys, result)

    run_summarizer()
    print_status_summary()


if __name__ == "__main__":
    main()
