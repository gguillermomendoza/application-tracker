from datetime import date
from unittest.mock import MagicMock
from src.sheet_writer import (
    write_existing_application_update,
    write_new_application_row,
)
from src.write_models import (
    ExistingApplicationUpdate,
    NewApplicationRow,
)

def test_existing_application_writer_targets_only_status_and_date_updated():
    service = MagicMock()

    execute_result = {
        "updatedRange": "'Application Tracker'!G37:H37",
        "updatedRows": 1,
        "updatedColumns": 2,
    }

    (
        service.spreadsheets.return_value
        .values.return_value
        .update.return_value
        .execute.return_value
    ) = execute_result

    intent = ExistingApplicationUpdate(
        row_number=37,
        status="Performance Task",
        date_updated=date(2026, 9, 16),
    )

    result = write_existing_application_update(
        service=service,
        spreadsheet_id="test-spreadsheet-id",
        intent=intent,
    )

    service.spreadsheets.return_value.values.return_value.update.assert_called_once_with(
        spreadsheetId="test-spreadsheet-id",
        range="'Application Tracker'!G37:H37",
        valueInputOption="RAW",
        body={
            "values": [
                [
                    "Performance Task",
                    "2026-09-16",
                ]
            ]
        },
    )

    assert result == execute_result
def test_writer_uses_target_row_from_validated_intent_only():
    service = MagicMock()

    (
        service.spreadsheets.return_value
        .values.return_value
        .update.return_value
        .execute.return_value
    ) = {}

    intent = ExistingApplicationUpdate(
        row_number=125,
        status="Rejected: App",
        date_updated=date(2026, 9, 16),
    )

    write_existing_application_update(
        service=service,
        spreadsheet_id="test-spreadsheet-id",
        intent=intent,
    )

    call = (
        service.spreadsheets.return_value
        .values.return_value
        .update.call_args
    )

    assert call.kwargs["range"] == "'Application Tracker'!G125:H125"
    assert call.kwargs["body"] == {
        "values": [["Rejected: App", "2026-09-16"]]
    }
def test_new_application_writer_populates_only_allowed_columns():
    service = MagicMock()

    execute_result = {
        "updates": {
            "updatedRange": "'Application Tracker'!A50:H50",
            "updatedRows": 1,
        }
    }

    (
        service.spreadsheets.return_value
        .values.return_value
        .append.return_value
        .execute.return_value
    ) = execute_result

    intent = NewApplicationRow(
        applied_date=date(2026, 9, 16),
        role="Data Scientist",
        company="Example Corp",
        status="Applied",
        date_updated=date(2026, 9, 16),
    )

    result = write_new_application_row(
        service=service,
        spreadsheet_id="test-spreadsheet-id",
        intent=intent,
    )

    service.spreadsheets.return_value.values.return_value.append.assert_called_once_with(
        spreadsheetId="test-spreadsheet-id",
        range="'Application Tracker'!A:H",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={
            "values": [
                [
                    "2026-09-16",
                    "Data Scientist",
                    "Example Corp",
                    "",
                    "",
                    "",
                    "Applied",
                    "2026-09-16",
                ]
            ]
        },
    )

    assert result == execute_result
def test_new_application_writer_leaves_user_managed_columns_blank():
    service = MagicMock()

    (
        service.spreadsheets.return_value
        .values.return_value
        .append.return_value
        .execute.return_value
    ) = {}

    intent = NewApplicationRow(
        applied_date=date(2026, 9, 16),
        role="Software Engineer",
        company="Example Corp",
        status="Applied",
        date_updated=date(2026, 9, 16),
    )

    write_new_application_row(
        service=service,
        spreadsheet_id="test-spreadsheet-id",
        intent=intent,
    )

    call = (
        service.spreadsheets.return_value
        .values.return_value
        .append.call_args
    )

    row = call.kwargs["body"]["values"][0]

    assert row[3] == ""  # Hiring Manager
    assert row[4] == ""  # Link
    assert row[5] == ""  # Connections
