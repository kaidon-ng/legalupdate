from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from scraper_utils import (
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

SOURCES = {
    "bailii_admlty": {
        "name": "EWHC Admiralty",
        "base_url": "https://www.bailii.org/ew/cases/EWHC/Admlty/",
        "pattern": re.compile(r"/(?:ew/)?cases/EWHC/Admlty/(\d{4})/(\d+)\.html$"),
        "filename": lambda year, number: f"[{year}] EWHC {number} (Admlty).pdf",
    },
    "bailii_uksc": {
        "name": "UK Supreme Court",
        "base_url": "https://www.bailii.org/uk/cases/UKSC/",
        "pattern": re.compile(r"/(?:uk/)?cases/UKSC/(\d{4})/(\d+)\.html$"),
        "filename": lambda year, number: f"[{year}] UKSC {number}.pdf",
    },
}


def log(message: str) -> None:
    print(message, flush=True)


def parse_case_date(text: str):
    match = DATE_PATTERN.search(text)

    if not match:
        return None

    return datetime.strptime(match.group(1), "%d %B %Y").date()


def absolute_url(listing_url: str, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href

    return urljoin(listing_url, href)


def citation_filename(source: dict, html_url: str) -> str:
    match = source["pattern"].search(html_url)

    if not match:
        return f"{source['name'].lower().replace(' ', '-')}-judgment.pdf"

    year, number = match.groups()
    return source["filename"](year, number)


def download_pdf(case_page, source: dict, html_url: str):
    pdf_url = html_url.removesuffix(".html") + ".pdf"
    pdf_path = unique_path(DATA_DIR / citation_filename(source, html_url))
    response = case_page.request.get(pdf_url)

    if not response.ok:
        raise RuntimeError(f"PDF request failed with HTTP {response.status}: {pdf_url}")

    pdf_path.write_bytes(response.body())
    write_url_sidecar(pdf_path, html_url)
    return pdf_path


def open_bailii_page(page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    wait_out_bailii_challenge(page)
    page.locator('a[title="BAILII Home Page"]').wait_for(
        state="attached",
        timeout=30_000,
    )


def scrape_source(context, source_key: str, source: dict, processed_urls: set[str]) -> None:
    today = get_today()
    window_start, window_end = weekly_window(today)
    source_url = f"{source['base_url']}{today.year}/"
    cases_downloaded = 0
    cases_seen = 0
    listing_page = context.new_page()

    write_status(source_key, "running", "", 0)
    log(f"[{source_key}] Start: {source_url}")

    try:
        try:
            open_bailii_page(listing_page, source_url)
        except Exception:
            page_text = listing_page.locator("body").inner_text(timeout=5_000)
            write_status(source_key, "down", explain_error(page_text, source["name"]), 0)
            return

        case_items = listing_page.locator("ul li")
        item_count = case_items.count()
        log(f"[{source_key}] Found {item_count} list items")

        if item_count == 0:
            page_text = listing_page.locator("body").inner_text(timeout=5_000)
            write_status(source_key, "down", explain_error(page_text, source["name"]), 0)
            return

        try:
            for item_index in range(item_count):
                case_item = listing_page.locator("ul li").nth(item_index)
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

                html_url = absolute_url(listing_page.url, href)

                if html_url in processed_urls:
                    log(f"[{source_key}] Duplicate: {html_url}")
                    cases_seen += 1
                    continue

                log(f"[{source_key}] Open: {case_date.isoformat()} - {first_link.inner_text(timeout=10_000).strip()}")
                case_page = context.new_page()

                try:
                    open_bailii_page(case_page, html_url)
                    html_url = case_page.url

                    if html_url in processed_urls:
                        log(f"[{source_key}] Duplicate: {html_url}")
                        cases_seen += 1
                        continue

                    pdf_path = download_pdf(case_page, source, html_url)
                    processed_urls.add(html_url)
                    cases_downloaded += 1
                    cases_seen += 1
                    log(f"[{source_key}] Download: {pdf_path.name}")
                finally:
                    case_page.close()
        except Exception as error:
            if cases_seen > 0:
                write_status(source_key, "partial", str(error), cases_downloaded)
                return
            raise
    except Exception as error:
        write_status(source_key, "failed", str(error), cases_downloaded)
        return
    finally:
        listing_page.close()

    write_status(source_key, "ok", "Finished", cases_downloaded)


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    processed_urls = load_processed_urls(DATA_DIR)

    log(f"[duplicates] Loaded {len(processed_urls)} processed URLs")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**bailii_launch_kwargs(is_headless()))

        try:
            context = new_bailii_context(browser)

            for source_key, source in SOURCES.items():
                scrape_source(context, source_key, source, processed_urls)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
