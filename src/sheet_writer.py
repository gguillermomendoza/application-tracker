from typing import Any

from src.tracker_schema import TRACKER_SHEET_NAME
from src.write_models import (
    ExistingApplicationUpdate,
    NewApplicationRow,
)

STATUS_COLUMN = "G"
DATE_UPDATED_COLUMN = "H"


def write_existing_application_update(
    *,
    service: Any,
    spreadsheet_id: str,
    intent: ExistingApplicationUpdate,
) -> dict:
    """
    Apply a validated existing-application update.

    This writer is deliberately constrained to:
      - Status
      - Date Updated

    It cannot accept arbitrary ranges, columns, or row dictionaries.
    """

    range_name = (
        f"'{TRACKER_SHEET_NAME}'!"
        f"{STATUS_COLUMN}{intent.row_number}:"
        f"{DATE_UPDATED_COLUMN}{intent.row_number}"
    )

    body = {
        "values": [
            [
                intent.status,
                intent.date_updated.isoformat(),
            ]
        ]
    }

    return (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body=body,
        )
        .execute()
    )
def write_new_application_row(
    *,
    service: Any,
    spreadsheet_id: str,
    intent: NewApplicationRow,
) -> dict:
    """
    Append a validated new application row.

    Automation controls only:
      A: Date
      B: Position/Program
      C: Company/Organization
      G: Status
      H: Date Updated

    D-F are intentionally left blank.
    """

    range_name = f"'{TRACKER_SHEET_NAME}'!A:H"

    body = {
        "values": [
            [
                intent.applied_date.isoformat(),  # A
                intent.role,                      # B
                intent.company,                   # C
                "",                               # D Hiring Manager
                "",                               # E Link
                "",                               # F Connections
                intent.status,                    # G
                intent.date_updated.isoformat(),  # H
            ]
        ]
    }

    return (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
        )
