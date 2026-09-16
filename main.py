from src.extraction import extract_application_event
from src.gmail_client import fetch_recent_messages


def main():
    messages = fetch_recent_messages(
        max_results=5,
        query='newer_than:90d "thank you for applying"',
    )

    print(f"Found {len(messages)} Gmail messages.\n")

    for message in messages:
        print("=" * 70)
        print(f"Message ID: {message['message_id']}")
        print(f"From:       {message['sender']}")
        print(f"Subject:    {message['subject']}")
        print(f"Date:       {message['received_at']}")
        print()

        try:
            event = extract_application_event(
                subject=message["subject"],
                sender=message["sender"],
                received_at=message["received_at"],
                body=message["body"],
            )

            print(event.model_dump_json(indent=2))

        except Exception as exc:
            print(
                f"Extraction failed: "
                f"{type(exc).__name__}: {exc}"
            )

        print()


if __name__ == "__main__":
    main()
