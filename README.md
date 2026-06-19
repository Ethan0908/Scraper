# Event Scraper

A GitHub Actions-ready Python pipeline for scraping **public event information** and saving it to Supabase, Google Sheets, CSV, JSONL, and Excel exports.

The current adapter supports Luma-style public event pages. The project is structured so you can add more event-site adapters later without changing the database/export pipeline.

## What it collects

For events:

- title
- event URL
- source site
- start/end time
- city
- venue name/address when publicly shown
- description
- cover image URL
- categories placeholder
- status/hash timestamps

For organizers:

- name
- role such as `Hosted By`, `Presented By`, or `Organizer`
- profile URL
- avatar URL
- website
- LinkedIn/Instagram/Twitter/X links when publicly visible
- public email only when visibly present
- platform contact URL when present

## Repository layout

```text
.github/workflows/scrape.yml   # Daily/manual GitHub Actions scraper
main.py                        # CLI entry point
event_scraper/                 # Python package
  config.py                    # Environment settings
  cleaning.py                  # URL/text/email cleaning helpers
  models.py                    # Normalized dataclasses
  storage.py                   # Supabase upserts
  exporters.py                 # CSV, JSONL, Excel, Google Sheets
  scrapers/
    base.py                    # Shared scraper interface
    luma.py                    # Luma adapter
database/schema.sql            # Supabase/Postgres schema
tests/                         # Small unit tests
```

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Edit `.env`:

```env
LUMA_TARGET_URLS=https://luma.com/nyc
MAX_EVENTS_PER_SOURCE=50
REQUEST_DELAY_SECONDS=2.0
```

Run locally:

```bash
python main.py --source luma
```

Exports will be written to `exports/`:

- `events.csv`
- `organizers.csv`
- `event_organizers.csv`
- `events.jsonl`
- `events.xlsx`

## Supabase setup

1. Create a Supabase project.
2. Open the SQL editor.
3. Run `database/schema.sql`.
4. Add these GitHub repository secrets:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

The scraper upserts by `event_url` for events and by `organizer_key` for organizers.

## Google Sheets setup

Optional.

Add these GitHub repository secrets:

- `GOOGLE_SHEET_ID`
- `GOOGLE_CREDENTIALS_JSON`

`GOOGLE_CREDENTIALS_JSON` should be the full service-account JSON as one secret value. Share the Google Sheet with the service-account email.

The pipeline writes three tabs:

- `Events`
- `Organizers`
- `Event Organizers`

## GitHub Actions

The workflow runs:

- manually through **Actions → Scrape Events → Run workflow**
- daily at `08:00 UTC`

Repository variables you can set:

- `LUMA_TARGET_URLS`
- `REQUEST_DELAY_SECONDS`
- `MAX_EVENTS_PER_SOURCE`

Example `LUMA_TARGET_URLS`:

```text
https://luma.com/nyc,https://luma.com/sf
```

## Adding another site

Create a new adapter in `event_scraper/scrapers/` that inherits from `BaseScraper` and returns `ScrapedEvent` objects. Then add it to `main.py`.

## Public-data boundary

This project is designed to collect public event and organizer information only. Do not use it for private pages, login-only data, CAPTCHA bypassing, hidden personal data, or aggressive crawling.
