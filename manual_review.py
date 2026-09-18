# manual_review_queue_test.py

from src.review_queue import (
    FirestoreReviewQueueStore,
    ReviewItem,
)


MESSAGE_ID = "manual-review-queue-test"


def main() -> None:
    store = FirestoreReviewQueueStore()

    item = ReviewItem(
        gmail_message_id=MESSAGE_ID,
        subject="Manual review queue test",
        sender="test@example.com",
        company="Example Corp",
        role="Data Scientist",
        event_type="offer",
        confidence=0.91,
        reason="manual persistence validation",
    )

    store.add_review_item(item)

    print("Review item persisted successfully.")
    print(f"Document ID: {MESSAGE_ID}")


if __name__ == "__main__":
    main()
