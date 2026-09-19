import os

def env_bool(
    name: str,
    *,
    default: bool,
) -> bool:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    return raw_value.strip().lower() == "true"

def validate_bool_env(name: str) -> None:
    raw_value = os.getenv(name)

    if raw_value is None:
        return

    value = raw_value.strip().lower()

    if value not in {"true", "false"}:
        raise RuntimeError(
            f"{name} must be either 'true' or 'false'."
        )



def require_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable is missing: {name}"
        )

    return value.strip()


def validate_runtime_config() -> None:
    require_env("GOOGLE_CLOUD_PROJECT")
    require_env("TRACKER_SPREADSHEET_ID")

    backend = os.getenv(
        "PROCESSED_MESSAGE_BACKEND",
        "json",
    ).strip().lower()
    for name in (
        "AUTO_WRITE",
        "ALLOW_INTERACTIVE_WRITES",
        "ALLOW_INTERACTIVE_OAUTH",
        "PERSIST_OAUTH_TOKENS",
    ):
        validate_bool_env(name)
    if backend not in {
        "json",
        "firestore",
    }:
        raise RuntimeError(
            "PROCESSED_MESSAGE_BACKEND must be "
            "'json' or 'firestore'."
        )

    auto_write = env_bool(
        "AUTO_WRITE",
        default=False,
    )

    allow_interactive_writes = env_bool(
        "ALLOW_INTERACTIVE_WRITES",
        default=False,
    )

    if (
        not auto_write
        and not allow_interactive_writes
    ):
        print(
            "WARNING: automatic writes are disabled and "
            "interactive writes are disabled. "
            "CREATE/UPDATE decisions will not execute."
        )
