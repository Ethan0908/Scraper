from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pandas as pd

from event_scraper.models import ScrapedEvent


def flatten(scraped_events: list[ScrapedEvent]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_rows: list[dict[str, Any]] = []
    organizer_rows: dict[str, dict[str, Any]] = {}
    relationship_rows: list[dict[str, Any]] = []

    for item in scraped_events:
        event = item.event.to_row()
        event_rows.append(event)
        for organizer in item.organizers:
            organizer_row = organizer.to_row()
            organizer_rows[organizer_row["organizer_key"]] = organizer_row
            relationship_rows.append(
                {
                    "event_url": item.event.event_url,
                    "event_title": item.event.title,
                    "organizer_key": organizer_row["organizer_key"],
                    "organizer_name": organizer.name,
                    "role": organizer.role,
                }
            )
    return (
        pd.DataFrame(event_rows),
        pd.DataFrame(organizer_rows.values()),
        pd.DataFrame(relationship_rows),
    )


def export_files(scraped_events: list[ScrapedEvent], export_dir: Path) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)
    events_df, organizers_df, relationships_df = flatten(scraped_events)

    events_df.to_csv(export_dir / "events.csv", index=False)
    organizers_df.to_csv(export_dir / "organizers.csv", index=False)
    relationships_df.to_csv(export_dir / "event_organizers.csv", index=False)

    with (export_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for item in scraped_events:
            handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    with pd.ExcelWriter(export_dir / "events.xlsx", engine="openpyxl") as writer:
        events_df.to_excel(writer, sheet_name="Events", index=False)
        organizers_df.to_excel(writer, sheet_name="Organizers", index=False)
        relationships_df.to_excel(writer, sheet_name="Event Organizers", index=False)


def export_google_sheet(
    scraped_events: list[ScrapedEvent],
    spreadsheet_id: str,
    credentials_json: str | None = None,
    credentials_b64: str | None = None,
    write_mode: str = "replace",
) -> None:
    try:
        import gspread
    except ImportError as exc:
        raise RuntimeError("Install 'gspread' to export to Google Sheets.") from exc

    credentials = parse_google_credentials(credentials_json, credentials_b64)
    client = gspread.service_account_from_dict(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)
    events_df, organizers_df, relationships_df = flatten(scraped_events)
    _write_worksheet(spreadsheet, "Events", events_df, write_mode)
    _write_worksheet(spreadsheet, "Organizers", organizers_df, write_mode)
    _write_worksheet(spreadsheet, "Event Organizers", relationships_df, write_mode)


def parse_google_credentials(credentials_json: str | None = None, credentials_b64: str | None = None) -> dict[str, Any]:
    candidates: list[str] = []
    if credentials_b64:
        try:
            candidates.append(base64.b64decode(credentials_b64).decode("utf-8"))
        except Exception as exc:
            raise ValueError("GOOGLE_CREDENTIALS_B64 is not valid base64-encoded UTF-8 JSON.") from exc

    if credentials_json:
        raw = credentials_json.strip()
        if raw.startswith("GOOGLE_CREDENTIALS_JSON="):
            raw = raw.split("=", 1)[1].strip()
        if raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1].strip()
        candidates.append(raw)
        if not raw.startswith("{") and '"type"' in raw:
            candidates.append("{" + raw.rstrip(",") + "}")

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(parsed, dict):
            raise ValueError("Google credentials must decode to a JSON object.")
        required = {"type", "client_email", "private_key"}
        missing = sorted(required - set(parsed))
        if missing:
            raise ValueError(f"Google credentials JSON is missing required keys: {', '.join(missing)}")
        return parsed

    if last_error:
        raise ValueError(
            "Could not parse Google service-account credentials. Put the complete JSON object in "
            "GOOGLE_CREDENTIALS_JSON, including the opening and closing braces, or put a base64-encoded "
            "copy of the JSON in GOOGLE_CREDENTIALS_B64. Do not paste only the inner lines."
        ) from last_error
    raise ValueError("Google credentials were not provided.")


def _write_worksheet(spreadsheet: Any, title: str, frame: pd.DataFrame, write_mode: str) -> None:
    try:
        worksheet = spreadsheet.worksheet(title)
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1, cols=max(len(frame.columns), 1))

    values = [frame.columns.tolist()] + frame.fillna("").astype(str).values.tolist()
    if write_mode == "append":
        existing = worksheet.get_all_values()
        if not existing:
            worksheet.update(values, value_input_option="RAW")
        elif len(values) > 1:
            worksheet.append_rows(values[1:], value_input_option="RAW")
        return

    worksheet.clear()
    if values:
        worksheet.update(values, value_input_option="RAW")
