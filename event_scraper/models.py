from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


@dataclass(slots=True)
class Organizer:
    name: str
    role: str = "Organizer"
    organizer_type: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    external_website_url: str | None = None
    linkedin_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None
    public_email: str | None = None
    platform_contact_url: str | None = None

    def organizer_key(self) -> str:
        basis = self.profile_url or self.linkedin_url or self.external_website_url or self.name.lower().strip()
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    def to_row(self) -> dict[str, Any]:
        data = asdict(self)
        data["organizer_key"] = self.organizer_key()
        return data


@dataclass(slots=True)
class Event:
    source_site: str
    event_url: str
    title: str
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    timezone: str | None = None
    city: str | None = None
    venue_name: str | None = None
    address: str | None = None
    cover_image_url: str | None = None
    categories: list[str] = field(default_factory=list)
    status: str = "active"
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def content_hash(self) -> str:
        payload = {
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "timezone": self.timezone,
            "city": self.city,
            "venue_name": self.venue_name,
            "address": self.address,
            "cover_image_url": self.cover_image_url,
            "categories": sorted(self.categories),
            "status": self.status,
        }
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def to_row(self) -> dict[str, Any]:
        data = asdict(self)
        data["content_hash"] = self.content_hash()
        return data


@dataclass(slots=True)
class ScrapedEvent:
    event: Event
    organizers: list[Organizer] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.to_row(),
            "organizers": [organizer.to_row() for organizer in self.organizers],
        }
