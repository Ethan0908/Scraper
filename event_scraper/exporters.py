from __future__ import annotations

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


def export_google_sheet(scraped_events: list[ScrapedEvent], spreadsheet_id: str, credentials_json: str) -> None:
    try:
        import gspread
    except ImportError as exc:
        raise RuntimeError("Install 'gspread' to export to Google Sheets.") from exc

    credentials = json.loads(credentials_json)
    client = gspread.service_account_from_dict(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)
    events_df, organizers_df, relationships_df = flatten(scraped_events)
    _write_worksheet(spreadsheet, "Events", events_df)
    _write_worksheet(spreadsheet, "Organizers", organizers_df)
    _write_worksheet(spreadsheet, "Event Organizers", relationships_df)


def _write_worksheet(spreadsheet: Any, title: str, frame: pd.DataFrame) -> None:
    try:
        worksheet = spreadsheet.worksheet(title)
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1, cols=1)
    worksheet.clear()
    values = [frame.columns.tolist()] + frame.fillna("").astype(str).values.tolist()
    if values:
        worksheet.update(values, value_input_option="RAW")
