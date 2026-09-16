import os
from pprint import pprint

from src.sheets_client import (
    column_index_to_letter,
    get_sheets_service,
    get_spreadsheet_metadata,
    quote_sheet_name,
    read_values,
)


STATUS_HEADER_TERMS = (
    "status",
    "stage",
)


def is_status_column(header: str) -> bool:
    normalized = header.strip().lower()

    return any(
        term in normalized
        for term in STATUS_HEADER_TERMS
    )


def main():
    spreadsheet_id = os.getenv("JOB_TRACKER_SPREADSHEET_ID")

    if not spreadsheet_id:
        raise RuntimeError(
            "JOB_TRACKER_SPREADSHEET_ID environment variable is not set."
        )

    service = get_sheets_service()

    metadata = get_spreadsheet_metadata(
        service,
        spreadsheet_id,
    )

    spreadsheet_title = metadata["properties"]["title"]

    print()
    print("=" * 70)
    print(f"Spreadsheet: {spreadsheet_title}")
    print("=" * 70)

    sheets = sorted(
        metadata.get("sheets", []),
        key=lambda sheet: sheet["properties"]["index"],
    )

    print("\nTabs:")

    for sheet in sheets:
        properties = sheet["properties"]

        print(
            f"  - {properties['title']} "
            f"(sheetId={properties['sheetId']})"
        )

    for sheet in sheets:
        title = sheet["properties"]["title"]
        quoted_title = quote_sheet_name(title)

        print()
        print("=" * 70)
        print(f"TAB: {title}")
        print("=" * 70)

        # Read header row only.
        header_rows = read_values(
            service,
            spreadsheet_id,
            f"{quoted_title}!1:1",
        )

        if not header_rows:
            print("No header/data found.")
            continue

        headers = header_rows[0]

        print("\nHeaders:")

        for index, header in enumerate(headers):
            column_letter = column_index_to_letter(index)
            print(f"  {column_letter}: {header!r}")

        # Read only five sample rows.
        sample_rows = read_values(
            service,
            spreadsheet_id,
            f"{quoted_title}!3:7",
        )

        print("\nExample rows:")

        if not sample_rows:
            print("  No data rows.")
        else:
            for row_number, row in enumerate(sample_rows, start=3):    
                padded_row = row + [""] * (len(headers) - len(row))

                row_dict = {
                    header: padded_row[index]
                    for index, header in enumerate(headers)
                    if header
                }

                print(f"\n  Row {row_number}:")
                pprint(row_dict, sort_dicts=False)

        # Find columns that look like Status or Stage.
        status_columns = [
            (index, header)
            for index, header in enumerate(headers)
            if header and is_status_column(header)
        ]

        if not status_columns:
            print("\nStatus-like columns: none detected")
            continue

        print("\nStatus-like columns:")

        for index, header in status_columns:
            column_letter = column_index_to_letter(index)

            status_rows = read_values(
                service,
                spreadsheet_id,
                f"{quoted_title}!{column_letter}3:{column_letter}"
            )

            unique_values = sorted(
                {
                    str(row[0]).strip()
                    for row in status_rows
                    if row and str(row[0]).strip()
                },
                key=str.lower,
            )

            print(
                f"\n  {header!r} "
                f"(column {column_letter})"
            )

            for value in unique_values:
                print(f"    - {value}")


if __name__ == "__main__":
    main()
