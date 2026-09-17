import json
from pathlib import Path


DEFAULT_PATH = Path("processed_messages.json")


def load_processed_message_ids(
    path: Path = DEFAULT_PATH,
) -> set[str]:
    if not path.exists():
        return set()

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("processed message store must contain a JSON list")

    return set(data)


def save_processed_message_ids(
    message_ids: set[str],
    path: Path = DEFAULT_PATH,
) -> None:
    temp_path = path.with_suffix(".tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(
            sorted(message_ids),
            file,
            indent=2,
        )

    temp_path.replace(path)
