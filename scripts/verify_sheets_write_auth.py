# verify_sheets_write_auth.py

import os

from src.sheets_client import get_sheets_write_service


def main():
    spreadsheet_id = os.environ["TRACKER_SPREADSHEET_ID"]

    service = get_sheets_write_service()

    metadata = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title",
        )
        .execute()
    )

    print("Authenticated writable Sheets client.")
    print("Spreadsheet:", metadata["properties"]["title"])
    print("WRITE PERFORMED: NO")


if __name__ == "__main__":
    main()
