import os


def env_bool(
    name: str,
    *,
    default: bool,
) -> bool:
    value = os.getenv(
        name,
        "true" if default else "false",
    )

    return value.strip().lower() == "true"


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
        default=True,
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
