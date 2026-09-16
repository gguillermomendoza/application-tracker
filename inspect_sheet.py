import os
from pprint import pprint

from src.sheets_client import get_sheets_service
from src.tracker_reader import read_tracker_applications


def main():
    spreadsheet_id = os.environ["TRACKER_SPREADSHEET_ID"]

    service = get_sheets_service()

    applications = read_tracker_applications(
        service=service,
        spreadsheet_id=spreadsheet_id,
    )

    print(f"Loaded {len(applications)} applications.\n")

    for application in applications[:5]:
        pprint(application.model_dump())


if __name__ == "__main__":
    main()
