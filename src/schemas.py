from enum import Enum

from pydantic import BaseModel, Field


class EventType(str, Enum):
    APPLIED = "applied"
    ASSESSMENT = "assessment"
    RECRUITER_SCREEN = "recruiter_screen"
    INTERVIEW = "interview"
    FINAL_INTERVIEW = "final_interview"
    REJECTED = "rejected"
    OFFER = "offer"
    WITHDRAWN = "withdrawn"
    OTHER = "other"


class ApplicationEvent(BaseModel):
    company: str | None = Field(
        default=None,
        description="Company associated with the job application event.",
    )

    role: str | None = Field(
        default=None,
        description="Job title or role associated with the event.",
    )

    event_type: EventType = Field(
        description="The job application lifecycle event represented by the email."
    )

    event_date: str | None = Field(
        default=None,
        description="Date of the event in YYYY-MM-DD format when supported by the email.",
    )

    requisition_id: str | None = Field(
        default=None,
        description="Job requisition or job posting identifier, if explicitly present.",
    )

    application_id: str | None = Field(
        default=None,
        description="Application identifier, if explicitly present.",
    )

    explicit_application_confirmation: bool = Field(
        description=(
            "True only when the email explicitly confirms that an application "
            "was successfully submitted or received."
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model confidence in the extraction from 0 to 1.",
    )
