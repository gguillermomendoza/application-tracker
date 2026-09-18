from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

from google.cloud import firestore


class ProcessedMessageStore(Protocol):
    def has_processed_message(
        self,
        message_id: str,
    ) -> bool:
        ...

    def mark_message_processed(
        self,
        message_id: str,
    ) -> None:
        ...


def _validate_message_id(
    message_id: str,
) -> None:
    if not isinstance(message_id, str) or not message_id.strip():
        raise ValueError(
            "message_id must be a non-empty string"
        )


class JsonProcessedMessageStore:
    def __init__(
        self,
        path: str | os.PathLike[str] = "processed_messages.json",
    ) -> None:
        self.path = Path(path)
        self._processed_message_ids = self._load()

    def has_processed_message(
        self,
        message_id: str,
    ) -> bool:
        _validate_message_id(message_id)

        return message_id in self._processed_message_ids

    def mark_message_processed(
        self,
        message_id: str,
    ) -> None:
        _validate_message_id(message_id)

        if message_id in self._processed_message_ids:
            return

        updated_ids = (
            self._processed_message_ids
            | {message_id}
        )

        self._persist(updated_ids)

        # Only mutate in-memory state after persistence succeeds.
        self._processed_message_ids = updated_ids

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()

        contents = self.path.read_text(
            encoding="utf-8"
        ).strip()

        if not contents:
            return set()

        try:
            data = json.loads(contents)

        except json.JSONDecodeError as exc:
            raise ValueError(
                "Processed-message store is not valid JSON: "
                f"{self.path}"
            ) from exc

        if not isinstance(data, list):
            raise ValueError(
                "Processed-message JSON must contain "
                "a list of message IDs"
            )

        if not all(
            isinstance(message_id, str)
            and message_id.strip()
            for message_id in data
        ):
            raise ValueError(
                "Processed-message JSON contains "
                "an invalid message ID"
            )

        return set(data)

    def _persist(
        self,
        message_ids: set[str],
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fd, temp_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    sorted(message_ids),
                    file,
                    indent=2,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(
                temp_path,
                self.path,
            )

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class FirestoreProcessedMessageStore:
    def __init__(
        self,
        *,
        client=None,
        collection_name: str = "processed_messages",
    ) -> None:
        if not collection_name.strip():
            raise ValueError(
                "collection_name must be non-empty"
            )

        self.client = client or firestore.Client()
        self.collection_name = collection_name

    def has_processed_message(
        self,
        message_id: str,
    ) -> bool:
        _validate_message_id(message_id)

        snapshot = (
            self.client
            .collection(self.collection_name)
            .document(message_id)
            .get()
        )

        return snapshot.exists

    def mark_message_processed(
        self,
        message_id: str,
    ) -> None:
        _validate_message_id(message_id)

        document = (
            self.client
            .collection(self.collection_name)
            .document(message_id)
        )

        document.set(
            {
                "gmail_message_id": message_id,
                "processed_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

def build_processed_message_store() -> ProcessedMessageStore:
    backend = os.getenv(
        "PROCESSED_MESSAGE_BACKEND",
        "json",
    ).strip().lower()

    if backend == "json":
        path = os.getenv(
            "PROCESSED_MESSAGE_JSON_PATH",
            "processed_messages.json",
        )

        return JsonProcessedMessageStore(
            path=path,
        )

    if backend == "firestore":
        collection_name = os.getenv(
            "PROCESSED_MESSAGE_FIRESTORE_COLLECTION",
            "processed_messages",
        )

        return FirestoreProcessedMessageStore(
            collection_name=collection_name,
        )

    raise ValueError(
        "Unsupported processed-message backend: "
        f"{backend!r}. Expected 'json' or 'firestore'."
    )        
