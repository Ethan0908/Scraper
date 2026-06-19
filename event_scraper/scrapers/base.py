from __future__ import annotations

import abc
import asyncio
from collections.abc import Iterable

from playwright.async_api import Browser, Page

from event_scraper.models import Organizer, ScrapedEvent


class BaseScraper(abc.ABC):
    source_site: str

    def __init__(self, target_urls: Iterable[str], delay_seconds: float = 2.0, max_events: int | None = None) -> None:
        self.target_urls = list(target_urls)
        self.delay_seconds = delay_seconds
        self.max_events = max_events

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
        if self.max_events is not None:
            urls = urls[: self.max_events]

        results: list[ScrapedEvent] = []
        for url in urls:
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


async def auto_scroll(page: Page, rounds: int = 8, wait_ms: int = 800) -> None:
    previous_height = 0
    for _ in range(rounds):
        current_height = await page.evaluate("document.body.scrollHeight")
        if current_height == previous_height:
            break
        previous_height = current_height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(wait_ms)
