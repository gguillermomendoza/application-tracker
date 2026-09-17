import os
from datetime import date

from src.decision_engine import (
    DecisionAction,
    decide_application_event,
)
from src.extraction import extract_application_event
from src.gmail_client import fetch_recent_messages
from src.processed_messages import (
    load_processed_message_ids,
    save_processed_message_ids,
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


GMAIL_QUERY = "newer_than:7d"


def handle_application_decision(
    *,
    decision,
    event,
    message,
    spreadsheet_id: str,
    processed_message_ids: set[str],
) -> bool:
    """
    Handle an ApplicationDecision after extraction and matching.

    Returns True only when a real Sheet write succeeds.

    REVIEW / IGNORE:
        No Sheet write occurs.
        The Gmail message is marked processed.

    CREATE / UPDATE:
        Build a validated write intent.
        Require explicit manual confirmation.
        Perform the constrained Sheet write.
        Mark the Gmail message processed only after the write succeeds.

    If a write is cancelled or fails, the Gmail message is NOT marked
    processed and can be retried later.
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

    if decision.action in {
        DecisionAction.IGNORE,
        DecisionAction.REVIEW,
    }:
        print("WRITE PERFORMED: NO")

        processed_message_ids.add(message_id)
        save_processed_message_ids(processed_message_ids)

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
                "CREATE event does not contain an explicit application date."
            )
            print("Treating as REVIEW.")
            print("WRITE PERFORMED: NO")

            processed_message_ids.add(message_id)
            save_processed_message_ids(processed_message_ids)

            print("MESSAGE MARKED PROCESSED")

            return False

        try:
            applied_date = date.fromisoformat(event.event_date)

        except ValueError:
            print()
            print("WRITE BLOCKED")
            print(
                f"Invalid application date from extraction: "
                f"{event.event_date!r}"
            )
            print("Treating as REVIEW.")
            print("WRITE PERFORMED: NO")

            processed_message_ids.add(message_id)
            save_processed_message_ids(processed_message_ids)

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
            f"{decision.action.value} unexpectedly produced no write intent"
        )

    # ------------------------------------------------------------
    # Manual confirmation gate
    # ------------------------------------------------------------

    print()
    print("REAL SHEET WRITE PROPOSED")

    if isinstance(intent, ExistingApplicationUpdate):
        print("Type: UPDATE")
        print(f"Row: {intent.row_number}")
        print(f"Status: {intent.status}")
        print(f"Date Updated: {intent.date_updated}")

    elif isinstance(intent, NewApplicationRow):
        print("Type: CREATE")
        print(f"Date: {intent.applied_date}")
        print(f"Position: {intent.role}")
        print(f"Company: {intent.company}")
        print(f"Status: {intent.status}")
        print(f"Date Updated: {intent.date_updated}")

    else:
        raise RuntimeError(
            f"Unsupported write intent type: {type(intent).__name__}"
        )

    print()

    confirmation = input("Type WRITE to execute: ").strip()

    if confirmation != "WRITE":
        print("WRITE CANCELLED")
        print("MESSAGE NOT MARKED PROCESSED")

        return False

    # ------------------------------------------------------------
    # Create writable Sheets client only after confirmation
    # ------------------------------------------------------------

    write_service = get_sheets_write_service()

    # ------------------------------------------------------------
    # Execute constrained write
    # ------------------------------------------------------------

    if isinstance(intent, ExistingApplicationUpdate):
        result = write_existing_application_update(
            service=write_service,
            spreadsheet_id=spreadsheet_id,
            intent=intent,
        )

    elif isinstance(intent, NewApplicationRow):
        result = write_new_application_row(
            service=write_service,
            spreadsheet_id=spreadsheet_id,
            intent=intent,
        )

    else:
        raise RuntimeError(
            f"Unsupported write intent type: {type(intent).__name__}"
        )

    # If the writer raises an exception, execution never reaches this
    # point, so the Gmail message remains unprocessed and can be retried.

    print()
    print("WRITE SUCCEEDED")
    print(f"Sheets response: {result}")

    processed_message_ids.add(message_id)
    save_processed_message_ids(processed_message_ids)

    print("MESSAGE MARKED PROCESSED")

    return True


def main() -> None:
    spreadsheet_id = os.environ["TRACKER_SPREADSHEET_ID"]

    # ------------------------------------------------------------
    # Load tracker and local processed-message checkpoint
    # ------------------------------------------------------------

    sheets_service = get_sheets_service()

    applications = read_tracker_applications(
        sheets_service,
        spreadsheet_id,
    )

    processed_message_ids = load_processed_message_ids()

    print(f"Loaded {len(applications)} tracker applications.")
    print(
        f"Loaded {len(processed_message_ids)} "
        "processed Gmail message IDs."
    )
    print(
        "MANUAL WRITE MODE — CREATE/UPDATE require "
        "explicit WRITE confirmation."
    )

    # ------------------------------------------------------------
    # Fetch Gmail messages
    # ------------------------------------------------------------

    messages = fetch_recent_messages(
        max_results=5,
        query=GMAIL_QUERY,
    )

    print(f"Fetched {len(messages)} Gmail messages.")

    # ------------------------------------------------------------
    # Process messages
    # ------------------------------------------------------------

    for message in messages:
        message_id = message["message_id"]

        if message_id in processed_message_ids:
            print(
                f"Skipping already processed message: "
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
            print(f"EMAIL: {message['subject']}")
            print(f"FROM: {message['sender']}")
            print(f"MESSAGE ID: {message_id}")
            print("ACTION: REVIEW")
            print(f"Reason: extraction failed: {exc}")
            print("WRITE PERFORMED: NO")
            print("MESSAGE NOT MARKED PROCESSED")
            print("=" * 72)

            # Extraction/API failures remain unprocessed so they
            # can be retried on a future run.
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
        print(f"EMAIL: {message['subject']}")
        print(f"FROM: {message['sender']}")
        print(f"MESSAGE ID: {message_id}")
        print(f"EVENT TYPE: {event.event_type.value}")
        print(f"EVENT DATE: {event.event_date}")
        print(f"CONFIDENCE: {event.confidence:.2f}")
        print("=" * 72)

        # --------------------------------------------------------
        # Handle decision and optional real write
        # --------------------------------------------------------

        try:
            write_performed = handle_application_decision(
                decision=decision,
                event=event,
                message=message,
                spreadsheet_id=spreadsheet_id,
                processed_message_ids=processed_message_ids,
            )

        except Exception as exc:
            print()
            print("=" * 72)
            print("DECISION HANDLING FAILED")
            print(f"EMAIL: {message['subject']}")
            print(f"Reason: {exc}")
            print("MESSAGE NOT MARKED PROCESSED")
            print("=" * 72)

            # Most importantly, do not add the Gmail message ID here.
            # Failed writes therefore remain eligible for retry.
            continue

        # --------------------------------------------------------
        # Refresh tracker after a successful write
        #
        # This prevents later Gmail messages in the same run from
        # making decisions against stale tracker state.
        # --------------------------------------------------------

        if write_performed:
            applications = read_tracker_applications(
                sheets_service,
                spreadsheet_id,
            )

            print(
                f"Tracker refreshed: "
                f"{len(applications)} applications loaded."
            )


if __name__ == "__main__":
    main()
