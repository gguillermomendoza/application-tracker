import os

from src.normalization import normalize_company, normalize_role
from src.sheets_client import get_sheets_service
from src.tracker_reader import read_tracker_applications


def main():
    spreadsheet_id = os.environ["TRACKER_SPREADSHEET_ID"]

    service = get_sheets_service()

    applications = read_tracker_applications(
        service,
        spreadsheet_id,
    )

    print(f"Loaded {len(applications)} applications.\n")

    for application in applications[:10]:
        print(f"Row {application.row_number}")
        print(f"  Company: {application.company!r}")
        print(f"  Normalized company: {normalize_company(application.company)!r}")
        print(f"  Role: {application.role!r}")
        print(f"  Normalized role: {normalize_role(application.role)!r}")
        print()


if __name__ == "__main__":
    main()
