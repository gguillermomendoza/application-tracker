import base64
import html
import os
import re
from pathlib import Path

from googleapiclient.discovery import build

from src.oauth_credentials import load_user_oauth_credentials


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

ROOT = Path(__file__).resolve().parents[1]

CREDENTIALS_PATH = Path(
    os.getenv(
        "GOOGLE_OAUTH_CLIENT_SECRETS_PATH",
        str(ROOT / "credentials.json"),
    )
)

TOKEN_PATH = Path(
    os.getenv(
        "GMAIL_TOKEN_PATH",
        str(ROOT / "token.json"),
    )
)


def get_gmail_service():
    allow_interactive = (
        os.getenv("ALLOW_INTERACTIVE_OAUTH", "true").lower()
        == "true"
    )

    persist_token = (
        os.getenv("PERSIST_OAUTH_TOKENS", "true").lower()
        == "true"
    )

    creds = load_user_oauth_credentials(
        token_path=TOKEN_PATH,
        client_secrets_path=CREDENTIALS_PATH,
        scopes=SCOPES,
        allow_interactive=allow_interactive,
        persist_token=persist_token,
    )

    return build(
        "gmail",
        "v1",
        credentials=creds,
    )


def _decode_base64url(data: str) -> str:
    padding = "=" * (-len(data) % 4)

    decoded = base64.urlsafe_b64decode(data + padding)

    return decoded.decode(
        "utf-8",
        errors="replace",
    )


def _get_part_data(
    service,
    message_id: str,
    part: dict,
) -> str:
    body = part.get("body", {})

    data = body.get("data")

    if data:
        return _decode_base64url(data)

    attachment_id = body.get("attachmentId")

    if attachment_id:
        attachment = (
            service.users()
            .messages()
            .attachments()
            .get(
                userId="me",
                messageId=message_id,
                id=attachment_id,
            )
            .execute()
        )

        attachment_data = attachment.get("data")

        if attachment_data:
            return _decode_base64url(
                attachment_data
            )

    return ""


def _html_to_text(value: str) -> str:
    value = re.sub(
        r"<(script|style).*?>.*?</\1>",
        "",
        value,
        flags=re.DOTALL | re.IGNORECASE,
    )

    value = re.sub(
        r"<br\s*/?>",
        "\n",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"</p>",
        "\n",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"<[^>]+>",
        "",
        value,
    )

    return html.unescape(value).strip()


def _extract_body(
    service,
    message_id: str,
    payload: dict,
) -> str:
    plain_parts = []
    html_parts = []

    def walk(part: dict):
        mime_type = part.get(
            "mimeType",
            "",
        )

        filename = part.get(
            "filename",
            "",
        )

        # Do not send resume/document attachments
        # or other attached files to Gemini.
        if filename:
            return

        if mime_type == "text/plain":
            text = _get_part_data(
                service,
                message_id,
                part,
            )

            if text:
                plain_parts.append(text)

        elif mime_type == "text/html":
            text = _get_part_data(
                service,
                message_id,
                part,
            )

            if text:
                html_parts.append(text)

        for child in part.get(
            "parts",
            [],
        ):
            walk(child)

    walk(payload)

    if plain_parts:
        return "\n".join(
            plain_parts
        ).strip()

    if html_parts:
        return _html_to_text(
            "\n".join(
                html_parts
            )
        )

    return ""


def _get_header(
    headers: list[dict],
    name: str,
) -> str:
    for header in headers:
        if (
            header.get(
                "name",
                "",
            ).lower()
            == name.lower()
        ):
            return header.get(
                "value",
                "",
            )

    return ""


def fetch_recent_messages(
    max_results: int = 20,
    query: str | None = None,
) -> list[dict]:
    service = get_gmail_service()

    result = (
        service.users()
        .messages()
        .list(
            userId="me",
            maxResults=max_results,
            q=query,
        )
        .execute()
    )

    messages = result.get(
        "messages",
        [],
    )

    parsed_messages = []

    for message_ref in messages:
        message_id = message_ref["id"]

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

        payload = message.get(
            "payload",
            {},
        )

        headers = payload.get(
            "headers",
            [],
        )

        parsed_messages.append(
            {
                "message_id": message_id,
                "subject": _get_header(
                    headers,
                    "Subject",
                ),
                "sender": _get_header(
                    headers,
                    "From",
                ),
                "received_at": _get_header(
                    headers,
                    "Date",
                ),
                "body": _extract_body(
                    service,
                    message_id,
                    payload,
                ),
            }
        )

    return parsed_messages
