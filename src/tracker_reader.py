from pydantic import BaseModel, ConfigDict

from src.sheets_client import read_values
from src.tracker_schema import (
    EXPECTED_HEADERS,
    FIRST_DATA_ROW,
    HEADER_ROW,
    TRACKER_SHEET_NAME,
)


class TrackerApplication(BaseModel):
    """
    Faithful typed representation of one existing application row.

    No normalization or interpretation should happen here.
    """

    model_config = ConfigDict(extra="forbid")

    row_number: int

    applied_date: str | None
    role: str | None
    company: str | None

    hiring_manager: str | None
    link: str | None
    connections: str | None

    status: str | None
    date_updated: str | None


def _cell_or_none(value: object) -> str | None:
    """
    Convert an empty or whitespace-only Sheet cell to None.

    Substantive user-entered content is preserved exactly, including
    leading/trailing whitespace. Normalization belongs in Phase 4b.
    """
    if value is None:
        return None

    text = str(value)

    if not text.strip():
        return None

    return text


def _pad_row(row: list[object], width: int) -> list[object]:
    """
    Sheets may omit trailing empty cells from returned rows.
    Restore the row to its expected logical width.
    """
    if len(row) > width:
        raise ValueError(
            f"Tracker row contains {len(row)} cells; expected at most {width}."
        )

    return row + [""] * (width - len(row))


def _is_blank_row(row: list[object]) -> bool:
    """Return True when every logical cell in the row is empty."""
    return all(_cell_or_none(cell) is None for cell in row)


def validate_tracker_headers(
    service,
    spreadsheet_id: str,
) -> None:
    """
    Fail safely if the live tracker schema no longer matches
    the schema the application was written against.
    """
    header_range = f"'{TRACKER_SHEET_NAME}'!{HEADER_ROW}:{HEADER_ROW}"

    rows = read_values(
        service=service,
        spreadsheet_id=spreadsheet_id,
        range_name=header_range,
    )

    if not rows:
        raise ValueError(
            f"No header row found in sheet {TRACKER_SHEET_NAME!r}."
        )

    actual_headers = rows[0]

    # Ignore Sheets' omission of trailing empty cells, but do not silently
    # accept additional named columns.
    while actual_headers and actual_headers[-1] == "":
        actual_headers.pop()

    if actual_headers != EXPECTED_HEADERS:
        raise ValueError(
            "Tracker schema mismatch.\n"
            f"Expected: {EXPECTED_HEADERS}\n"
            f"Actual:   {actual_headers}"
        )


def read_tracker_applications(
    service,
    spreadsheet_id: str,
) -> list[TrackerApplication]:
    """
    Read Application Tracker rows into typed Python objects.

    Read-only operation:
    - validates headers
    - skips rows 1 and 2
    - preserves source row numbers
    - skips entirely blank application rows
    - does not normalize, match, deduplicate, or modify data
    """
    validate_tracker_headers(
        service=service,
        spreadsheet_id=spreadsheet_id,
    )

    width = len(EXPECTED_HEADERS)

    # Explicit A:H keeps the mapping tied to the validated schema.
    data_range = (
        f"'{TRACKER_SHEET_NAME}'!"
        f"A{FIRST_DATA_ROW}:H"
    )

    rows = read_values(
        service=service,
        spreadsheet_id=spreadsheet_id,
        range_name=data_range,
    )

    applications: list[TrackerApplication] = []

    for row_number, raw_row in enumerate(rows, start=FIRST_DATA_ROW):
        row = _pad_row(raw_row, width)

        if _is_blank_row(row):
            continue

        application = TrackerApplication(
            row_number=row_number,
            applied_date=_cell_or_none(row[0]),
            role=_cell_or_none(row[1]),
            company=_cell_or_none(row[2]),
            hiring_manager=_cell_or_none(row[3]),
            link=_cell_or_none(row[4]),
            connections=_cell_or_none(row[5]),
            status=_cell_or_none(row[6]),
            date_updated=_cell_or_none(row[7]),
        )

        applications.append(application)

    return applications
