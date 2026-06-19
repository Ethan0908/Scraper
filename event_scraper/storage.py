from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_scraper.models import ScrapedEvent


@dataclass(slots=True)
class StorageSummary:
    events_upserted: int = 0
    organizers_upserted: int = 0
    relationships_upserted: int = 0


class SupabaseStorage:
    def __init__(self, url: str, service_role_key: str) -> None:
        try:
            from supabase import create_client
        except ImportError as exc:
            raise RuntimeError("Install the 'supabase' package to use Supabase storage.") from exc
        self.client = create_client(url, service_role_key)

    def upsert_events(self, scraped_events: list[ScrapedEvent]) -> StorageSummary:
        summary = StorageSummary()
        for item in scraped_events:
            event_row = item.event.to_row()
            event_response = (
                self.client.table("events")
                .upsert(event_row, on_conflict="event_url")
                .execute()
            )
            event_data = _first(event_response.data)
            event_id = event_data.get("id") if event_data else None
            if not event_id:
                lookup = self.client.table("events").select("id").eq("event_url", item.event.event_url).limit(1).execute()
                event_id = _first(lookup.data).get("id") if _first(lookup.data) else None
            if not event_id:
                continue
            summary.events_upserted += 1

            for organizer in item.organizers:
                organizer_row = organizer.to_row()
                organizer_response = (
                    self.client.table("organizers")
                    .upsert(organizer_row, on_conflict="organizer_key")
                    .execute()
                )
                organizer_data = _first(organizer_response.data)
                organizer_id = organizer_data.get("id") if organizer_data else None
                if not organizer_id:
                    lookup = (
                        self.client.table("organizers")
                        .select("id")
                        .eq("organizer_key", organizer.organizer_key())
                        .limit(1)
                        .execute()
                    )
                    organizer_id = _first(lookup.data).get("id") if _first(lookup.data) else None
                if not organizer_id:
                    continue
                summary.organizers_upserted += 1
                relationship = {
                    "event_id": event_id,
                    "organizer_id": organizer_id,
                    "role": organizer.role,
                }
                self.client.table("event_organizers").upsert(
                    relationship,
                    on_conflict="event_id,organizer_id,role",
                ).execute()
                summary.relationships_upserted += 1
        return summary


def _first(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, dict) else None
    return None
