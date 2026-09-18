from unittest.mock import MagicMock

import pytest
from google.cloud import firestore

from src.review_queue import (
    FirestoreReviewQueueStore,
    ReviewItem,
)


def make_review_item() -> ReviewItem:
    return ReviewItem(
        gmail_message_id="gmail-123",
        subject="Update on your application",
        sender="recruiting@example.com",
        company="Example Corp",
        role="Data Scientist",
        event_type="offer",
        confidence=0.94,
        reason="event type has no approved tracker status",
    )


def test_firestore_review_queue_writes_expected_document():
    client = MagicMock()

    collection = client.collection.return_value
    document = collection.document.return_value

    store = FirestoreReviewQueueStore(
        client=client,
    )

    item = make_review_item()

    store.add_review_item(item)

    client.collection.assert_called_once_with(
        "review_queue"
    )

    collection.document.assert_called_once_with(
        "gmail-123"
    )

    document.set.assert_called_once()

    payload = document.set.call_args.args[0]

    assert payload["gmail_message_id"] == "gmail-123"
    assert payload["subject"] == "Update on your application"
    assert payload["sender"] == "recruiting@example.com"
    assert payload["company"] == "Example Corp"
    assert payload["role"] == "Data Scientist"
    assert payload["event_type"] == "offer"
    assert payload["confidence"] == 0.94
    assert (
        payload["reason"]
        == "event type has no approved tracker status"
    )
    assert payload["review_status"] == "pending"

    assert (
        payload["created_at"]
        is firestore.SERVER_TIMESTAMP
    )

    assert document.set.call_args.kwargs == {
        "merge": True,
    }


def test_firestore_review_queue_uses_custom_collection():
    client = MagicMock()

    store = FirestoreReviewQueueStore(
        client=client,
        collection_name="test_review_queue",
    )

    store.add_review_item(
        make_review_item()
    )

    client.collection.assert_called_once_with(
        "test_review_queue"
    )


def test_firestore_review_queue_rejects_blank_message_id():
    client = MagicMock()

    store = FirestoreReviewQueueStore(
        client=client,
    )

    item = ReviewItem(
        gmail_message_id="",
        subject="Application update",
        sender="recruiting@example.com",
        company=None,
        role=None,
        event_type="other",
        confidence=0.5,
        reason="ambiguous",
    )

    with pytest.raises(
        ValueError,
        match="gmail_message_id",
    ):
        store.add_review_item(item)

    client.collection.assert_not_called()


def test_firestore_review_queue_rejects_blank_collection_name():
    client = MagicMock()

    with pytest.raises(
        ValueError,
        match="collection_name",
    ):
        FirestoreReviewQueueStore(
            client=client,
            collection_name="",
        )
