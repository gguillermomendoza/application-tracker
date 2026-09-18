import json

import pytest

from src.processed_messages import (
    FirestoreProcessedMessageStore,
    JsonProcessedMessageStore,
    build_processed_message_store,
    )

from unittest.mock import MagicMock

from google.cloud import firestore

from src.processed_messages import (
    FirestoreProcessedMessageStore,
)
def test_missing_file_starts_empty(tmp_path):
    path = tmp_path / "processed_messages.json"

    store = JsonProcessedMessageStore(path)

    assert store.has_processed_message("abc123") is False


def test_empty_file_starts_empty(tmp_path):
    path = tmp_path / "processed_messages.json"
    path.write_text("", encoding="utf-8")

    store = JsonProcessedMessageStore(path)

    assert store.has_processed_message("abc123") is False


def test_existing_message_is_loaded(tmp_path):
    path = tmp_path / "processed_messages.json"
    path.write_text(
        json.dumps(["abc123"]),
        encoding="utf-8",
    )

    store = JsonProcessedMessageStore(path)

    assert store.has_processed_message("abc123") is True
    assert store.has_processed_message("other") is False


def test_mark_message_processed_persists(tmp_path):
    path = tmp_path / "processed_messages.json"

    store = JsonProcessedMessageStore(path)
    store.mark_message_processed("abc123")

    reloaded_store = JsonProcessedMessageStore(path)

    assert reloaded_store.has_processed_message("abc123") is True


def test_mark_message_processed_is_idempotent(tmp_path):
    path = tmp_path / "processed_messages.json"

    store = JsonProcessedMessageStore(path)

    store.mark_message_processed("abc123")
    store.mark_message_processed("abc123")

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert data == ["abc123"]


def test_blank_message_id_is_rejected(tmp_path):
    path = tmp_path / "processed_messages.json"
    store = JsonProcessedMessageStore(path)

    with pytest.raises(ValueError):
        store.mark_message_processed("")


def test_malformed_json_fails_closed(tmp_path):
    path = tmp_path / "processed_messages.json"
    path.write_text(
        "{ definitely-not-json",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        JsonProcessedMessageStore(path)
def test_firestore_store_reports_existing_message():
    client = MagicMock()
    collection = client.collection.return_value
    document = collection.document.return_value

    snapshot = MagicMock()
    snapshot.exists = True

    document.get.return_value = snapshot

    store = FirestoreProcessedMessageStore(
        client=client,
    )

    result = store.has_processed_message(
        "gmail-123"
    )

    assert result is True

    client.collection.assert_called_once_with(
        "processed_messages"
    )
    collection.document.assert_called_once_with(
        "gmail-123"
    )
    document.get.assert_called_once_with()


def test_firestore_store_reports_missing_message():
    client = MagicMock()
    document = (
        client
        .collection.return_value
        .document.return_value
    )

    snapshot = MagicMock()
    snapshot.exists = False

    document.get.return_value = snapshot

    store = FirestoreProcessedMessageStore(
        client=client,
    )

    assert (
        store.has_processed_message(
            "gmail-123"
        )
        is False
    )


def test_firestore_store_marks_message_processed():
    client = MagicMock()
    collection = client.collection.return_value
    document = collection.document.return_value

    store = FirestoreProcessedMessageStore(
        client=client,
    )

    store.mark_message_processed(
        "gmail-123"
    )

    client.collection.assert_called_once_with(
        "processed_messages"
    )
    collection.document.assert_called_once_with(
        "gmail-123"
    )

    document.set.assert_called_once()

    payload = document.set.call_args.args[0]

    assert payload["gmail_message_id"] == "gmail-123"
    assert (
        payload["processed_at"]
        is firestore.SERVER_TIMESTAMP
    )

    assert document.set.call_args.kwargs == {
        "merge": True,
    }


def test_firestore_store_rejects_blank_message_id():
    client = MagicMock()

    store = FirestoreProcessedMessageStore(
        client=client,
    )

    with pytest.raises(ValueError):
        store.mark_message_processed("")


def test_firestore_store_rejects_blank_collection_name():
    client = MagicMock()

    with pytest.raises(ValueError):
        FirestoreProcessedMessageStore(
            client=client,
            collection_name="",
        )

def test_store_factory_defaults_to_json(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "processed.json"

    monkeypatch.delenv(
        "PROCESSED_MESSAGE_BACKEND",
        raising=False,
    )
    monkeypatch.setenv(
        "PROCESSED_MESSAGE_JSON_PATH",
        str(path),
    )

    store = build_processed_message_store()

    assert isinstance(
        store,
        JsonProcessedMessageStore,
    )
    assert store.path == path


def test_store_factory_uses_explicit_json_backend(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "processed.json"

    monkeypatch.setenv(
        "PROCESSED_MESSAGE_BACKEND",
        "json",
    )
    monkeypatch.setenv(
        "PROCESSED_MESSAGE_JSON_PATH",
        str(path),
    )

    store = build_processed_message_store()

    assert isinstance(
        store,
        JsonProcessedMessageStore,
    )


def test_store_factory_builds_firestore_backend(
    monkeypatch,
):
    fake_store = MagicMock()

    firestore_store_class = MagicMock(
        return_value=fake_store,
    )

    monkeypatch.setenv(
        "PROCESSED_MESSAGE_BACKEND",
        "firestore",
    )
    monkeypatch.setenv(
        "PROCESSED_MESSAGE_FIRESTORE_COLLECTION",
        "test_processed_messages",
    )

    monkeypatch.setattr(
        "src.processed_messages.FirestoreProcessedMessageStore",
        firestore_store_class,
    )

    result = build_processed_message_store()

    assert result is fake_store

    firestore_store_class.assert_called_once_with(
        collection_name="test_processed_messages",
    )


def test_store_factory_rejects_unknown_backend(
    monkeypatch,
):
    monkeypatch.setenv(
        "PROCESSED_MESSAGE_BACKEND",
        "banana",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported processed-message backend",
    ):
        build_processed_message_store()
