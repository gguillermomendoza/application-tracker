from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


def load_user_oauth_credentials(
    *,
    token_path: str | Path,
    client_secrets_path: str | Path,
    scopes: Sequence[str],
    allow_interactive: bool,
    persist_token: bool,
) -> Credentials:
    token_path = Path(token_path)
    client_secrets_path = Path(client_secrets_path)

    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_path),
            scopes=scopes,
        )

    if creds is not None and not creds.valid and creds.refresh_token:
        creds.refresh(Request())

        if persist_token:
            token_path.write_text(
                creds.to_json(),
                encoding="utf-8",
            )

    if creds is not None and creds.valid:
        return creds

    if not allow_interactive:
        raise RuntimeError(
            "OAuth credentials are unavailable or invalid and "
            "interactive OAuth is disabled."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets_path),
        scopes=scopes,
    )

    creds = flow.run_local_server(port=0)

    if persist_token:
        token_path.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

    return creds
