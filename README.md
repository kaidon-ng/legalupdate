# Legal Updates Digest

A weekly legal judgment digest prototype for the PyCon Singapore 2026 Open Track.

The app scrapes recent judgments, summarizes them into short digest notes, generates long-summary PDFs, tags cases by legal topic, and filters the digest by each user's saved preferences.

## Quick Start For Judges

This repository includes demo data, so you can run the web app without scraping or configuring cloud credentials.

```powershell
cd pycon_hack
python -m pip install -r requirements.txt
python .\server.py
```

Open:

```text
http://127.0.0.1:5000/digest
```

No login is required to view the included demo digest.

Optional demo account:

```text
Email: demo@example.com
Password: password123
```

Use the account if you want to test saved preferences and account-filtered digests.

## Included Demo Data

The repository includes a pre-generated local demo dataset for `20 June 2026`:

- `legal_digest.db` with 22 summarized cases
- `digest_data.js` static browser fallback data
- `cases_summary.json` generated case export
- `summary_pdfs/` with 22 generated long-summary PDFs
- `scraper_status.json` from the demo run

Each case stores:

- `short_summary`
- `regular_summary`
- `lawyer_summary`
- `summary_pdf`
- `source_url`
- metadata such as court, parties, citation, source, and legal tags

## Main Pages

```text
http://127.0.0.1:5000/
```

Preference page.

```text
http://127.0.0.1:5000/login
```

Optional login/register page.

```text
http://127.0.0.1:5000/digest
```

Legal digest page. It works without login using the included public demo data. If logged in, it uses the account's saved source/topic preferences.

## Features

- Weekly judgment scraping pipeline
- Singapore Judiciary scraper
- BAILII Commercial Court scraper
- BAILII UK Supreme Court scraper
- BAILII Admiralty scraper
- OpenAI summarization by default
- Optional Bedrock Haiku support
- Legal topic tagging
- SQLite local database
- Optional Firebase Firestore and Storage persistence
- Account login/register with saved preferences
- No-login public digest demo
- Regular-reader and lawyer-specific summaries
- Long-summary PDF modal preview
- Apify Actor configuration for hosted weekly scraping

## Local Configuration

Copy the example env file:

```powershell
Copy-Item .\.env.example .\.env
```

For the included demo, you do not need real API keys.

For fresh AI summarization, set:

```env
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-5.4
AI_PROVIDER=openai
```

Do not commit `.env` or Firebase service-account JSON files.

## Running The Full Pipeline

Only run this if you want to scrape and summarize fresh cases.

```powershell
$env:CI="true"
python .\main.py
```

For a deterministic demo date:

```powershell
$env:CI="true"
$env:DEMO_DATE="2026-06-20"
python .\main.py
```

The pipeline:

1. Creates local folders.
2. Runs the scraper scripts.
3. Extracts PDF text.
4. Summarizes and tags each case.
5. Generates long-summary PDFs.
6. Saves cases to SQLite.
7. Writes `digest_data.js` for static fallback.

## Firebase Optional Sync

If Firebase credentials are configured, summaries can be pushed to Firestore and summary PDFs to Firebase Storage.

Set one of:

```env
FIREBASE_SERVICE_ACCOUNT_JSON={...}
```

or:

```env
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
```

Then run:

```powershell
python .\sync_firebase.py
```

## Apify Deployment

The repository includes:

- `.actor/actor.json`
- `.actor/INPUT_SCHEMA.json`
- `Dockerfile`
- `actor_main.py`

Required Apify secrets:

```env
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-5.4
AI_PROVIDER=openai
CI=true
```

Optional Firebase secrets:

```env
FIREBASE_SERVICE_ACCOUNT_JSON={...}
FIREBASE_STORAGE_BUCKET=legalupdates-cac8a.firebasestorage.app
FIREBASE_CASES_COLLECTION=cases
```

## Project Structure

```text
server.py                     Flask app and API
account_store.py              Auth, preferences, filtered digest data
main.py                       Scraper/summarizer orchestrator
summarizer.py                 PDF text extraction, AI summaries, PDF generation
scraper_utils.py              Shared scraper and AI helpers
singapore_judiciary_scrape.py Singapore Judiciary scraper
bailii_comm.py                BAILII Commercial Court scraper
bailii_uksc_admlty.py         UKSC and Admiralty scraper
firebase_store.py             Optional Firebase writes
sync_firebase.py              Upload existing local demo data to Firebase
index.html / app.js           Preferences frontend
login.html / login.js         Login/register frontend
digest.html / digest.js       Digest frontend
legal_digest.db               Included local demo database
summary_pdfs/                 Included generated long-summary PDFs
```

## Notes

This is a hackathon prototype. The included demo data is intended to make judging and local testing reliable without requiring live scraping, paid API keys, or cloud setup.
