import pytest

from src.application_source import (
    detect_application_source,
)


@pytest.mark.parametrize(
    ("sender", "expected"),
    [
        (
            "Handshake <jobs@notifications.joinhandshake.com>",
            "Handshake",
        ),
        (
            "LinkedIn <jobs-noreply@linkedin.com>",
            "LinkedIn",
        ),
        (
            "Indeed <jobs@indeed.com>",
            "Indeed",
        ),
        (
            "Recruiting <recruiting@example.com>",
            "Unknown role",
        ),
    ],
)
def test_detect_application_source(
    sender,
    expected,
):
    assert detect_application_source(sender) == expected
