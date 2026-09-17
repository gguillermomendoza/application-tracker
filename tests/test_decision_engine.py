from src.decision_engine import DecisionAction, decide_application_event
from src.schemas import ApplicationEvent, EventType
from src.tracker_reader import TrackerApplication


def make_tracker_application(
    row_number: int,
    company: str,
    role: str,
    status: str = "Applied",
) -> TrackerApplication:
    return TrackerApplication(
        row_number=row_number,
        applied_date="9/10",
        role=role,
        company=company,
        hiring_manager=None,
        link=None,
        connections=None,
        status=status,
        date_updated="9/10",
    )


def make_event(
    company: str | None,
    role: str | None,
    event_type: EventType,
    confidence: float = 0.99,
    explicit_application_confirmation: bool = False,
) -> ApplicationEvent:
    return ApplicationEvent(
        company=company,
        role=role,
        event_type=event_type,
        event_date="2026-09-16",
        requisition_id=None,
        application_id=None,
        explicit_application_confirmation=explicit_application_confirmation,
        confidence=confidence,
    )


def test_new_application_confirmation_creates():
    event = make_event(
        company="Example Corp",
        role="Data Scientist",
        event_type=EventType.APPLIED,
        confidence=0.99,
        explicit_application_confirmation=True,
    )

    decision = decide_application_event(
        event=event,
        applications=[],
    )

    assert decision.action == DecisionAction.CREATE
    assert decision.existing_row is None
    assert decision.proposed_status == "Applied"


def test_existing_application_confirmation_is_ignored():
    applications = [
        make_tracker_application(
            row_number=37,
            company="Pinecone",
            role="Associate Field Engineer",
        )
    ]

    event = make_event(
        company="Pinecone",
        role="Associate Field Engineer",
        event_type=EventType.APPLIED,
        explicit_application_confirmation=True,
    )

    decision = decide_application_event(
        event=event,
        applications=applications,
    )

    assert decision.action == DecisionAction.IGNORE
    assert decision.existing_row == 37


def test_assessment_updates_existing_application():
    applications = [
        make_tracker_application(
            row_number=37,
            company="Pinecone",
            role="Associate Field Engineer",
            status="Applied",
        )
    ]

    event = make_event(
        company="Pinecone",
        role="Associate Field Engineer",
        event_type=EventType.ASSESSMENT,
    )

    decision = decide_application_event(
        event=event,
        applications=applications,
    )

    assert decision.action == DecisionAction.UPDATE
    assert decision.existing_row == 37
    assert decision.current_status == "Applied"
    assert decision.proposed_status == "Performance Task"


def test_multiple_matches_require_review():
    applications = [
        make_tracker_application(
            row_number=20,
            company="Example Corp",
            role="Data Scientist",
        ),
        make_tracker_application(
            row_number=45,
            company="Example Corp",
            role="Data Scientist",
        ),
    ]

    event = make_event(
        company="Example Corp",
        role="Data Scientist",
        event_type=EventType.REJECTED,
    )

    decision = decide_application_event(
        event=event,
        applications=applications,
    )

    assert decision.action == DecisionAction.REVIEW


def test_other_event_is_ignored():
    event = make_event(
        company="Example Corp",
        role="Data Scientist",
        event_type=EventType.OTHER,
    )

    decision = decide_application_event(
        event=event,
        applications=[],
    )

    assert decision.action == DecisionAction.IGNORE

def test_low_confidence_application_confirmation_requires_review():
    event = make_event(
        company="Example Corp",
        role="Data Scientist",
        event_type=EventType.APPLIED,
        confidence=0.90,
        explicit_application_confirmation=True,
    )

    decision = decide_application_event(
        event=event,
        applications=[],
    )

    assert decision.action == DecisionAction.REVIEW
    assert decision.existing_row is None
    assert decision.proposed_status is None


def test_low_confidence_existing_event_requires_review():
    applications = [
        make_tracker_application(
            row_number=37,
            company="Pinecone",
            role="Associate Field Engineer",
            status="Applied",
        )
    ]

    event = make_event(
        company="Pinecone",
        role="Associate Field Engineer",
        event_type=EventType.ASSESSMENT,
        confidence=0.80,
    )

    decision = decide_application_event(
        event=event,
        applications=applications,
    )

    assert decision.action == DecisionAction.REVIEW
    assert decision.existing_row == 37
    assert decision.current_status == "Applied"
    assert decision.proposed_status is None


def test_missing_role_requires_review():
    event = make_event(
        company="Example Corp",
        role=None,
        event_type=EventType.APPLIED,
        confidence=0.99,
        explicit_application_confirmation=True,
    )

    decision = decide_application_event(
        event=event,
        applications=[],
    )

    assert decision.action == DecisionAction.REVIEW
    assert decision.company == "Example Corp"
    assert decision.role is None


def test_existing_status_already_matches_is_ignored():
    applications = [
        make_tracker_application(
            row_number=37,
            company="Pinecone",
            role="Associate Field Engineer",
            status="Performance Task",
        )
    ]

    event = make_event(
        company="Pinecone",
        role="Associate Field Engineer",
        event_type=EventType.ASSESSMENT,
        confidence=0.99,
    )

    decision = decide_application_event(
        event=event,
        applications=applications,
    )

    assert decision.action == DecisionAction.IGNORE
    assert decision.existing_row == 37
    assert decision.current_status == "Performance Task"
    assert decision.proposed_status == "Performance Task"


def test_unmapped_event_requires_review():
    applications = [
        make_tracker_application(
            row_number=37,
            company="Pinecone",
            role="Associate Field Engineer",
            status="Phone/Hirevue Interview",
        )
    ]

    event = make_event(
        company="Pinecone",
        role="Associate Field Engineer",
        event_type=EventType.OFFER,
        confidence=0.99,
    )

    decision = decide_application_event(
        event=event,
        applications=applications,
    )

    assert decision.action == DecisionAction.REVIEW
    assert decision.existing_row == 37
    assert decision.proposed_status is None
