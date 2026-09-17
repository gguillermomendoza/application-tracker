from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from src.decision_engine import (
    ApplicationDecision,
    DecisionAction,
    TRACKER_STATUS_BY_EVENT,
)
from src.tracker_schema import FIRST_DATA_ROW


APPROVED_TRACKER_STATUSES = frozenset(TRACKER_STATUS_BY_EVENT.values())


class WriteIntentError(ValueError):
    """Raised when a decision cannot safely become a Sheet write intent."""


class ExistingApplicationUpdate(BaseModel):
    """
    The only fields an automated update is allowed to modify
    for an existing tracker row.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    row_number: int
    status: str
    date_updated: date

    @field_validator("row_number")
    @classmethod
    def validate_row_number(cls, value: int) -> int:
        if value < FIRST_DATA_ROW:
            raise ValueError(
                f"row_number must be >= {FIRST_DATA_ROW}"
            )
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.strip()

        if value not in APPROVED_TRACKER_STATUSES:
            raise ValueError(
                f"status is not an approved tracker status: {value!r}"
            )

        return value


class NewApplicationRow(BaseModel):
    """
    The only fields automation is allowed to populate
    when creating a new application row.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    applied_date: date
    role: str
    company: str
    status: Literal["Applied"]
    date_updated: date

    @field_validator("role", "company")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be blank")

        return value


WriteIntent = ExistingApplicationUpdate | NewApplicationRow


def decision_to_write_intent(
    decision: ApplicationDecision,
    *,
    date_updated: date,
    applied_date: date | None = None,
) -> WriteIntent | None:
    """
    Convert a validated ApplicationDecision into a narrowly scoped
    Sheet write intent.

    REVIEW and IGNORE intentionally produce no write intent.

    This function performs no external writes.
    """

    if decision.action in {
        DecisionAction.REVIEW,
        DecisionAction.IGNORE,
    }:
        return None

    if decision.action == DecisionAction.UPDATE:
        if decision.existing_row is None:
            raise WriteIntentError(
                "UPDATE decision is missing existing_row"
            )

        if decision.proposed_status is None:
            raise WriteIntentError(
                "UPDATE decision is missing proposed_status"
            )

        if decision.current_status == decision.proposed_status:
            raise WriteIntentError(
                "UPDATE decision does not change the tracker status"
            )

        return ExistingApplicationUpdate(
            row_number=decision.existing_row,
            status=decision.proposed_status,
            date_updated=date_updated,
        )

    if decision.action == DecisionAction.CREATE:
        if decision.existing_row is not None:
            raise WriteIntentError(
                "CREATE decision unexpectedly references an existing row"
            )

        if decision.company is None or not decision.company.strip():
            raise WriteIntentError(
                "CREATE decision is missing company"
            )

        if decision.role is None or not decision.role.strip():
            raise WriteIntentError(
                "CREATE decision is missing role"
            )

        if decision.proposed_status != "Applied":
            raise WriteIntentError(
                "CREATE decisions may only create rows with status 'Applied'"
            )

        if applied_date is None:
            raise WriteIntentError(
                "CREATE decision requires an explicit applied_date"
            )

        return NewApplicationRow(
            applied_date=applied_date,
            role=decision.role,
            company=decision.company,
            status="Applied",
            date_updated=date_updated,
        )

    raise WriteIntentError(
        f"unsupported decision action: {decision.action!r}"
    )
