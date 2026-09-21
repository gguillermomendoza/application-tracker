from email.utils import parseaddr


_SOURCE_LABELS_BY_DOMAIN = (
    (
        "notifications.joinhandshake.com",
        "Handshake",
    ),
    (
        "linkedin.com",
        "LinkedIn",
    ),
    (
        "indeed.com",
        "Indeed",
    ),
)


def detect_application_source(
    sender: str,
) -> str:
    """
    Derive a deterministic Position/Program fallback from the
    sender's email domain.

    This function does not use Gemini and does not infer a job role.
    """

    _, address = parseaddr(sender)

    normalized_address = address.strip().casefold()

    domain = normalized_address.rsplit(
        "@",
        maxsplit=1,
    )[-1]

    for expected_domain, label in _SOURCE_LABELS_BY_DOMAIN:
        if (
            domain == expected_domain
            or domain.endswith(
                f".{expected_domain}"
            )
        ):
            return label

    return "Unknown role"
