import pytest

from src.config import env_bool, require_env, validate_runtime_config


def test_env_bool_returns_true(monkeypatch):
    monkeypatch.setenv("TEST_BOOL", "true")

    assert env_bool("TEST_BOOL", default=False) is True


def test_env_bool_returns_false(monkeypatch):
    monkeypatch.setenv("TEST_BOOL", "false")

    assert env_bool("TEST_BOOL", default=True) is False


def test_env_bool_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("TEST_BOOL", "TRUE")

    assert env_bool("TEST_BOOL", default=False) is True


def test_env_bool_uses_default_when_missing(monkeypatch):
    monkeypatch.delenv("TEST_BOOL", raising=False)

    assert env_bool("TEST_BOOL", default=True) is True
    assert env_bool("TEST_BOOL", default=False) is False


def test_env_bool_treats_non_true_value_as_false(
    monkeypatch,
):
    monkeypatch.setenv(
        "TEST_BOOL",
        "yes",
    )

    assert env_bool(
        "TEST_BOOL",
        default=False,
    ) is False


def test_require_env_rejects_missing_value(monkeypatch):
    monkeypatch.delenv("REQUIRED_VALUE", raising=False)

    with pytest.raises(
        RuntimeError,
        match="Required environment variable is missing",
    ):
        require_env("REQUIRED_VALUE")


def test_validate_runtime_config_rejects_invalid_backend(
    monkeypatch,
):
    monkeypatch.setenv(
        "GOOGLE_CLOUD_PROJECT",
        "test-project",
    )
    monkeypatch.setenv(
        "TRACKER_SPREADSHEET_ID",
        "test-sheet",
    )
    monkeypatch.setenv(
        "PROCESSED_MESSAGE_BACKEND",
        "invalid",
    )

    with pytest.raises(
        RuntimeError,
        match="PROCESSED_MESSAGE_BACKEND",
    ):
        validate_runtime_config()


def test_validate_runtime_config_rejects_invalid_boolean(
    monkeypatch,
):
    monkeypatch.setenv(
        "GOOGLE_CLOUD_PROJECT",
        "test-project",
    )
    monkeypatch.setenv(
        "TRACKER_SPREADSHEET_ID",
        "test-sheet",
    )
    monkeypatch.setenv(
        "PROCESSED_MESSAGE_BACKEND",
        "firestore",
    )
    monkeypatch.setenv(
        "AUTO_WRITE",
        "definitely",
    )

    with pytest.raises(
        RuntimeError,
        match="AUTO_WRITE must be either 'true' or 'false'",
    ):
        validate_runtime_config()
