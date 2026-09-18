import os
from datetime import date
from src.config import (
    env_bool,
    require_env,
    validate_runtime_config,
)

from src.decision_engine import (
    DecisionAction,
    decide_application_event,
)
from src.extraction import extract_application_event
from src.gmail_client import fetch_recent_messages
from src.processed_messages import (
    ProcessedMessageStore,
    build_processed_message_store,
)
from src.review_queue import (
    ReviewItem,
    ReviewQueueStore,
    build_review_queue_store,
)
from src.sheet_writer import (
    write_existing_application_update,
    write_new_application_row,
)
from src.sheets_client import (
    get_sheets_service,
    get_sheets_write_service,
)
from src.tracker_reader import read_tracker_applications
from src.write_models import (
    ExistingApplicationUpdate,
    NewApplicationRow,
    decision_to_write_intent,
)


GMAIL_QUERY = "newer_than:2d"


def auto_write_enabled() -> bool:
    return env_bool(
        "AUTO_WRITE",
        default=False,
    )


def interactive_writes_enabled() -> bool:
    return env_bool(
        "ALLOW_INTERACTIVE_WRITES",
        default=True,
    )


def interactive_writes_enabled() -> bool:
    return (
        os.getenv(
            "ALLOW_INTERACTIVE_WRITES",
            "true",
        )
        .strip()
        .lower()
        == "true"
    )


def handle_application_decision(
    *,
    decision,
    event,
    message,
    spreadsheet_id: str,
    processed_store: ProcessedMessageStore,
    review_queue: ReviewQueueStore,
    auto_write: bool = False,
    allow_interactive_writes: bool = True,
) -> bool:
    """
    Handle an ApplicationDecision after extraction and matching.

    Returns True only when a real Sheet write succeeds.

    IGNORE:
        No Sheet write occurs.
        The Gmail message is marked processed.

    REVIEW:
        No Sheet write occurs.
        A durable review item is persisted.
        The Gmail message is marked processed only after review
        persistence succeeds.

    CREATE / UPDATE:
        Build a validated write intent.
        Require explicit manual confirmation unless AUTO_WRITE is enabled.
        Perform the constrained Sheet write.
        Mark the Gmail message processed only after the write succeeds.

    If a Sheet write, review persistence operation, or manual approval
    fails, the Gmail message is NOT marked processed and can be retried.
    """

    message_id = message["message_id"]

    print()
    print("=" * 72)
    print(f"ACTION: {decision.action.value.upper()}")
    print(f"Company: {decision.company}")
    print(f"Role: {decision.role}")
    print(f"Existing row: {decision.existing_row}")
    print(f"Current status: {decision.current_status}")
    print(f"Proposed status: {decision.proposed_status}")
    print(f"Reason: {decision.reason}")
    print("=" * 72)

    # ------------------------------------------------------------
    # No-write decisions
    # ------------------------------------------------------------

    if decision.action == DecisionAction.IGNORE:
        print("WRITE PERFORMED: NO")

        processed_store.mark_message_processed(
            message_id
        )

        print("MESSAGE MARKED PROCESSED")

        return False

    if decision.action == DecisionAction.REVIEW:
        print("WRITE PERFORMED: NO")

        review_item = ReviewItem(
            gmail_message_id=message_id,
            subject=message["subject"],
            sender=message["sender"],
            company=event.company,
            role=event.role,
            event_type=event.event_type.value,
            confidence=event.confidence,
            reason=decision.reason,
        )

        # Persist review item first.
        # If this raises, execution stops and the message remains
        # unprocessed so it can be retried later.
        review_queue.add_review_item(
            review_item
        )

        # Only mark processed AFTER durable review persistence succeeds.
        processed_store.mark_message_processed(
            message_id
        )

        print("REVIEW ITEM PERSISTED")
        print("MESSAGE MARKED PROCESSED")

        return False

    # ------------------------------------------------------------
    # Determine dates for validated write intent
    # ------------------------------------------------------------

    date_updated = date.today()
    applied_date = None

    if decision.action == DecisionAction.CREATE:
        if not event.event_date:
            print()
            print("WRITE BLOCKED")
            print(
                "CREATE event does not contain an explicit "
                "application date."
            )
            print("Treating as REVIEW.")
            print("WRITE PERFORMED: NO")

            review_queue.add_review_item(
                ReviewItem(
                    gmail_message_id=message_id,
                    subject=message["subject"],
                    sender=message["sender"],
                    company=event.company,
                    role=event.role,
                    event_type=event.event_type.value,
                    confidence=event.confidence,
                    reason=(
                        "CREATE event does not contain "
                        "an explicit application date."
                    ),
                )
            )

            # Only mark processed after review persistence succeeds.
            processed_store.mark_message_processed(
                message_id
            )

            print("REVIEW ITEM PERSISTED")
            print("MESSAGE MARKED PROCESSED")

            return False

        try:
            applied_date = date.fromisoformat(
                event.event_date
            )

        except ValueError:
            print()
            print("WRITE BLOCKED")
            print(
                "Invalid application date from extraction: "
                f"{event.event_date!r}"
            )
            print("Treating as REVIEW.")
            print("WRITE PERFORMED: NO")

            review_queue.add_review_item(
                ReviewItem(
                    gmail_message_id=message_id,
                    subject=message["subject"],
                    sender=message["sender"],
                    company=event.company,
                    role=event.role,
                    event_type=event.event_type.value,
                    confidence=event.confidence,
                    reason=(
                        "CREATE event contains invalid "
                        f"application date: {event.event_date!r}"
                    ),
                )
            )

            # Only mark processed after review persistence succeeds.
            processed_store.mark_message_processed(
                message_id
            )

            print("REVIEW ITEM PERSISTED")
            print("MESSAGE MARKED PROCESSED")

            return False

    # ------------------------------------------------------------
    # Decision -> validated write intent
    # ------------------------------------------------------------

    intent = decision_to_write_intent(
        decision,
        date_updated=date_updated,
        applied_date=applied_date,
    )

    if intent is None:
        raise RuntimeError(
            f"{decision.action.value} unexpectedly "
            "produced no write intent"
        )

    # ------------------------------------------------------------
    # Display proposed write
    # ------------------------------------------------------------

    print()
    print("REAL SHEET WRITE PROPOSED")

    if isinstance(
        intent,
        ExistingApplicationUpdate,
    ):
        print("Type: UPDATE")
        print(f"Row: {intent.row_number}")
        print(f"Status: {intent.status}")
        print(
            f"Date Updated: {intent.date_updated}"
        )

    elif isinstance(
        intent,
        NewApplicationRow,
    ):
        print("Type: CREATE")
        print(f"Date: {intent.applied_date}")
        print(f"Position: {intent.role}")
        print(f"Company: {intent.company}")
        print(f"Status: {intent.status}")
        print(
            f"Date Updated: {intent.date_updated}"
        )

    else:
        raise RuntimeError(
            "Unsupported write intent type: "
            f"{type(intent).__name__}"
        )

    # ------------------------------------------------------------
    # Manual confirmation gate / automatic-write mode
    # ------------------------------------------------------------

    print()

    if auto_write:
        print(
            "AUTO_WRITE enabled - executing approved "
            "write automatically."
        )

    elif not allow_interactive_writes:
        print(
            "INTERACTIVE WRITES DISABLED - "
            "write not executed."
        )
        print("MESSAGE NOT MARKED PROCESSED")

        return False

    else:
        confirmation = input(
            "Type WRITE to execute: "
        ).strip()

        if confirmation != "WRITE":
            print("WRITE CANCELLED")
            print(
                "MESSAGE NOT MARKED PROCESSED"
            )

            return False

    # ------------------------------------------------------------
    # Create writable Sheets client only after approval
    # ------------------------------------------------------------

    write_service = get_sheets_write_service()

    # ------------------------------------------------------------
    # Execute constrained write
    # ------------------------------------------------------------

    if isinstance(
        intent,
        ExistingApplicationUpdate,
    ):
        result = write_existing_application_update(
            service=write_service,
            spreadsheet_id=spreadsheet_id,
            intent=intent,
        )

    elif isinstance(
        intent,
        NewApplicationRow,
    ):
        result = write_new_application_row(
            service=write_service,
            spreadsheet_id=spreadsheet_id,
            intent=intent,
        )

    else:
        raise RuntimeError(
            "Unsupported write intent type: "
            f"{type(intent).__name__}"
        )

    # If the writer raises an exception, execution never reaches
    # this point. The Gmail message therefore remains unprocessed
    # and can be retried.

    print()
    print("WRITE SUCCEEDED")
    print(f"Sheets response: {result}")

    processed_store.mark_message_processed(
        message_id
    )

    print("MESSAGE MARKED PROCESSED")

    return True

def main() -> None:
    validate_runtime_config()

    spreadsheet_id = require_env(
        "TRACKER_SPREADSHEET_ID"
    )

    auto_write = auto_write_enabled()

    allow_interactive_writes = (
        interactive_writes_enabled()
    )

    # ------------------------------------------------------------
    # Load tracker and persistence stores
    # ------------------------------------------------------------

    sheets_service = get_sheets_service()

    applications = read_tracker_applications(
        sheets_service,
        spreadsheet_id,
    )

    processed_store = (
        build_processed_message_store()
    )

    review_queue = build_review_queue_store()

    print(
        f"Loaded {len(applications)} "
        "tracker applications."
    )
    print(
        "Processed-message store initialized."
    )
    print(
        "Review queue store initialized."
    )

    if auto_write:
        print(
            "AUTO WRITE MODE - approved CREATE/UPDATE "
            "decisions will execute automatically."
        )

    elif allow_interactive_writes:
        print(
            "MANUAL WRITE MODE - CREATE/UPDATE "
            "require explicit WRITE confirmation."
        )

    else:
        print(
            "NON-INTERACTIVE WRITE MODE - "
            "CREATE/UPDATE will not execute "
            "without AUTO_WRITE."
        )

    # ------------------------------------------------------------
    # Fetch Gmail messages
    # ------------------------------------------------------------

    messages = fetch_recent_messages(
        max_results=5,
        query=GMAIL_QUERY,
    )

    print(
        f"Fetched {len(messages)} Gmail messages."
    )

    # ------------------------------------------------------------
    # Process messages
    # ------------------------------------------------------------

    for message in messages:
        message_id = message["message_id"]

        if processed_store.has_processed_message(
            message_id
        ):
            print(
                "Skipping already processed message: "
                f"{message['subject']}"
            )
            continue

        # --------------------------------------------------------
        # Gemini extraction
        # --------------------------------------------------------

        try:
            event = extract_application_event(
                subject=message["subject"],
                sender=message["sender"],
                received_at=message["received_at"],
                body=message["body"],
            )

        except Exception as exc:
            print()
            print("=" * 72)
            print(
                f"EMAIL: {message['subject']}"
            )
            print(
                f"FROM: {message['sender']}"
            )
            print(
                f"MESSAGE ID: {message_id}"
            )
            print("ACTION: EXTRACTION_FAILED")
            print(
                f"Reason: extraction failed: {exc}"
            )
            print("WRITE PERFORMED: NO")
            print(
                "MESSAGE NOT MARKED PROCESSED"
            )
            print("=" * 72)

            # Extraction/API failures remain unprocessed so
            # they can be retried on a future run.
            continue

        # --------------------------------------------------------
        # Deterministic decision engine
        # --------------------------------------------------------

        decision = decide_application_event(
            event=event,
            applications=applications,
        )

        # --------------------------------------------------------
        # Print source email / extraction information
        # --------------------------------------------------------

        print()
        print("=" * 72)
        print(
            f"EMAIL: {message['subject']}"
        )
        print(
            f"FROM: {message['sender']}"
        )
        print(
            f"MESSAGE ID: {message_id}"
        )
        print(
            f"EVENT TYPE: "
            f"{event.event_type.value}"
        )
        print(
            f"EVENT DATE: {event.event_date}"
        )
        print(
            f"CONFIDENCE: "
            f"{event.confidence:.2f}"
        )
        print("=" * 72)

        # --------------------------------------------------------
        # Handle decision and optional real write
        # --------------------------------------------------------

        try:
            write_performed = (
                handle_application_decision(
                    decision=decision,
                    event=event,
                    message=message,
                    spreadsheet_id=spreadsheet_id,
                    processed_store=processed_store,
                    review_queue=review_queue,
                    auto_write=auto_write,
                    allow_interactive_writes=(
                        allow_interactive_writes
                    ),
                )
            )

        except Exception as exc:
            print()
            print("=" * 72)
            print(
                "DECISION HANDLING FAILED"
            )
            print(
                f"EMAIL: {message['subject']}"
            )
            print(
                f"Reason: {exc}"
            )
            print(
                "MESSAGE NOT MARKED PROCESSED"
            )
            print("=" * 72)

            # Most importantly, do not mark the Gmail
            # message processed here. Failed Sheet writes
            # and failed review persistence remain eligible
            # for retry.
            continue

        # --------------------------------------------------------
        # Refresh tracker after a successful write
        #
        # This prevents later Gmail messages in the same run
        # from making decisions against stale tracker state.
        # --------------------------------------------------------

        if write_performed:
            applications = (
                read_tracker_applications(
                    sheets_service,
                    spreadsheet_id,
                )
            )

            print(
                "Tracker refreshed: "
                f"{len(applications)} "
                "applications loaded."
            )


if __name__ == "__main__":
    main()
