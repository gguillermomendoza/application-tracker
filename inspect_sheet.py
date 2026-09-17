import os

from src.normalization import normalize_company, normalize_role
from src.sheets_client import get_sheets_service
from src.tracker_reader import read_tracker_applications
from src.matching import find_exact_application_matches
from src.matching import classify_exact_matches
def main():
    spreadsheet_id = os.environ["TRACKER_SPREADSHEET_ID"]

    service = get_sheets_service()

    applications = read_tracker_applications(
        service,
        spreadsheet_id,
    )

    print(f"Loaded {len(applications)} applications.\n")

    for application in applications[-50:-20]:
        print(f"Row {application.row_number}")
        print(f"  Company: {application.company!r}")
        print(f"  Normalized company: {normalize_company(application.company)!r}")
        print(f"  Role: {application.role!r}")
        print(f"  Normalized role: {normalize_role(application.role)!r}")
        print()
    matches = find_exact_application_matches(
    company="Simon Kuchner",
    role="Associate Consultant",
    applications=applications,
    )   

    print(f"Matches found: {len(matches)}")

    for match in matches:
        print(
            f"Row {match.row_number}: "
            f"{match.company} — {match.role} — {match.status}"
        )
    result, matches = classify_exact_matches(
    role="Associate Consultant",
    company="Simon Kuchner",
    applications=applications,
    )   

    print(f"Match result: {result.value}")
    print(f"Matching rows: {[match.row_number for match in matches]}")

if __name__ == "__main__":
     main()
