from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from scraper_utils import (
    DATA_DIR,
    explain_error,
    get_today,
    is_headless,
    load_processed_urls,
    safe_filename,
    unique_path,
    weekly_window,
    write_status,
    write_url_sidecar,
)


START_URL = "https://www.elitigation.sg/gd/"
MAIN_CONTAINER = "#bodyContainer"
CASE_CARD = f"{MAIN_CONTAINER} .card.col-12"
DATE_PATTERN = re.compile(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})")
DOWNLOAD_TEXT = re.compile(r"Download PDF", re.IGNORECASE)


def log(message: str) -> None:
    print(message, flush=True)


def parse_decision_date(raw_text: str):
    match = DATE_PATTERN.search(raw_text)

    if not match:
        return None

    return datetime.strptime(match.group(1), "%d %b %Y").date()


def download_pdf(popup: Page, data_dir: Path) -> Path:
    download_link = popup.locator("a.nav-item.nav-link").filter(
        has_text=DOWNLOAD_TEXT
    ).first
    download_link.wait_for(state="visible", timeout=20_000)

    with popup.expect_download(timeout=30_000) as download_info:
        download_link.click()

    download = download_info.value
    filename = safe_filename(download.suggested_filename or "singapore-judgment.pdf")
    pdf_path = unique_path(data_dir / filename)
    download.save_as(str(pdf_path))
    return pdf_path


def process_card(
    page: Page,
    context: BrowserContext,
    card_index: int,
    processed_urls: set[str],
    window_start,
    window_end,
) -> tuple[str, int]:
    card = page.locator(CASE_CARD).nth(card_index)
    date_text = card.locator(".decision-date-link").first.inner_text(timeout=10_000)
    decision_date = parse_decision_date(date_text)

    if decision_date is None:
        log(f"[skip] Could not parse date from {date_text!r}")
        return "continue", 0

    title_link = card.locator("a.gd-heardertext").first
    title = re.sub(r"\s+", " ", title_link.inner_text(timeout=10_000).strip())

    if decision_date > window_end:
        log(f"[skip] {decision_date.isoformat()} is newer than today: {title}")
        return "continue", 0

    if decision_date < window_start:
        log(f"[stop] {decision_date.isoformat()} is older than weekly window: {title}")
        return "stop", 0

    log(f"[open] {decision_date.isoformat()} - {title}")
    popup: Page | None = None

    try:
        with page.expect_popup(timeout=20_000) as popup_info:
            title_link.click()

        popup = popup_info.value

        try:
            popup.wait_for_load_state("domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            log(f"[warn] Popup load wait timed out; continuing: {title}")

        judgment_url = popup.url

        if judgment_url in processed_urls:
            log(f"[duplicate] {judgment_url}")
            return "continue", 0

        popup.locator("body").wait_for(state="attached", timeout=20_000)

        pdf_path = download_pdf(popup, DATA_DIR)
        write_url_sidecar(pdf_path, judgment_url)
        processed_urls.add(judgment_url)
        log(f"[download] {pdf_path.name}")
        return "continue", 1
    finally:
        if popup is not None and not popup.is_closed():
            popup.close()


def go_to_next_page(page: Page) -> bool:
    next_link = page.locator("li.PagedList-skipToNext a[rel='next']").first

    if next_link.count() == 0:
        return False

    href = next_link.get_attribute("href")

    if not href:
        return False

    next_link.click()
    page.locator(MAIN_CONTAINER).wait_for(state="visible", timeout=30_000)
    return True


def scrape() -> tuple[str, str, int]:
    DATA_DIR.mkdir(exist_ok=True)
    today = get_today()
    window_start, window_end = weekly_window(today)
    processed_urls = load_processed_urls(DATA_DIR)
    cases_downloaded = 0
    cases_seen = 0
    should_stop = False

    log(f"[window] {window_start.isoformat()} to {window_end.isoformat()}")
    log(f"[duplicates] Loaded {len(processed_urls)} processed URLs")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=is_headless())

        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            log(f"[start] {START_URL}")
            page.goto(START_URL, wait_until="domcontentloaded", timeout=45_000)

            try:
                page.locator(MAIN_CONTAINER).wait_for(state="visible", timeout=30_000)
            except PlaywrightTimeoutError:
                page_text = page.locator("body").inner_text(timeout=5_000)
                return "down", explain_error(page_text, "Singapore Judiciary"), 0

            try:
                while not should_stop:
                    cards = page.locator(CASE_CARD)
                    card_count = cards.count()
                    log(f"[page] Found {card_count} cards")

                    for card_index in range(card_count):
                        action, downloaded = process_card(
                            page,
                            context,
                            card_index,
                            processed_urls,
                            window_start,
                            window_end,
                        )
                        cases_seen += 1
                        cases_downloaded += downloaded

                        if action == "stop":
                            should_stop = True
                            break

                    if should_stop:
                        break

                    if not go_to_next_page(page):
                        break
            except Exception as error:
                if cases_seen > 0:
                    return "partial", str(error), cases_downloaded
                raise
        finally:
            browser.close()

    return "ok", "Finished", cases_downloaded


def main() -> None:
    write_status("singapore", "running", "", 0)

    try:
        status, message, cases = scrape()
    except Exception as error:
        write_status("singapore", "failed", str(error), 0)
        raise SystemExit(1) from error

    write_status("singapore", status, message, cases)


if __name__ == "__main__":
    main()
