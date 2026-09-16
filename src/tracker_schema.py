from dataclasses import dataclass
from enum import Enum


TRACKER_SHEET_NAME = "Application Tracker"

HEADER_ROW = 1
INSTRUCTION_ROW = 2
FIRST_DATA_ROW = 3


class TrackerColumn(str, Enum):
    DATE = "Date"
    POSITION = "Position/Program"
    COMPANY = "Company/Organization"
    HIRING_MANAGER = "Hiring Manager"
    LINK = "Link"
    CONNECTIONS = "Connections"
    STATUS = "Status"
    DATE_UPDATED = "Date Updated"


class TrackerStatus(str, Enum):
    APPLIED = "Applied"
    PERFORMANCE_TASK = "Performance Task"
    PHONE_INTERVIEW = "Phone/Hirevue Interview"
    REJECTED_APPLICATION = "Rejected: App"


@dataclass(frozen=True)
class TrackerSchema:
    sheet_name: str = TRACKER_SHEET_NAME
    header_row: int = HEADER_ROW
    first_data_row: int = FIRST_DATA_ROW

    date_column: str = TrackerColumn.DATE.value
    position_column: str = TrackerColumn.POSITION.value
    company_column: str = TrackerColumn.COMPANY.value
    status_column: str = TrackerColumn.STATUS.value
    date_updated_column: str = TrackerColumn.DATE_UPDATED.value


TRACKER_SCHEMA = TrackerSchema()

# Existing application rows:
EXISTING_ROW_WRITABLE_COLUMNS = frozenset(
    {
        TrackerColumn.STATUS,
        TrackerColumn.DATE_UPDATED,
    }
)


NEW_ROW_WRITABLE_COLUMNS = frozenset(
    {
        TrackerColumn.DATE,
        TrackerColumn.POSITION,
        TrackerColumn.COMPANY,
        TrackerColumn.STATUS,
        TrackerColumn.DATE_UPDATED,
    }
)


# These fields are considered user-managed and should never be
# automatically overwritten by the agent.
USER_MANAGED_COLUMNS = frozenset(
    {
        TrackerColumn.HIRING_MANAGER,
        TrackerColumn.LINK,
        TrackerColumn.CONNECTIONS,
    }
)

# Schema validation

EXPECTED_HEADERS = [
    TrackerColumn.DATE.value,
    TrackerColumn.POSITION.value,
    TrackerColumn.COMPANY.value,
    TrackerColumn.HIRING_MANAGER.value,
    TrackerColumn.LINK.value,
    TrackerColumn.CONNECTIONS.value,
    TrackerColumn.STATUS.value,
    TrackerColumn.DATE_UPDATED.value,
]


def validate_tracker_headers(headers: list[str]) -> None:
    actual = [header.strip() for header in headers]

    if actual != EXPECTED_HEADERS:
        raise ValueError(
            "Application Tracker schema does not match expected columns.\n"
            f"Expected: {EXPECTED_HEADERS}\n"
            f"Actual:   {actual}"
        )
