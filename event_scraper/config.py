from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    luma_target_urls: list[str]
    request_delay_seconds: float
    max_events_per_source: int | None
    headless: bool
    export_dir: Path
    supabase_url: str | None
    supabase_service_role_key: str | None
    google_sheet_id: str | None
    google_credentials_json: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        max_events_raw = os.getenv("MAX_EVENTS_PER_SOURCE")
        return cls(
            luma_target_urls=_split_csv(os.getenv("LUMA_TARGET_URLS")) or ["https://luma.com/nyc"],
            request_delay_seconds=float(os.getenv("REQUEST_DELAY_SECONDS", "2.0")),
            max_events_per_source=int(max_events_raw) if max_events_raw else None,
            headless=os.getenv("HEADLESS", "true").lower() != "false",
            export_dir=Path(os.getenv("EXPORT_DIR", "exports")),
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID"),
            google_credentials_json=os.getenv("GOOGLE_CREDENTIALS_JSON"),
        )
