import builtins
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import main
from src.decision_engine import ApplicationDecision, DecisionAction
from src.schemas import ApplicationEvent, EventType
from src.write_models import (
    ExistingApplicationUpdate,
    NewApplicationRow,
    WriteIntentError,
)


class FakeProcessedMessageStore:
    def __init__(self):
        self.processed = set()

    def has_processed_message(
        self,
        message_id: str,
    ) -> bool:
        return message_id in self.processed

    def mark_message_processed(
        self,
        message_id: str,
    ) -> None:
        self.processed.add(message_id)


class FakeReviewQueueStore:
    def __init__(self):
        self.items = []

    def add_review_item(
        self,
        item,
    ) -> None:
        self.items.append(item)


SPREADSHEET_ID = "test-spreadsheet-id"
MESSAGE_ID = "gmail-message-123"


def make_message() -> dict:
    return {
        "message_id": MESSAGE_ID,
        "subject": "Application update",
        "sender": "recruiting@example.com",
    }


def make_update_decision() -> ApplicationDecision:
    return ApplicationDecision(
        action=DecisionAction.UPDATE,
        existing_row=37,
        company="Example Corp",
        role="Data Scientist",
        current_status="Applied",
        proposed_status="Performance Task",
        reason="assessment event matched one existing application",
    )


def make_create_decision() -> ApplicationDecision:
    return ApplicationDecision(
        action=DecisionAction.CREATE,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status=None,
        proposed_status="Applied",
        reason="explicit application confirmation",
    )

def make_event(
    *,
    event_type: EventType = EventType.ASSESSMENT,
    event_date: str | None = "2026-09-17",
    role: str | None = "Data Scientist",
) -> ApplicationEvent:
    return ApplicationEvent(
        company="Example Corp",
        role=role,
        event_type=event_type,
        event_date=event_date,
        explicit_application_confirmation=(
            event_type == EventType.APPLIED
        ),
        confidence=0.99,
    )


@pytest.fixture
def mocked_dependencies(monkeypatch):
    write_service = MagicMock(
        name="write_service"
    )

    get_write_service = MagicMock(
        name="get_sheets_write_service",
        return_value=write_service,
    )

    update_writer = MagicMock(
        name="write_existing_application_update",
        return_value={
            "updatedRows": 1,
        },
    )

    create_writer = MagicMock(
        name="write_new_application_row",
        return_value={
            "updates": {
                "updatedRows": 1,
            }
        },
    )

    confirmation = MagicMock(
        name="input",
        return_value="WRITE",
    )

    review_queue = FakeReviewQueueStore()

    monkeypatch.setattr(
        main,
        "get_sheets_write_service",
        get_write_service,
    )
    monkeypatch.setattr(
        main,
        "write_existing_application_update",
        update_writer,
    )
    monkeypatch.setattr(
        main,
        "write_new_application_row",
        create_writer,
    )
    monkeypatch.setattr(
        builtins,
        "input",
        confirmation,
    )

    return SimpleNamespace(
        write_service=write_service,
        get_write_service=get_write_service,
        update_writer=update_writer,
        create_writer=create_writer,
        confirmation=confirmation,
        review_queue=review_queue,
    )


def test_update_writes_once_then_marks_message_processed(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    result = main.handle_application_decision(
        decision=make_update_decision(),
        event=make_event(),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
    )

    assert result is True

    mocked_dependencies.update_writer.assert_called_once()
    mocked_dependencies.create_writer.assert_not_called()

    call = mocked_dependencies.update_writer.call_args

    assert (
        call.kwargs["service"]
        is mocked_dependencies.write_service
    )
    assert (
        call.kwargs["spreadsheet_id"]
        == SPREADSHEET_ID
    )

    intent = call.kwargs["intent"]

    assert isinstance(
        intent,
        ExistingApplicationUpdate,
    )
    assert intent.row_number == 37
    assert intent.status == "Performance Task"

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []


def test_create_writes_once_then_marks_message_processed(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    result = main.handle_application_decision(
        decision=make_create_decision(),
        event=make_event(
            event_type=EventType.APPLIED,
            event_date="2026-09-16",
        ),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
    )

    assert result is True

    mocked_dependencies.create_writer.assert_called_once()
    mocked_dependencies.update_writer.assert_not_called()

    call = mocked_dependencies.create_writer.call_args
    intent = call.kwargs["intent"]

    assert isinstance(
        intent,
        NewApplicationRow,
    )
    assert intent.company == "Example Corp"
    assert intent.role == "Data Scientist"
    assert (
        intent.applied_date.isoformat()
        == "2026-09-16"
    )
    assert intent.status == "Applied"

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []

def test_missing_role_create_uses_sender_fallback(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    decision = ApplicationDecision(
        action=DecisionAction.CREATE,
        existing_row=None,
        company="Tata Consultancy Services",
        role=None,
        current_status=None,
        proposed_status="Applied",
        reason="explicit application confirmation",
    )

    message = make_message()
    message["sender"] = (
        "Handshake "
        "<jobs@notifications.joinhandshake.com>"
    )

    result = main.handle_application_decision(
        decision=decision,
        event=make_event(
            event_type=EventType.APPLIED,
            event_date="2026-09-17",
            role=None,
        ),
        message=message,
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
        auto_write=True,
    )

    assert result is True

    mocked_dependencies.create_writer.assert_called_once()

    intent = (
        mocked_dependencies
        .create_writer
        .call_args
        .kwargs["intent"]
    )

    assert isinstance(
        intent,
        NewApplicationRow,
    )
    assert intent.company == "Tata Consultancy Services"
    assert intent.role == "Handshake"
    assert intent.status == "Applied"

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

def test_writer_exception_does_not_mark_message_processed(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    mocked_dependencies.update_writer.side_effect = RuntimeError(
        "Sheets API failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Sheets API failed",
    ):
        main.handle_application_decision(
            decision=make_update_decision(),
            event=make_event(),
            message=make_message(),
            spreadsheet_id=SPREADSHEET_ID,
            processed_store=processed_store,
            review_queue=mocked_dependencies.review_queue,
        )

    mocked_dependencies.update_writer.assert_called_once()

    assert not processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []


@pytest.mark.parametrize(
    "action",
    [
        DecisionAction.REVIEW,
        DecisionAction.IGNORE,
    ],
)
def test_review_and_ignore_never_write(
    action,
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    decision = ApplicationDecision(
        action=action,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status=None,
        proposed_status=None,
        reason="no write required",
    )

    result = main.handle_application_decision(
        decision=decision,
        event=make_event(),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
    )

    assert result is False

    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()
    mocked_dependencies.confirmation.assert_not_called()

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    if action == DecisionAction.REVIEW:
        assert len(
            mocked_dependencies.review_queue.items
        ) == 1

        item = mocked_dependencies.review_queue.items[0]

        assert item.gmail_message_id == MESSAGE_ID
        assert item.company == "Example Corp"
        assert item.role == "Data Scientist"
        assert item.event_type == "assessment"
        assert item.confidence == 0.99
        assert item.reason == "no write required"

    else:
        assert mocked_dependencies.review_queue.items == []

def test_decision_log_includes_reason(
    monkeypatch,
):
    processed_store = FakeProcessedMessageStore()
    review_queue = FakeReviewQueueStore()

    log_event = MagicMock()

    monkeypatch.setattr(
        main,
        "log_event",
        log_event,
    )

    decision = ApplicationDecision(
        action=DecisionAction.IGNORE,
        company="Example Corp",
        role="Data Scientist",
        reason="application is already represented in the tracker",
    )

    result = main.handle_application_decision(
        decision=decision,
        event=make_event(),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=review_queue,
    )

    assert result is False

    log_event.assert_called_once_with(
        "decision_made",
        message_id=MESSAGE_ID,
        decision="ignore",
        reason=(
            "application is already represented "
            "in the tracker"
        ),
        existing_row=None,
        current_status=None,
        proposed_status=None,
    )

def test_create_without_event_date_never_writes(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    result = main.handle_application_decision(
        decision=make_create_decision(),
        event=make_event(
            event_type=EventType.APPLIED,
            event_date=None,
        ),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
    )

    assert result is False

    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.confirmation.assert_not_called()

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert len(
        mocked_dependencies.review_queue.items
    ) == 1

    item = mocked_dependencies.review_queue.items[0]

    assert item.gmail_message_id == MESSAGE_ID
    assert item.company == "Example Corp"
    assert item.role == "Data Scientist"
    assert item.event_type == "applied"
    assert (
        item.reason
        == "CREATE event does not contain "
        "an explicit application date."
    )


def test_create_with_malformed_event_date_never_writes(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    result = main.handle_application_decision(
        decision=make_create_decision(),
        event=make_event(
            event_type=EventType.APPLIED,
            event_date="09/17/2026",
        ),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
    )

    assert result is False

    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.confirmation.assert_not_called()

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert len(
        mocked_dependencies.review_queue.items
    ) == 1

    item = mocked_dependencies.review_queue.items[0]

    assert item.gmail_message_id == MESSAGE_ID
    assert item.company == "Example Corp"
    assert item.role == "Data Scientist"
    assert item.event_type == "applied"
    assert (
        item.reason
        == "CREATE event contains invalid "
        "application date: '09/17/2026'"
    )


def test_review_queue_failure_does_not_mark_processed(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    decision = ApplicationDecision(
        action=DecisionAction.REVIEW,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status=None,
        proposed_status=None,
        reason="needs review",
    )

    mocked_dependencies.review_queue.add_review_item = MagicMock(
        side_effect=RuntimeError(
            "Firestore unavailable"
        )
    )

    with pytest.raises(
        RuntimeError,
        match="Firestore unavailable",
    ):
        main.handle_application_decision(
            decision=decision,
            event=make_event(),
            message=make_message(),
            spreadsheet_id=SPREADSHEET_ID,
            processed_store=processed_store,
            review_queue=mocked_dependencies.review_queue,
        )

    assert not processed_store.has_processed_message(
        MESSAGE_ID
    )

    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()
    mocked_dependencies.confirmation.assert_not_called()


def test_malformed_write_decision_fails_closed(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    malformed_decision = ApplicationDecision(
        action=DecisionAction.UPDATE,
        existing_row=None,
        company="Example Corp",
        role="Data Scientist",
        current_status="Applied",
        proposed_status="Performance Task",
        reason="malformed update",
    )

    with pytest.raises(WriteIntentError):
        main.handle_application_decision(
            decision=malformed_decision,
            event=make_event(),
            message=make_message(),
            spreadsheet_id=SPREADSHEET_ID,
            processed_store=processed_store,
            review_queue=mocked_dependencies.review_queue,
        )

    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()

    assert not processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []


def test_unsupported_write_intent_fails_closed(
    mocked_dependencies,
    monkeypatch,
):
    processed_store = FakeProcessedMessageStore()

    monkeypatch.setattr(
        main,
        "decision_to_write_intent",
        MagicMock(
            return_value=object()
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Unsupported write intent type",
    ):
        main.handle_application_decision(
            decision=make_update_decision(),
            event=make_event(),
            message=make_message(),
            spreadsheet_id=SPREADSHEET_ID,
            processed_store=processed_store,
            review_queue=mocked_dependencies.review_queue,
        )

    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()
    mocked_dependencies.confirmation.assert_not_called()

    assert not processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []


def test_cancelled_manual_write_does_not_write_or_mark_processed(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    mocked_dependencies.confirmation.return_value = "NO"

    result = main.handle_application_decision(
        decision=make_update_decision(),
        event=make_event(),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
    )

    assert result is False

    mocked_dependencies.confirmation.assert_called_once()
    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()

    assert not processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []


def test_auto_write_defaults_to_false(
    monkeypatch,
):
    monkeypatch.delenv(
        "AUTO_WRITE",
        raising=False,
    )

    assert main.auto_write_enabled() is False


@pytest.mark.parametrize(
    "value",
    [
        "true",
        "TRUE",
        "True",
        " true ",
    ],
)
def test_auto_write_accepts_true_case_insensitively(
    monkeypatch,
    value,
):
    monkeypatch.setenv(
        "AUTO_WRITE",
        value,
    )

    assert main.auto_write_enabled() is True


@pytest.mark.parametrize(
    "value",
    [
        "false",
        "FALSE",
        "",
        "1",
        "yes",
        "enabled",
    ],
)
def test_auto_write_rejects_non_true_values(
    monkeypatch,
    value,
):
    monkeypatch.setenv(
        "AUTO_WRITE",
        value,
    )

    assert main.auto_write_enabled() is False


def test_auto_write_update_skips_confirmation(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    result = main.handle_application_decision(
        decision=make_update_decision(),
        event=make_event(),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
        auto_write=True,
    )

    assert result is True

    mocked_dependencies.confirmation.assert_not_called()
    mocked_dependencies.update_writer.assert_called_once()
    mocked_dependencies.create_writer.assert_not_called()

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []


def test_auto_write_create_skips_confirmation(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    result = main.handle_application_decision(
        decision=make_create_decision(),
        event=make_event(
            event_type=EventType.APPLIED,
            event_date="2026-09-17",
        ),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
        auto_write=True,
    )

    assert result is True

    mocked_dependencies.confirmation.assert_not_called()
    mocked_dependencies.create_writer.assert_called_once()
    mocked_dependencies.update_writer.assert_not_called()

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []


@pytest.mark.parametrize(
    "action",
    [
        DecisionAction.REVIEW,
        DecisionAction.IGNORE,
    ],
)
def test_auto_write_never_writes_review_or_ignore(
    action,
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    decision = ApplicationDecision(
        action=action,
        company="Example Corp",
        role="Data Scientist",
        reason="no automatic write allowed",
    )

    result = main.handle_application_decision(
        decision=decision,
        event=make_event(),
        message=make_message(),
        spreadsheet_id=SPREADSHEET_ID,
        processed_store=processed_store,
        review_queue=mocked_dependencies.review_queue,
        auto_write=True,
    )

    assert result is False

    mocked_dependencies.confirmation.assert_not_called()
    mocked_dependencies.get_write_service.assert_not_called()
    mocked_dependencies.update_writer.assert_not_called()
    mocked_dependencies.create_writer.assert_not_called()

    assert processed_store.has_processed_message(
        MESSAGE_ID
    )

    if action == DecisionAction.REVIEW:
        assert len(
            mocked_dependencies.review_queue.items
        ) == 1

        item = mocked_dependencies.review_queue.items[0]

        assert item.gmail_message_id == MESSAGE_ID
        assert item.company == "Example Corp"
        assert item.role == "Data Scientist"
        assert (
            item.reason
            == "no automatic write allowed"
        )

    else:
        assert mocked_dependencies.review_queue.items == []


def test_auto_write_writer_failure_does_not_mark_processed(
    mocked_dependencies,
):
    processed_store = FakeProcessedMessageStore()

    mocked_dependencies.update_writer.side_effect = RuntimeError(
        "Sheets API failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Sheets API failed",
    ):
        main.handle_application_decision(
            decision=make_update_decision(),
            event=make_event(),
            message=make_message(),
            spreadsheet_id=SPREADSHEET_ID,
            processed_store=processed_store,
            review_queue=mocked_dependencies.review_queue,
            auto_write=True,
        )

    mocked_dependencies.confirmation.assert_not_called()
    mocked_dependencies.update_writer.assert_called_once()

    assert not processed_store.has_processed_message(
        MESSAGE_ID
    )

    assert mocked_dependencies.review_queue.items == []
