# Interaction Logs

This document records the main collaboration evidence for the PyCon Singapore 2026 Open Track submission.

Project: **CommonLaw Brief**  
Repository: `kaidon-ng/legalupdate`  
Date of build session: `23 June 2026`

Sensitive values such as API keys, Firebase private keys, and service-account credentials are intentionally excluded.

## Contributors

| Contributor | Role | Contributions |
| --- | --- | --- |
| Project owner / developer | Human product owner and domain lead | Proposed the legal digest idea, explained the Singapore/common-law motivation, selected sources, provided scraper selectors, chose the no-login demo requirement, reviewed UI, requested changes, and made product decisions. |
| OpenAI Codex | AI coding assistant | Implemented the frontend, backend, scrapers, summarizer pipeline, local database, optional Firebase/Apify integration, docs, tests, Git commits, and submission preparation based on the human requirements. |
| External stakeholders | Not separately recorded in this build session | No separate human-human stakeholder meetings or teammate discussions were provided in the repository context. This was treated as a solo build with AI-assisted implementation. |

## AI-Human Collaboration Timeline

### 1. Idea and Scope

Human prompt summary:

> Build a weekly legal news digest for Singapore/common-law judgments. Scrape new judgments weekly, summarize them, and let users configure what sources/topics they want.

AI contribution:

- Helped shape the architecture around a weekly scrape, local processing pipeline, and filtered frontend digest.
- Discussed Django, Node.js, Next.js, Playwright, and Apify tradeoffs.

Resulting files:

- `README.md`
- `server.py`
- `main.py`
- scraper scripts

### 2. Frontend Preferences Page

Human prompt summary:

> Make a simple frontend where users choose regular reader/lawyer, sources, and topics. No login system yet.

AI contribution:

- Built the preferences UI.
- Added source toggles and topic chips.
- Later moved login to a separate page and made "View digest" a more obvious top button.

Resulting files:

- `index.html`
- `styles.css`
- `app.js`
- `login.html`
- `login.js`

### 3. Scraper Pipeline

Human prompt summary:

> Create `main.py`, `data/`, status files, and separate scraper scripts. Build Playwright scrapers for Singapore Judiciary and BAILII sources using the provided selectors.

AI contribution:

- Implemented the orchestrator and scraper scripts.
- Added duplicate protection.
- Added scraper status tracking.
- Added BAILII anti-bot browser context hardening.
- Added Apify actor configuration for hosted runs.

Resulting files:

- `main.py`
- `scraper_utils.py`
- `singapore_judiciary_scrape.py`
- `bailii_comm.py`
- `bailii_uksc_admlty.py`
- `.actor/actor.json`
- `actor_main.py`
- `Dockerfile`

### 4. Digest Page

Human prompt summary:

> Keep the previous preferences page, and create a new digest page. It should show cases grouped by source, details, source links, and PDFs.

AI contribution:

- Built the digest page and sidebar navigation.
- Added case detail view.
- Added public no-login digest mode for judges.
- Changed long-summary PDF preview from a side panel to a centered modal.

Resulting files:

- `digest.html`
- `digest.css`
- `digest.js`
- `digest_data.js`

### 5. Summarization and Tagging

Human prompt summary:

> Add a local post-scrape summarizer. Use OpenAI GPT-5.4. Add prompts for short and long summaries. Add tags based on the UI selectors. Later add regular-reader and lawyer summaries.

AI contribution:

- Implemented PDF text extraction with PyMuPDF.
- Added LLM summary generation and JSON parsing.
- Added legal-topic tagging.
- Added `regular_summary` and `lawyer_summary`.
- Added generated long-summary PDFs with ReportLab.
- Added optional Bedrock Haiku support for demo generation.

Resulting files:

- `summarizer.py`
- `scraper_utils.py`
- `requirements.txt`
- `summary_pdfs/`
- `legal_digest.db`

### 6. Storage and Accounts

Human prompt summary:

> Store summaries in a database. Filter based on account config. Add quick authentication. Later make the public user able to run without login.

AI contribution:

- Added SQLite local storage for demo and development.
- Added account registration/login with password hashing.
- Added saved preferences per account.
- Added no-login public digest behavior.
- Added optional Firebase Firestore/Storage integration and local sync script.

Resulting files:

- `account_store.py`
- `server.py`
- `firebase_store.py`
- `sync_firebase.py`
- `legal_digest.db`

### 7. Demo Data Generation

Human prompt summary:

> Run the system for demo date `20/6` using Bedrock Haiku, then move back to OpenAI.

AI contribution:

- Added provider switch with `AI_PROVIDER`.
- Ran the pipeline with `DEMO_DATE=2026-06-20` and Bedrock Haiku.
- Generated 22 local demo cases.
- Restored OpenAI as the default provider.

Demo output:

- 13 Singapore Judiciary cases
- 8 BAILII Commercial Court cases
- 1 UK Supreme Court case
- 0 Admiralty cases
- 22 short summaries
- 22 regular-reader summaries
- 22 lawyer summaries
- 22 long-summary PDFs

Resulting files:

- `legal_digest.db`
- `cases_summary.json`
- `digest_data.js`
- `summary_pdfs/`
- `scraper_status.json`

### 8. Submission Preparation

Human prompt summary:

> Prepare for GitHub submission. Make sure judges can run it without logging in, and commit/push the repo.

AI contribution:

- Added README and `.env.example`.
- Ensured `.env`, raw scraped data, and service-account files are ignored.
- Added `.gitattributes` for binary database/PDF files.
- Shortened generated PDF filenames to avoid Git/Windows path issues.
- Committed and pushed the repository.

Git evidence:

- `4f3e5a7 Prepare legal digest demo submission`
- `387d7b3 Redirect to preferences after login`

## Prompt Evidence Summary

Representative AI-human prompts from the build session included:

- "Build a weekly news digest for law."
- "Make a simple frontend for configuring reader type, sources, and topics."
- "Build the Singapore Judiciary Playwright scraper using these selectors."
- "Build BAILII Commercial Court and UKSC/Admiralty scrapers."
- "Add the missing post-scrape summarizer pipeline."
- "Use OpenAI GPT-5.4 for summarising and filtering."
- "Add tags based on the index page selectors."
- "Save summaries into a database."
- "Use Firebase for storage."
- "Add a frontend and backend with quick authentication."
- "Make cases store short summary, long-summary PDF, and actual judgment URL."
- "Make the PDF open as a centered modal."
- "Make the public user able to run without login and view selected content."
- "Prepare everything for GitHub submission."

## Human-Human Collaboration Evidence

No separate human-human collaboration materials were provided in this repository context.

The project owner acted as:

- Product stakeholder
- Domain guide
- UX reviewer
- Technical reviewer
- Final submission owner

If further team discussion, mentor feedback, judging feedback, or stakeholder interviews are added later, they should be appended here with:

- date
- participant names or roles
- discussion summary
- decisions made
- links to notes, issues, or commits

## Verification Evidence

During the build session, the following checks were run:

- Python compile checks with `python -m py_compile`
- JavaScript syntax checks with `node --check`
- Flask API smoke tests for register/login/preferences/digest
- No-login digest API checks
- SQLite record counts for demo cases
- Generated PDF existence checks
- Secret scans for exposed Firebase private key content before commit
- Git staging check to ensure `.env` and raw scraped data were not committed

Current demo state:

- No login required for `/digest`
- 22 included cases
- 22 long-summary PDFs
- regular-reader and lawyer summaries available
- optional demo account available:
  - `demo@example.com`
  - `password123`
