from __future__ import annotations

import abc
import asyncio
import logging
from collections.abc import Iterable

from playwright.async_api import Browser, Page

from event_scraper.models import Organizer, ScrapedEvent

LOGGER = logging.getLogger(__name__)


class BaseScraper(abc.ABC):
    source_site: str

    def __init__(
        self,
        target_urls: Iterable[str],
        delay_seconds: float = 2.0,
        max_events: int | None = None,
        shard_index: int = 0,
        shard_count: int = 1,
    ) -> None:
        self.target_urls = list(target_urls)
        self.delay_seconds = delay_seconds
        self.max_events = max_events
        self.shard_index = shard_index
        self.shard_count = shard_count
        if self.shard_count < 1:
            raise ValueError("shard_count must be at least 1")
        if not 0 <= self.shard_index < self.shard_count:
            raise ValueError("shard_index must be between 0 and shard_count - 1")

    @abc.abstractmethod
    async def collect_event_urls(self, browser: Browser) -> list[str]:
        pass

    @abc.abstractmethod
    async def scrape_event(self, browser: Browser, event_url: str) -> ScrapedEvent | None:
        pass

    async def scrape_organizer_profile(self, browser: Browser, organizer: Organizer) -> Organizer:
        return organizer

    async def run(self, browser: Browser) -> list[ScrapedEvent]:
        urls = await self.collect_event_urls(browser)
        LOGGER.info("Collected %d candidate event URLs before sharding", len(urls))

        if self.shard_count > 1:
            urls = [url for index, url in enumerate(urls) if index % self.shard_count == self.shard_index]
            LOGGER.info("Shard %d/%d will scrape %d event URLs", self.shard_index + 1, self.shard_count, len(urls))

        if self.max_events is not None:
            urls = urls[: self.max_events]
            LOGGER.info("Applying max_events limit: %d event URLs", len(urls))

        results: list[ScrapedEvent] = []
        for index, url in enumerate(urls, start=1):
            LOGGER.info("Scraping event %d/%d: %s", index, len(urls), url)
            event = await self.scrape_event(browser, url)
            if event is None:
                continue
            enriched: list[Organizer] = []
            for organizer in event.organizers:
                enriched.append(await self.scrape_organizer_profile(browser, organizer))
                await asyncio.sleep(self.delay_seconds)
            event.organizers = enriched
            results.append(event)
            await asyncio.sleep(self.delay_seconds)
        return results


async def safe_goto(page: Page, url: str, timeout_ms: int = 45_000) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
