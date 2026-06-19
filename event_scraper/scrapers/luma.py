from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page

from event_scraper.cleaning import clean_name, clean_text, extract_email, is_noise_url, normalise_url
from event_scraper.models import Event, Organizer, ScrapedEvent
from event_scraper.scrapers.base import BaseScraper, safe_goto

LOGGER = logging.getLogger(__name__)

LUMA_HOSTS = {"luma.com", "lu.ma", "www.luma.com", "www.lu.ma"}
SECTION_ROLES = {
    "hosted by": "Hosted By",
    "hosts": "Hosted By",
    "presented by": "Presented By",
    "organized by": "Organizer",
    "organised by": "Organizer",
    "organizer": "Organizer",
    "organiser": "Organizer",
}
SKIP_PATH_PREFIXES = (
    "/discover",
    "/pricing",
    "/home",
    "/login",
    "/signup",
    "/about",
    "/terms",
    "/privacy",
    "/help",
    "/settings",
    "/notifications",
)


class LumaScraper(BaseScraper):
    source_site = "luma"

    def __init__(
        self,
        target_urls: Iterable[str],
        delay_seconds: float = 2.0,
        max_events: int | None = None,
        shard_index: int = 0,
        shard_count: int = 1,
        scroll_rounds: int = 40,
        no_new_url_rounds: int = 5,
    ) -> None:
        super().__init__(
            target_urls=target_urls,
            delay_seconds=delay_seconds,
            max_events=max_events,
            shard_index=shard_index,
            shard_count=shard_count,
        )
        self.scroll_rounds = scroll_rounds
        self.no_new_url_rounds = no_new_url_rounds

    async def collect_event_urls(self, browser: Browser) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for target_url in self.target_urls:
            page = await browser.new_page()
            target_count_before = len(urls)
            try:
                await safe_goto(page, target_url)
                no_new_rounds = 0
                for round_index in range(self.scroll_rounds + 1):
                    new_urls = await self._extract_event_urls_from_page(page, target_url)
                    added = 0
                    for href in new_urls:
                        if href not in seen:
                            seen.add(href)
                            urls.append(href)
                            added += 1

                    if added:
                        no_new_rounds = 0
                        LOGGER.info(
                            "Collected %d new Luma event URLs from %s on scroll round %d",
                            added,
                            target_url,
                            round_index,
                        )
                    else:
                        no_new_rounds += 1

                    if no_new_rounds >= self.no_new_url_rounds:
                        LOGGER.info(
                            "Stopping %s after %d rounds with no new URLs",
                            target_url,
                            no_new_rounds,
                        )
                        break

                    clicked_more = await self._click_load_more(page)
                    await page.evaluate("window.scrollBy(0, Math.max(document.body.scrollHeight, 2400))")
                    await page.wait_for_timeout(1200 if clicked_more else 900)
            finally:
                await page.close()

            LOGGER.info("Collected %d event URLs from target %s", len(urls) - target_count_before, target_url)
        return urls

    async def _extract_event_urls_from_page(self, page: Page, target_url: str) -> list[str]:
        anchors = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(a => ({ href: a.href, text: a.innerText || a.textContent || '' }))",
        )
        urls: list[str] = []
        for anchor in anchors:
            href = normalise_url(anchor.get("href"), target_url)
            if not href or not self._looks_like_luma_event_url(href, target_url):
                continue
            urls.append(href)
        return urls

    async def _click_load_more(self, page: Page) -> bool:
        return bool(
            await page.evaluate(
                """
                () => {
                  const matches = [...document.querySelectorAll('button,a')]
                    .filter((el) => /load more|show more|more events/i.test(el.innerText || el.textContent || ''));
                  if (!matches.length) return false;
                  matches[0].click();
                  return true;
                }
                """
            )
        )

    async def scrape_event(self, browser: Browser, event_url: str) -> ScrapedEvent | None:
        page = await browser.new_page()
        try:
            await safe_goto(page, event_url)
            html = await page.content()
            visible_text = await page.locator("body").inner_text(timeout=5_000)
        finally:
            await page.close()

        soup = BeautifulSoup(html, "lxml")
        schemas = _extract_json_ld(soup)
        event_schema = _find_event_schema(schemas)
        title = clean_text(_schema_value(event_schema, "name") or _meta(soup, "og:title") or _title(soup))
        if title and " | luma" in title.lower():
            title = re.sub(r"\s*\|\s*Luma\s*$", "", title, flags=re.IGNORECASE)
        if not title:
            return None

        description = clean_text(_schema_value(event_schema, "description") or _meta(soup, "og:description"))
        location = _schema_value(event_schema, "location")
        venue_name, address, city = _parse_location(location)
        image = _schema_image(event_schema) or _meta(soup, "og:image")

        event = Event(
            source_site=self.source_site,
            event_url=event_url,
            title=title,
            description=description,
            start_time=clean_text(_schema_value(event_schema, "startDate")),
            end_time=clean_text(_schema_value(event_schema, "endDate")),
            timezone=None,
            city=city,
            venue_name=venue_name,
            address=address,
            cover_image_url=normalise_url(image, event_url),
            categories=[],
        )

        organizers = _organizers_from_schema(event_schema, event_url)
        organizers.extend(_organizers_from_sections(soup, event_url))
        contact_url = _find_contact_url(soup, event_url)
        if contact_url:
            for organizer in organizers:
                organizer.platform_contact_url = organizer.platform_contact_url or contact_url

        body_email = extract_email(visible_text)
        if body_email:
            for organizer in organizers:
                organizer.public_email = organizer.public_email or body_email

        return ScrapedEvent(event=event, organizers=_dedupe_organizers(organizers))

    async def scrape_organizer_profile(self, browser: Browser, organizer: Organizer) -> Organizer:
        if not organizer.profile_url:
            return organizer
        parsed = urlparse(organizer.profile_url)
        if parsed.netloc not in LUMA_HOSTS:
            return organizer

        page = await browser.new_page()
        try:
            await safe_goto(page, organizer.profile_url)
            html = await page.content()
            text = await page.locator("body").inner_text(timeout=5_000)
        except Exception:
            await page.close()
            return organizer
        await page.close()

        soup = BeautifulSoup(html, "lxml")
        organizer.bio = organizer.bio or clean_text(_meta(soup, "og:description"))
        organizer.avatar_url = organizer.avatar_url or normalise_url(_meta(soup, "og:image"), organizer.profile_url)
        profile_name = clean_name(_meta(soup, "og:title") or _title(soup))
        organizer.name = organizer.name or profile_name or "Unknown organizer"
        organizer.public_email = organizer.public_email or extract_email(text)

        for href in _all_links(soup, organizer.profile_url):
            lowered = href.lower()
            if "linkedin.com/" in lowered:
                organizer.linkedin_url = organizer.linkedin_url or href
            elif "instagram.com/" in lowered:
                organizer.instagram_url = organizer.instagram_url or href
            elif "twitter.com/" in lowered or "x.com/" in lowered:
                organizer.twitter_url = organizer.twitter_url or href
            elif "mailto:" in lowered:
                organizer.public_email = organizer.public_email or href.split(":", 1)[1].split("?", 1)[0]
            elif not _is_luma_url(href) and not is_noise_url(href):
                organizer.external_website_url = organizer.external_website_url or href
        return organizer

    def _looks_like_luma_event_url(self, url: str, target_url: str | None = None) -> bool:
        parsed = urlparse(url)
        if parsed.netloc not in LUMA_HOSTS:
            return False
        path = parsed.path.rstrip("/")
        if not path or path == "/":
            return False
        if target_url and path == urlparse(target_url).path.rstrip("/"):
            return False
        if any(path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
            return False
        if path.count("/") > 2:
            return False
        return True


def _extract_json_ld(soup: BeautifulSoup) -> list[Any]:
    data: list[Any] = []
    for script in soup.select('script[type="application/ld+json"]'):
        if not script.string:
            continue
        try:
            parsed = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            data.extend(parsed)
        else:
            data.append(parsed)
    return data


def _find_event_schema(schemas: list[Any]) -> dict[str, Any]:
    for item in _walk_schema(schemas):
        if isinstance(item, dict):
            schema_type = item.get("@type")
            if schema_type == "Event" or (isinstance(schema_type, list) and "Event" in schema_type):
                return item
    return {}


def _walk_schema(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _walk_schema(item)
    elif isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_schema(nested)


def _schema_value(schema: dict[str, Any], key: str) -> Any:
    return schema.get(key) if schema else None


def _schema_image(schema: dict[str, Any]) -> str | None:
    image = _schema_value(schema, "image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    return image if isinstance(image, str) else None


def _parse_location(location: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(location, dict):
        return None, None, None
    venue_name = clean_text(location.get("name"))
    address_obj = location.get("address")
    if isinstance(address_obj, dict):
        parts = [
            address_obj.get("streetAddress"),
            address_obj.get("addressLocality"),
            address_obj.get("addressRegion"),
            address_obj.get("postalCode"),
            address_obj.get("addressCountry"),
        ]
        address = clean_text(", ".join(str(part) for part in parts if part))
        city = clean_text(address_obj.get("addressLocality"))
    else:
        address = clean_text(str(address_obj)) if address_obj else None
        city = None
    return venue_name, address, city


def _organizers_from_schema(schema: dict[str, Any], base_url: str) -> list[Organizer]:
    raw = schema.get("organizer") if schema else None
    if not raw:
        return []
    raw_items = raw if isinstance(raw, list) else [raw]
    organizers: list[Organizer] = []
    for item in raw_items:
        if isinstance(item, dict):
            name = clean_name(item.get("name"))
            if not name:
                continue
            organizers.append(
                Organizer(
                    name=name,
                    role="Organizer",
                    organizer_type=item.get("@type"),
                    profile_url=normalise_url(item.get("url"), base_url),
                    avatar_url=normalise_url(_schema_image(item), base_url),
                )
            )
        elif isinstance(item, str):
            name = clean_name(item)
            if name:
                organizers.append(Organizer(name=name, role="Organizer"))
    return organizers


def _organizers_from_sections(soup: BeautifulSoup, base_url: str) -> list[Organizer]:
    organizers: list[Organizer] = []
    for role_label, role in SECTION_ROLES.items():
        pattern = re.compile(rf"\b{re.escape(role_label)}\b", re.IGNORECASE)
        for node in soup.find_all(string=pattern):
            container = node.parent
            for _ in range(3):
                if container and container.parent:
                    container = container.parent
            if not container:
                continue
            candidates = list(container.select("a[href]"))
            if not candidates and container.parent:
                candidates = list(container.parent.select("a[href]"))
            for anchor in candidates:
                name = clean_name(anchor.get_text(" "))
                href = normalise_url(anchor.get("href"), base_url)
                if not name or not href or is_noise_url(href):
                    continue
                if _is_social_only_name(name):
                    continue
                organizers.append(Organizer(name=name, role=role, profile_url=href, organizer_type="person"))
    return organizers


def _is_social_only_name(name: str) -> bool:
    return name.lower().strip() in {"linkedin", "instagram", "twitter", "x", "website", "email"}


def _find_contact_url(soup: BeautifulSoup, base_url: str) -> str | None:
    for anchor in soup.select("a[href]"):
        text = (anchor.get_text(" ") or "").lower()
        href = normalise_url(anchor.get("href"), base_url)
        if href and ("contact" in text or "contact" in href.lower()):
            return href
    return None


def _all_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = normalise_url(anchor.get("href"), base_url)
        if not href or href in seen or is_noise_url(href):
            continue
        seen.add(href)
        links.append(href)
    return links


def _is_luma_url(url: str) -> bool:
    return urlparse(url).netloc in LUMA_HOSTS


def _dedupe_organizers(organizers: list[Organizer]) -> list[Organizer]:
    by_key: dict[str, Organizer] = {}
    for organizer in organizers:
        key = organizer.organizer_key()
        existing = by_key.get(key)
        if not existing:
            by_key[key] = organizer
            continue
        for field in (
            "organizer_type",
            "profile_url",
            "avatar_url",
            "bio",
            "external_website_url",
            "linkedin_url",
            "instagram_url",
            "twitter_url",
            "public_email",
            "platform_contact_url",
        ):
            if getattr(existing, field) is None and getattr(organizer, field) is not None:
                setattr(existing, field, getattr(organizer, field))
        if existing.role != organizer.role and organizer.role not in existing.role:
            existing.role = f"{existing.role}; {organizer.role}"
    return list(by_key.values())


def _meta(soup: BeautifulSoup, property_name: str) -> str | None:
    tag = soup.find("meta", property=property_name) or soup.find("meta", attrs={"name": property_name})
    if not tag:
        return None
    value = tag.get("content")
    return value if isinstance(value, str) else None


def _title(soup: BeautifulSoup) -> str | None:
    return soup.title.string if soup.title and soup.title.string else None
