import os

from src.decision_engine import decide_application_event
from src.extraction import extract_application_event
from src.gmail_client import fetch_recent_messages
from src.sheets_client import get_sheets_service
from src.tracker_reader import read_tracker_applications
from src.processed_messages import (
    load_processed_message_ids,
    save_processed_message_ids,
)

GMAIL_QUERY = 'newer_than:7d'


def print_dry_run_decision(message: dict, event, decision) -> None:
    print()
    print("=" * 72)
    print(f"EMAIL: {message['subject']}")
    print(f"FROM: {message['sender']}")
    print(f"MESSAGE ID: {message['message_id']}")
    print("-" * 72)

    print(f"ACTION: {decision.action.value.upper()}")
    print(f"Company: {decision.company}")
    print(f"Role: {decision.role}")
    print(f"Event type: {event.event_type.value}")
    print(f"Confidence: {event.confidence:.2f}")
    print(f"Existing row: {decision.existing_row}")
    print(f"Current status: {decision.current_status}")
    print(f"Proposed status: {decision.proposed_status}")
    print(f"Reason: {decision.reason}")

    print("WRITE PERFORMED: NO")
    print("=" * 72)


def main() -> None:
    spreadsheet_id = os.environ["TRACKER_SPREADSHEET_ID"]

    # Read the tracker once at the start of the run.
    sheets_service = get_sheets_service()
    applications = read_tracker_applications(
        sheets_service,
        spreadsheet_id,
    )
    processed_message_ids = load_processed_message_ids()

    print(f"Loaded {len(applications)} tracker applications.")
    print(f"Loaded {len(processed_message_ids)} processed Gmail message IDs.")
    print("DRY RUN ONLY — no Sheet writes are enabled.")

    messages = fetch_recent_messages(
        max_results=25,
        query=GMAIL_QUERY,
    )

    print(f"Fetched {len(messages)} Gmail messages.")

    for message in messages:
        message_id = message["message_id"]

        if message_id in processed_message_ids:
            print(f"Skipping already processed message: {message['subject']}")
            continue

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
            print("ACTION: REVIEW")
            print(f"Reason: extraction failed: {exc}")
            print("WRITE PERFORMED: NO")
            print("=" * 72)

        # Intentionally NOT marked processed.
            continue

        decision = decide_application_event(
            event=event,
            applications=applications,
        )
    
        print_dry_run_decision(
            message=message,
            event=event,
            decision=decision,
        )   

        processed_message_ids.add(message_id)
        save_processed_message_ids(processed_message_ids)



if __name__ == "__main__":
    main()
