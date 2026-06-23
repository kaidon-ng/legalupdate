from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from scraper_utils import (
    BAILII_CHALLENGE_TITLES,
    DATA_DIR,
    bailii_launch_kwargs,
    explain_error,
    get_today,
    is_headless,
    load_processed_urls,
    new_bailii_context,
    unique_path,
    wait_out_bailii_challenge,
    weekly_window,
    write_status,
    write_url_sidecar,
)


DATE_PATTERN = re.compile(r"\((\d{1,2}\s+[A-Za-z]+\s+\d{4})\)")
CASE_URL_PATTERN = re.compile(r"/(?:ew/)?cases/EWHC/Comm/(\d{4})/(\d+)\.html$")


def log(message: str) -> None:
    print(message, flush=True)


def listing_url(year: int) -> str:
    return f"https://www.bailii.org/ew/cases/EWHC/Comm/{year}/"


def parse_case_date(text: str):
    match = DATE_PATTERN.search(text)

    if not match:
        return None

    return datetime.strptime(match.group(1), "%d %B %Y").date()


def citation_filename(html_url: str) -> str:
    match = CASE_URL_PATTERN.search(html_url)

    if not match:
        return "bailii-commercial-judgment.pdf"

    year, number = match.groups()
    return f"[{year}] EWHC {number} (Comm).pdf"


def download_pdf(page, html_url: str):
    pdf_url = html_url.removesuffix(".html") + ".pdf"
    pdf_path = unique_path(DATA_DIR / citation_filename(html_url))
    response = page.request.get(pdf_url)

    if not response.ok:
        raise RuntimeError(f"PDF request failed with HTTP {response.status}: {pdf_url}")

    pdf_path.write_bytes(response.body())
    write_url_sidecar(pdf_path, html_url)
    return pdf_path


def open_listing(page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    wait_out_bailii_challenge(page)
    page.locator("body").wait_for(state="visible", timeout=30_000)


def scrape() -> tuple[str, str, int]:
    DATA_DIR.mkdir(exist_ok=True)
    today = get_today()
    window_start, window_end = weekly_window(today)
    source_url = listing_url(today.year)
    processed_urls = load_processed_urls(DATA_DIR)
    cases_downloaded = 0
    cases_seen = 0

    log(f"[window] {window_start.isoformat()} to {window_end.isoformat()}")
    log(f"[duplicates] Loaded {len(processed_urls)} processed URLs")
    log(f"[start] {source_url}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**bailii_launch_kwargs(is_headless()))

        try:
            context = new_bailii_context(browser)
            page = context.new_page()

            try:
                open_listing(page, source_url)
            except PlaywrightTimeoutError:
                page_text = page.locator("body").inner_text(timeout=5_000)
                return "down", explain_error(page_text, "BAILII Commercial Court"), 0

            if page.title() in BAILII_CHALLENGE_TITLES:
                return "down", "BAILII challenge page did not clear.", 0

            case_items = page.locator("li")
            item_count = case_items.count()
            log(f"[listing] Found {item_count} list items")

            if item_count == 0:
                page_text = page.locator("body").inner_text(timeout=5_000)
                return "down", explain_error(page_text, "BAILII Commercial Court"), 0

            try:
                for item_index in range(item_count):
                    case_item = page.locator("li").nth(item_index)
                    item_text = case_item.inner_text(timeout=10_000)
                    case_date = parse_case_date(item_text)

                    if case_date is None or case_date < window_start or case_date > window_end:
                        continue

                    first_link = case_item.locator("a").first

                    if first_link.count() == 0:
                        continue

                    href = first_link.get_attribute("href")

                    if not href:
                        continue

                    html_url = urljoin(page.url, href)

                    if html_url in processed_urls:
                        log(f"[duplicate] {html_url}")
                        cases_seen += 1
                        continue

                    log(f"[open] {case_date.isoformat()} - {first_link.inner_text(timeout=10_000).strip()}")

                    try:
                        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                            first_link.click()
                    except PlaywrightTimeoutError:
                        page.goto(html_url, wait_until="domcontentloaded", timeout=45_000)

                    wait_out_bailii_challenge(page)
                    html_url = page.url
                    pdf_path = download_pdf(page, html_url)
                    processed_urls.add(html_url)
                    cases_downloaded += 1
                    cases_seen += 1
                    log(f"[download] {pdf_path.name}")

                    page.go_back(wait_until="domcontentloaded", timeout=30_000)
                    wait_out_bailii_challenge(page)
            except Exception as error:
                if cases_seen > 0:
                    return "partial", str(error), cases_downloaded
                raise
        finally:
            browser.close()

    return "ok", "Finished", cases_downloaded


def main() -> None:
    write_status("bailii_comm", "running", "", 0)

    try:
        status, message, cases = scrape()
    except Exception as error:
        write_status("bailii_comm", "failed", str(error), 0)
        raise SystemExit(1) from error

    write_status("bailii_comm", status, message, cases)


if __name__ == "__main__":
    main()
