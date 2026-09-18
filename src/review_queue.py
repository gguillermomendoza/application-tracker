from __future__ import annotations
import os

from dataclasses import dataclass
from typing import Protocol

from google.cloud import firestore


@dataclass(frozen=True)
class ReviewItem:
    gmail_message_id: str
    subject: str
    sender: str
    company: str | None
    role: str | None
    event_type: str
    confidence: float
    reason: str


class ReviewQueueStore(Protocol):
    def add_review_item(
        self,
        item: ReviewItem,
    ) -> None:
        ...


class FirestoreReviewQueueStore:
    def __init__(
        self,
        *,
        client=None,
        collection_name: str = "review_queue",
    ) -> None:
        if not collection_name.strip():
            raise ValueError(
                "collection_name must be non-empty"
            )

        self.client = client or firestore.Client()
        self.collection_name = collection_name

    def add_review_item(
        self,
        item: ReviewItem,
    ) -> None:
        if not item.gmail_message_id.strip():
            raise ValueError(
                "gmail_message_id must be non-empty"
            )

        document = (
            self.client
            .collection(self.collection_name)
            .document(item.gmail_message_id)
        )

        document.set(
            {
                "gmail_message_id": item.gmail_message_id,
                "subject": item.subject,
                "sender": item.sender,
                "company": item.company,
                "role": item.role,
                "event_type": item.event_type,
                "confidence": item.confidence,
                "reason": item.reason,
                "created_at": firestore.SERVER_TIMESTAMP,
                "review_status": "pending",
            },
            merge=True,
        )



def build_review_queue_store() -> ReviewQueueStore:
    collection_name = os.getenv(
        "REVIEW_QUEUE_FIRESTORE_COLLECTION",
        "review_queue",
    )

    return FirestoreReviewQueueStore(
        collection_name=collection_name,
    )
