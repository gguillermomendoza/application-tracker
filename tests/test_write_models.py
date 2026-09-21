from datetime import date

import pytest
from pydantic import ValidationError

from src.decision_engine import ApplicationDecision, DecisionAction
from src.write_models import (
    ExistingApplicationUpdate,
    NewApplicationRow,
    WriteIntentError,
    decision_to_write_intent,
)


TODAY = date(2026, 9, 16)


def test_update_decision_builds_existing_application_update():
    decision = ApplicationDecision(
        action=DecisionAction.UPDATE,
        existing_row=37,
        company="Pinecone",
        role="Associate Field Engineer",
        current_status="Applied",
        proposed_status="Performance Task",
        reason="assessment event matched one existing application",
    )

    intent = decision_to_write_intent(
        decision,
        date_updated=TODAY,
    )

    assert intent == ExistingApplicationUpdate(
        row_number=37,
        status="Performance Task",
        date_updated=TODAY,
    )


def test_create_decision_builds_new_application_row():
    decision = ApplicationDecision(
        action=DecisionAction.CREATE,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status=None,
        proposed_status="Applied",
        reason="explicit application confirmation",
    )

    intent = decision_to_write_intent(
        decision,
        applied_date=TODAY,
        date_updated=TODAY,
    )

    assert intent == NewApplicationRow(
        applied_date=TODAY,
        role="Data Scientist",
        company="Example Corp",
        status="Applied",
        date_updated=TODAY,
    )


@pytest.mark.parametrize(
    "action",
    [
        DecisionAction.REVIEW,
        DecisionAction.IGNORE,
    ],
)
def test_review_and_ignore_never_produce_write_intent(action):
    decision = ApplicationDecision(
        action=action,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status=None,
        proposed_status=None,
        reason="no write should occur",
    )

    intent = decision_to_write_intent(
        decision,
        date_updated=TODAY,
    )

    assert intent is None


def test_update_without_existing_row_fails_closed():
    decision = ApplicationDecision(
        action=DecisionAction.UPDATE,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status="Applied",
        proposed_status="Performance Task",
        reason="malformed update",
    )

    with pytest.raises(WriteIntentError):
        decision_to_write_intent(
            decision,
            date_updated=TODAY,
        )


def test_create_without_applied_date_fails_closed():
    decision = ApplicationDecision(
        action=DecisionAction.CREATE,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status=None,
        proposed_status="Applied",
        reason="new application",
    )

    with pytest.raises(WriteIntentError):
        decision_to_write_intent(
            decision,
            date_updated=TODAY,
        )


def test_existing_application_update_cannot_target_instruction_row():
    with pytest.raises(ValidationError):
        ExistingApplicationUpdate(
            row_number=2,
            status="Performance Task",
            date_updated=TODAY,
        )


def test_existing_application_update_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ExistingApplicationUpdate(
            row_number=10,
            status="Some New Status",
            date_updated=TODAY,
        )


def test_existing_application_update_forbids_extra_columns():
    with pytest.raises(ValidationError):
        ExistingApplicationUpdate(
            row_number=10,
            status="Performance Task",
            date_updated=TODAY,
            hiring_manager="Do not write this",  # type: ignore[call-arg]
        )


def test_new_application_row_forbids_extra_columns():
    with pytest.raises(ValidationError):
        NewApplicationRow(
            applied_date=TODAY,
            role="Data Scientist",
            company="Example Corp",
            status="Applied",
            date_updated=TODAY,
            link="https://example.com",  # type: ignore[call-arg]
        )


def test_create_cannot_use_non_applied_status():
    with pytest.raises(ValidationError):
        NewApplicationRow(
            applied_date=TODAY,
            role="Data Scientist",
            company="Example Corp",
            status="Offer",  # type: ignore[arg-type]
            date_updated=TODAY,)
def test_create_without_role_accepts_explicit_fallback():
    decision = ApplicationDecision(
        action=DecisionAction.CREATE,
        existing_row=None,
        company="Example Corp",
        role=None,
        current_status=None,
        proposed_status="Applied",
        reason="explicit application confirmation",
    )

    intent = decision_to_write_intent(
        decision,
        applied_date=TODAY,
        date_updated=TODAY,
        create_role_fallback="Handshake",
    )

    assert intent == NewApplicationRow(
        applied_date=TODAY,
        role="Handshake",
        company="Example Corp",
        status="Applied",
        date_updated=TODAY,
    )


def test_create_without_role_or_fallback_fails_closed():
    decision = ApplicationDecision(
        action=DecisionAction.CREATE,
        existing_row=None,
        company="Example Corp",
        role=None,
        current_status=None,
        proposed_status="Applied",
        reason="explicit application confirmation",
    )

    with pytest.raises(
        WriteIntentError,
        match="CREATE decision is missing role",
    ):
        decision_to_write_intent(
            decision,
            applied_date=TODAY,
            date_updated=TODAY,
        )


def test_create_fallback_does_not_override_real_role():
    decision = ApplicationDecision(
        action=DecisionAction.CREATE,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status=None,
        proposed_status="Applied",
        reason="explicit application confirmation",
    )

    intent = decision_to_write_intent(
        decision,
        applied_date=TODAY,
        date_updated=TODAY,
        create_role_fallback="Handshake",
    )

    assert intent.role == "Data Scientist"
