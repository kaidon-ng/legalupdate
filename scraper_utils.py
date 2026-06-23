from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATUS_FILE = BASE_DIR / "scraper_status.json"
TOKEN_LOG_FILE = BASE_DIR / "token_log.json"

STATUS_KEYS = ("singapore", "bailii_comm", "bailii_uksc", "bailii_admlty")
DEFAULT_STATUS = {
    key: {"status": "pending", "message": "", "cases": 0} for key in STATUS_KEYS
}

BAILII_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)
BAILII_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-extensions",
    "--no-first-run",
    "--disable-default-apps",
]
BAILII_CHALLENGE_TITLES = {"Oh noes!", "Making sure you're not a bot!"}


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback.copy()

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback.copy()

    return loaded if isinstance(loaded, dict) else fallback.copy()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_status(scraper_key: str, status: str, message: str = "", cases: int = 0) -> None:
    current = read_json(STATUS_FILE, DEFAULT_STATUS)

    for key in STATUS_KEYS:
        current.setdefault(key, {"status": "pending", "message": "", "cases": 0})

    current[scraper_key] = {
        "status": status,
        "message": message,
        "cases": int(cases),
    }
    write_json(STATUS_FILE, current)


def update_token_log(input_tokens: int = 0, output_tokens: int = 0) -> None:
    current = read_json(TOKEN_LOG_FILE, {"input": 0, "output": 0})
    current["input"] = int(current.get("input", 0)) + int(input_tokens or 0)
    current["output"] = int(current.get("output", 0)) + int(output_tokens or 0)
    write_json(TOKEN_LOG_FILE, current)


def get_today() -> date:
    demo_date = os.getenv("DEMO_DATE")

    if demo_date:
        return datetime.strptime(demo_date, "%Y-%m-%d").date()

    return date.today()


def weekly_window(today: date) -> tuple[date, date]:
    days_since_sunday = (today.weekday() + 1) % 7 or 7
    return today - timedelta(days=days_since_sunday), today


def is_headless() -> bool:
    return os.getenv("CI", "").lower() == "true"


def load_processed_urls(data_dir: Path = DATA_DIR) -> set[str]:
    processed_urls: set[str] = set()

    for url_file in data_dir.glob("*.url"):
        url = url_file.read_text(encoding="utf-8").strip()

        if url:
            processed_urls.add(url)

    return processed_urls


def safe_filename(value: str, default: str = "judgment") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.rstrip(" .") or default


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 2

    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")

        if not candidate.exists():
            return candidate

        counter += 1


def write_url_sidecar(pdf_path: Path, html_url: str) -> None:
    pdf_path.with_suffix(".url").write_text(html_url + "\n", encoding="utf-8")


def openai_ready() -> bool:
    api_key = os.getenv("OPENAI_API_KEY", "")
    return bool(api_key and "placeholder" not in api_key.lower())


def bedrock_ready() -> bool:
    return bool(
        os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        and os.getenv("AWS_REGION")
        and os.getenv("HAIKU_BEDROCK_MODEL_ID")
    )


def llm_provider() -> str:
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()

    if provider == "bedrock":
        return "bedrock"

    return "openai"


def llm_ready() -> bool:
    if llm_provider() == "bedrock":
        return bedrock_ready()

    return openai_ready()


def token_count_from_usage(usage, field: str) -> int:
    if usage is None:
        return 0

    if isinstance(usage, dict):
        return int(usage.get(field, 0) or 0)

    return int(getattr(usage, field, 0) or 0)


def invoke_openai(prompt: str, max_output_tokens: int = 80) -> str:
    if llm_provider() == "bedrock":
        return invoke_bedrock(prompt, max_output_tokens)

    if not openai_ready():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.4"),
        input=prompt,
        max_output_tokens=max_output_tokens,
    )
    usage = getattr(response, "usage", None)
    update_token_log(
        token_count_from_usage(usage, "input_tokens"),
        token_count_from_usage(usage, "output_tokens"),
    )

    output_text = getattr(response, "output_text", "")

    if output_text:
        return output_text.strip()

    return str(response).strip()


def invoke_bedrock(prompt: str, max_output_tokens: int = 80) -> str:
    if not bedrock_ready():
        raise RuntimeError("Bedrock is not configured")

    import boto3

    client = boto3.client(
        service_name="bedrock-runtime",
        region_name=os.environ["AWS_REGION"],
    )
    response = client.converse(
        modelId=os.environ["HAIKU_BEDROCK_MODEL_ID"],
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        inferenceConfig={"maxTokens": max_output_tokens},
    )
    usage = response.get("usage", {})
    update_token_log(
        int(usage.get("inputTokens", 0) or 0),
        int(usage.get("outputTokens", 0) or 0),
    )
    content = response.get("output", {}).get("message", {}).get("content", [])
    text_parts = [item.get("text", "") for item in content if item.get("text")]
    return "\n".join(text_parts).strip()


def classify_trade_case(body_text: str) -> str:
    if not llm_ready():
        return "NO"

    prompt = f"""
Return only YES or NO.

Is this judgment relevant to any of these topics: admiralty, shipping, carriage
of goods by sea, bills of lading, charterparties, marine insurance, collision,
salvage, demurrage, laytime, international trade, commodity trading, commercial
contracts, agency, arbitration, sale of goods, trade finance, sanctions/export
controls affecting trade?

Judgment text:
{body_text[:12000]}
""".strip()

    try:
        answer = invoke_openai(prompt, max_output_tokens=8).upper()
    except Exception:
        return "NO"

    return "YES" if answer.startswith("YES") else "NO"


def explain_error(page_text: str, site_name: str) -> str:
    fallback = f"{site_name} could not be scraped because the page did not load as expected."

    if not llm_ready():
        return fallback

    prompt = f"""
In one short sentence, explain why this scraper may have failed for {site_name}.
Avoid speculation. Base the answer only on this page text:

{page_text[:4000]}
""".strip()

    try:
        return invoke_openai(prompt, max_output_tokens=60) or fallback
    except Exception:
        return fallback


def bailii_launch_kwargs(headless: bool) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"channel": "chrome", "headless": headless}

    if headless:
        kwargs["args"] = BAILII_LAUNCH_ARGS

    return kwargs


def new_bailii_context(browser):
    context = browser.new_context(
        user_agent=BAILII_USER_AGENT,
        viewport={"width": 1280, "height": 720},
        locale="en-GB",
        timezone_id="Europe/London",
        extra_http_headers={"Accept-Language": "en-GB,en;q=0.9"},
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    return context


def wait_out_bailii_challenge(page) -> None:
    try:
        if page.title() in BAILII_CHALLENGE_TITLES:
            page.wait_for_function(
                "![\"Oh noes!\", \"Making sure you're not a bot!\"].includes(document.title)",
                timeout=45_000,
            )
    except Exception:
        pass
