from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from event_scraper.config import Settings
from event_scraper.exporters import export_files, export_google_sheet
from event_scraper.scrapers import LumaScraper
from event_scraper.storage import SupabaseStorage

LOGGER = logging.getLogger("event_scraper")


async def scrape(
    settings: Settings,
    source: str,
    target_urls: list[str],
    shard_index: int,
    shard_count: int,
    max_events: int | None,
) -> list:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.headless)
        try:
            if source == "luma":
                scraper = LumaScraper(
                    target_urls,
                    delay_seconds=settings.request_delay_seconds,
                    max_events=max_events,
                    shard_index=shard_index,
                    shard_count=shard_count,
                    scroll_rounds=settings.scroll_rounds,
                    no_new_url_rounds=settings.no_new_url_rounds,
                )
                return await scraper.run(browser)
            raise ValueError(f"Unsupported source: {source}")
        finally:
            await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape public event pages into Supabase and spreadsheet exports.")
    parser.add_argument("--source", default="luma", choices=["luma"], help="Event site adapter to run.")
    parser.add_argument("--target-url", action="append", help="Override LUMA_TARGET_URLS. Can be passed more than once.")
    parser.add_argument("--max-events", type=int, default=None, help="Limit events after URL discovery and sharding.")
    parser.add_argument("--shard-index", type=int, default=0, help="Zero-based shard index to scrape.")
    parser.add_argument("--shard-count", type=int, default=1, help="Total number of shards.")
    parser.add_argument("--no-supabase", action="store_true", help="Skip Supabase writes even when credentials exist.")
    parser.add_argument("--no-google-sheets", action="store_true", help="Skip Google Sheets export even when credentials exist.")
    return parser.parse_args()


async def amain() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    settings = Settings.from_env()
    target_urls = args.target_url or settings.luma_target_urls
    max_events = args.max_events if args.max_events is not None else settings.max_events_per_source

    started_at = datetime.now(timezone.utc)
    LOGGER.info("Starting %s scrape for targets: %s", args.source, ", ".join(target_urls))
    LOGGER.info("Shard settings: index=%d count=%d", args.shard_index, args.shard_count)
    scraped_events = await scrape(settings, args.source, target_urls, args.shard_index, args.shard_count, max_events)
    LOGGER.info("Scraped %d events", len(scraped_events))

    export_files(scraped_events, settings.export_dir)
    LOGGER.info("Wrote CSV, JSONL, and Excel exports to %s", settings.export_dir)

    if not args.no_supabase and settings.supabase_url and settings.supabase_service_role_key:
        storage = SupabaseStorage(settings.supabase_url, settings.supabase_service_role_key)
        summary = storage.upsert_events(scraped_events)
        LOGGER.info("Supabase upsert summary: %s", summary)
    elif not args.no_supabase:
        LOGGER.info("Skipping Supabase: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing")

    if (
        not args.no_google_sheets
        and settings.google_sheet_id
        and (settings.google_credentials_json or settings.google_credentials_b64)
    ):
        export_google_sheet(
            scraped_events,
            settings.google_sheet_id,
            credentials_json=settings.google_credentials_json,
            credentials_b64=settings.google_credentials_b64,
            write_mode=settings.sheet_write_mode,
        )
        LOGGER.info("Exported results to Google Sheets using %s mode", settings.sheet_write_mode)
    elif not args.no_google_sheets:
        LOGGER.info("Skipping Google Sheets: GOOGLE_SHEET_ID and credentials are required")

    LOGGER.info("Finished in %.1f seconds", (datetime.now(timezone.utc) - started_at).total_seconds())


if __name__ == "__main__":
    asyncio.run(amain())
