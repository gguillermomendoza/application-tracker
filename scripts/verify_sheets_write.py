import os
from datetime import date

from src.sheet_writer import (
    write_existing_application_update,
    write_new_application_row,
)
from src.sheets_client import get_sheets_write_service
from src.write_models import (
    ExistingApplicationUpdate,
    NewApplicationRow,
)


TEST_SPREADSHEET_ENV = "SHEETS_WRITE_TEST_SPREADSHEET_ID"
PRODUCTION_SPREADSHEET_ENV = "TRACKER_SPREADSHEET_ID"


def get_test_spreadsheet_id() -> str:
    spreadsheet_id = os.environ.get(TEST_SPREADSHEET_ENV)

    if not spreadsheet_id:
        raise SystemExit(
            f"{TEST_SPREADSHEET_ENV} is required. "
            "This script must target a disposable test spreadsheet."
        )

    production_id = os.environ.get(PRODUCTION_SPREADSHEET_ENV)

    if production_id and spreadsheet_id == production_id:
        raise SystemExit(
            "Refusing to run: test spreadsheet ID matches "
            "TRACKER_SPREADSHEET_ID."
        )

    return spreadsheet_id


def confirm_write(description: str) -> None:
    print()
    print("ABOUT TO PERFORM A REAL WRITE TO A TEST SPREADSHEET")
    print(description)
    print()

    confirmation = input("Type WRITE to continue: ")

    if confirmation != "WRITE":
        raise SystemExit("Write cancelled.")


def test_update(service, spreadsheet_id: str) -> None:
    row_number = 3

    intent = ExistingApplicationUpdate(
        row_number=row_number,
        status="Performance Task",
        date_updated=date.today(),
    )

    confirm_write(
        f"UPDATE row {intent.row_number}: "
        f"Status={intent.status!r}, "
        f"Date Updated={intent.date_updated}"
    )

    result = write_existing_application_update(
        service=service,
        spreadsheet_id=spreadsheet_id,
        intent=intent,
    )

    print("WRITE SUCCEEDED")
    print(result)


def test_create(service, spreadsheet_id: str) -> None:
    intent = NewApplicationRow(
        applied_date=date.today(),
        role="WRITE TEST - Data Scientist",
        company="WRITE TEST - Example Corp",
        status="Applied",
        date_updated=date.today(),
    )

    confirm_write(
        "APPEND test application: "
        f"{intent.company} / {intent.role}"
    )

    result = write_new_application_row(
        service=service,
        spreadsheet_id=spreadsheet_id,
        intent=intent,
    )

    print("WRITE SUCCEEDED")
    print(result)


def main() -> None:
    spreadsheet_id = get_test_spreadsheet_id()
    service = get_sheets_write_service()

    print("Target: disposable test spreadsheet")
    print()
    print("1. Test UPDATE")
    print("2. Test CREATE")

    choice = input("Choose test: ").strip()

    if choice == "1":
        test_update(service, spreadsheet_id)
    elif choice == "2":
        test_create(service, spreadsheet_id)
    else:
        raise SystemExit("Invalid choice.")


if __name__ == "__main__":
    main()
