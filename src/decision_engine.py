from enum import Enum

from pydantic import BaseModel

from src.matching import find_application_matches
from src.schemas import ApplicationEvent, EventType
from src.tracker_reader import TrackerApplication


CREATE_CONFIDENCE_THRESHOLD = 0.95
UPDATE_CONFIDENCE_THRESHOLD = 0.90


class DecisionAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    REVIEW = "review"
    IGNORE = "ignore"


class ApplicationDecision(BaseModel):
    action: DecisionAction

    existing_row: int | None = None
    company: str | None = None
    role: str | None = None

    current_status: str | None = None
    proposed_status: str | None = None

    reason: str


# Keep this intentionally small.
# Only map statuses we already understand from the live tracker.
TRACKER_STATUS_BY_EVENT: dict[EventType, str] = {
    EventType.APPLIED: "Applied",
    EventType.ASSESSMENT: "Performance Task",
    EventType.RECRUITER_SCREEN: "Phone/Hirevue Interview",
    EventType.INTERVIEW: "Phone/Hirevue Interview",
    EventType.REJECTED: "Rejected: App",
}


def _same_status(current: str | None, proposed: str) -> bool:
    if current is None:
        return False

    return current.strip().casefold() == proposed.strip().casefold()


def decide_application_event(
    event: ApplicationEvent,
    applications: list[TrackerApplication],
) -> ApplicationDecision:
    """
    Determine what the tracker would do for one extracted application event.

    This function performs no writes and has no external side effects.
    """

    # OTHER events never need tracker modification.
    if event.event_type == EventType.OTHER:
        return ApplicationDecision(
            action=DecisionAction.IGNORE,
            company=event.company,
            role=event.role,
            reason="event does not represent a tracker-changing application event",
        )

    # Company + role are required for deterministic application identification.
    if not event.company or not event.role:
        return ApplicationDecision(
            action=DecisionAction.REVIEW,
            company=event.company,
            role=event.role,
            reason="company and role are required for reliable application identification",
        )

    matches = find_application_matches(
        company=event.company,
        role=event.role,
        applications=applications,
    )

    # Never guess when more than one tracker row satisfies the match.
    if len(matches) > 1:
        return ApplicationDecision(
            action=DecisionAction.REVIEW,
            company=event.company,
            role=event.role,
            reason=f"multiple tracker rows matched the application ({len(matches)} matches)",
        )

    # Application confirmations are handled separately because they are the
    # only events currently eligible to create a new tracker row.
    if event.event_type == EventType.APPLIED:
        if len(matches) == 1:
            match = matches[0]

            return ApplicationDecision(
                action=DecisionAction.IGNORE,
                existing_row=match.row_number,
                company=event.company,
                role=event.role,
                current_status=match.status,
                proposed_status=None,
                reason="application is already represented in the tracker",
            )

        if not event.explicit_application_confirmation:
            return ApplicationDecision(
                action=DecisionAction.REVIEW,
                company=event.company,
                role=event.role,
                reason="APPLIED event is not an explicit application confirmation",
            )

        if event.confidence < CREATE_CONFIDENCE_THRESHOLD:
            return ApplicationDecision(
                action=DecisionAction.REVIEW,
                company=event.company,
                role=event.role,
                reason=(
                    "application confirmation confidence is below "
                    f"{CREATE_CONFIDENCE_THRESHOLD:.2f}"
                ),
            )

        return ApplicationDecision(
            action=DecisionAction.CREATE,
            company=event.company,
            role=event.role,
            proposed_status=TRACKER_STATUS_BY_EVENT[EventType.APPLIED],
            reason=(
                "explicit application confirmation with no matching "
                "tracker application detected"
            ),
        )

    # Every other tracker-changing event currently requires an existing row.
    if len(matches) == 0:
        return ApplicationDecision(
            action=DecisionAction.REVIEW,
            company=event.company,
            role=event.role,
            reason="no existing tracker application matched this event",
        )

    match = matches[0]

    if event.confidence < UPDATE_CONFIDENCE_THRESHOLD:
        return ApplicationDecision(
            action=DecisionAction.REVIEW,
            existing_row=match.row_number,
            company=event.company,
            role=event.role,
            current_status=match.status,
            reason=(
                "event confidence is below "
                f"{UPDATE_CONFIDENCE_THRESHOLD:.2f}"
            ),
        )

    proposed_status = TRACKER_STATUS_BY_EVENT.get(event.event_type)

    # OFFER, WITHDRAWN, FINAL_INTERVIEW, etc. currently land here until
    # we deliberately define tracker-compatible statuses for them.
    if proposed_status is None:
        return ApplicationDecision(
            action=DecisionAction.REVIEW,
            existing_row=match.row_number,
            company=event.company,
            role=event.role,
            current_status=match.status,
            reason=(
                f"no approved tracker status mapping exists for "
                f"{event.event_type.value}"
            ),
        )

    # Avoid proposing a write when the tracker already has the desired status.
    if _same_status(match.status, proposed_status):
        return ApplicationDecision(
            action=DecisionAction.IGNORE,
            existing_row=match.row_number,
            company=event.company,
            role=event.role,
            current_status=match.status,
            proposed_status=proposed_status,
            reason="tracker already has the proposed status",
        )

    return ApplicationDecision(
        action=DecisionAction.UPDATE,
        existing_row=match.row_number,
        company=event.company,
        role=event.role,
        current_status=match.status,
        proposed_status=proposed_status,
        reason=f"{event.event_type.value} event matched one existing application",
    )
