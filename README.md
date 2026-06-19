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
MAX_EVENTS_PER_SOURCE=
REQUEST_DELAY_SECONDS=2.0
SCROLL_ROUNDS=40
NO_NEW_URL_ROUNDS=5
SHEET_WRITE_MODE=replace
```

Run locally:

```bash
python main.py --source luma
```

Run a smaller shard locally:

```bash
python main.py --source luma --shard-count 4 --shard-index 0
```

Exports will be written to `exports/`:

- `events.csv`
- `organizers.csv`
- `event_organizers.csv`
- `events.jsonl`
- `events.xlsx`

## Supabase setup

Optional. Skip this if you only want Google Sheets.

1. Create a Supabase project.
2. Open the SQL editor.
3. Run `database/schema.sql`.
4. Add these GitHub repository secrets:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

The scraper upserts by `event_url` for events and by `organizer_key` for organizers.

## Google Sheets setup

Add these GitHub repository secrets:

- `GOOGLE_SHEET_ID`
- one of:
  - `GOOGLE_CREDENTIALS_JSON`
  - `GOOGLE_CREDENTIALS_B64`

`GOOGLE_CREDENTIALS_JSON` must be the full service-account JSON object, including the opening `{` and closing `}`. Do not paste only the inner lines such as `"type": "service_account"`.

The safer option is `GOOGLE_CREDENTIALS_B64`:

```bash
base64 -w 0 service-account.json
```

On macOS:

```bash
base64 service-account.json | tr -d '\n'
```

Share the Google Sheet with the service-account email.

The pipeline writes three tabs:

- `Events`
- `Organizers`
- `Event Organizers`

Use `SHEET_WRITE_MODE=replace` for one full scrape. Use `SHEET_WRITE_MODE=append` when running separate shards into the same sheet.

## GitHub Actions

The workflow runs:

- manually through **Actions → Scrape Events → Run workflow**
- daily at `08:00 UTC`

Manual inputs:

- `target_urls`: comma-separated Luma listing/calendar URLs
- `max_events`: optional limit after URL discovery and sharding
- `shard_index`: zero-based shard number
- `shard_count`: total number of shards
- `scroll_rounds`: maximum listing-page scroll rounds
- `sheet_write_mode`: `replace` or `append`

Repository variables you can set:

- `LUMA_TARGET_URLS`
- `REQUEST_DELAY_SECONDS`
- `MAX_EVENTS_PER_SOURCE`
- `SCROLL_ROUNDS`
- `NO_NEW_URL_ROUNDS`
- `SHEET_WRITE_MODE`

Example `LUMA_TARGET_URLS`:

```text
https://luma.com/nyc,https://luma.com/sf
```

## Splitting a scrape

To split a large scrape into four separate runs:

1. Run shard `0` with `shard_count=4` and `sheet_write_mode=replace`.
2. Run shards `1`, `2`, and `3` with `shard_count=4` and `sheet_write_mode=append`.

Each shard first discovers the full listing URL set, then scrapes only the event URLs assigned to that shard.

## Adding another site

Create a new adapter in `event_scraper/scrapers/` that inherits from `BaseScraper` and returns `ScrapedEvent` objects. Then add it to `main.py`.

## Public-data boundary

This project is designed to collect public event and organizer information only. Do not use it for private pages, login-only data, CAPTCHA bypassing, hidden personal data, or aggressive crawling.
