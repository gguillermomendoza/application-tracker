import os
from pathlib import Path

from googleapiclient.discovery import build

from src.oauth_credentials import load_user_oauth_credentials


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SHEETS_READONLY_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

SHEETS_WRITE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

CREDENTIALS_PATH = Path(
    os.getenv(
        "GOOGLE_OAUTH_CLIENT_SECRETS_PATH",
        str(PROJECT_ROOT / "credentials.json"),
    )
)

READONLY_TOKEN_PATH = Path(
    os.getenv(
        "SHEETS_READONLY_TOKEN_PATH",
        str(PROJECT_ROOT / "token_sheets_readonly.json"),
    )
)

WRITE_TOKEN_PATH = Path(
    os.getenv(
        "SHEETS_WRITE_TOKEN_PATH",
        str(PROJECT_ROOT / "token_sheets_write.json"),
    )
)


def _env_flag(
    name: str,
    default: bool,
) -> bool:
    default_value = "true" if default else "false"

    return (
        os.getenv(name, default_value)
        .strip()
        .lower()
        == "true"
    )


def _get_sheets_credentials(
    *,
    scopes: list[str],
    token_path: Path,
):
    return load_user_oauth_credentials(
        token_path=token_path,
        client_secrets_path=CREDENTIALS_PATH,
        scopes=scopes,
        allow_interactive=_env_flag(
            "ALLOW_INTERACTIVE_OAUTH",
            True,
        ),
        persist_token=_env_flag(
            "PERSIST_OAUTH_TOKENS",
            True,
        ),
    )


def get_sheets_service():
    """
    Authenticate to Google Sheets with read-only access.

    Uses a token separate from Gmail and from the writable
    Sheets token so each OAuth permission set remains isolated.
    """
    creds = _get_sheets_credentials(
        scopes=SHEETS_READONLY_SCOPES,
        token_path=READONLY_TOKEN_PATH,
    )

    return build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False,
    )


def get_sheets_write_service():
    """
    Authenticate to Google Sheets with write access.

    This uses a separate OAuth token from the read-only Sheets
    service. Application code should still construct writes only
    through the constrained Sheet writer.
    """
    creds = _get_sheets_credentials(
        scopes=SHEETS_WRITE_SCOPES,
        token_path=WRITE_TOKEN_PATH,
    )

    return build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False,
    )


def get_spreadsheet_metadata(
    service,
    spreadsheet_id: str,
) -> dict:
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


def quote_sheet_name(
    sheet_name: str,
) -> str:
    """
    Quote a tab name for use in A1 notation.

    Example:
        Applications 2026 -> 'Applications 2026'
    """
    escaped = sheet_name.replace(
        "'",
        "''",
    )

    return f"'{escaped}'"


def column_index_to_letter(
    index: int,
) -> str:
    """
    Convert a zero-based column index to A1 notation.

    0 -> A
    25 -> Z
    26 -> AA
    """
    number = index + 1
    letters = ""

    while number:
        number, remainder = divmod(
            number - 1,
            26,
        )

        letters = (
            chr(65 + remainder)
            + letters
        )

    return letters
