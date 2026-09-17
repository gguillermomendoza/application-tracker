from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token_sheets_readonly.json"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


def get_sheets_service():
    """
    Authenticate to Google Sheets with read-only access.

    Uses a token separate from Gmail so Gmail OAuth permissions
    remain completely independent.
    """
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_PATH),
            SHEETS_SCOPES,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SHEETS_SCOPES,
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

    return build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False,
    )


def get_spreadsheet_metadata(service, spreadsheet_id: str) -> dict:
    """
    Read spreadsheet title and tab metadata.
    """
    return (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields=(
                "properties(title),"
                "sheets(properties("
                "sheetId,title,index,"
                "gridProperties(rowCount,columnCount)"
                "))"
            ),
        )
        .execute()
    )


def read_values(
    service,
    spreadsheet_id: str,
    range_name: str,
) -> list[list[str]]:
    """
    Read cell values from one A1 range.
    """
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        )
        .execute()
    )

    return result.get("values", [])


def quote_sheet_name(sheet_name: str) -> str:
    """
    Quote a tab name for use in A1 notation.

    Example:
        Applications 2026 -> 'Applications 2026'
    """
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'"


def column_index_to_letter(index: int) -> str:
    """
    Convert a zero-based column index to A1 notation.

    0 -> A
    25 -> Z
    26 -> AA
    """
    number = index + 1
    letters = ""

    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters

    return letters
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SHEETS_READONLY_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

SHEETS_WRITE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

READONLY_TOKEN_PATH = Path("token_sheets_readonly.json")
WRITE_TOKEN_PATH = Path("token_sheets_write.json")
CREDENTIALS_PATH = Path("credentials.json")


def _get_sheets_credentials(
    *,
    scopes: list[str],
    token_path: Path,
) -> Credentials:
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_path),
            scopes,
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH),
            scopes,
        )
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json())

    return creds


def get_sheets_service():
    """
    Existing read-only Sheets service.
    """
    creds = _get_sheets_credentials(
        scopes=SHEETS_READONLY_SCOPES,
        token_path=READONLY_TOKEN_PATH,
    )

    return build(
        "sheets",
        "v4",
        credentials=creds,
    )


def get_sheets_write_service():
    """
    Writable Sheets service.

    Having this service does NOT authorize arbitrary application code
    to construct writes. It will eventually be consumed only by the
    constrained Sheet writer.
    """
    creds = _get_sheets_credentials(
        scopes=SHEETS_WRITE_SCOPES,
        token_path=WRITE_TOKEN_PATH,
    )

    return build(
        "sheets",
        "v4",
        credentials=creds,
    )
