from src.normalization import normalize_company, normalize_role
from src.tracker_reader import TrackerApplication
from enum import Enum


class MatchResult(str, Enum):
    NONE = "none"
    UNIQUE = "unique"
    MULTIPLE = "multiple"


def classify_exact_matches(
    *,
    company: str | None,
    role: str | None,
    applications: list[TrackerApplication],
) -> tuple[MatchResult, list[TrackerApplication]]:
    matches = find_exact_application_matches(
        company=company,
        role=role,
        applications=applications,
    )

    if not matches:
        result = MatchResult.NONE
    elif len(matches) == 1:
        result = MatchResult.UNIQUE
    else:
        result = MatchResult.MULTIPLE

    return result, matches


def find_exact_application_matches(
    *,
    company: str | None,
    role: str | None,
    applications: list[TrackerApplication],
) -> list[TrackerApplication]:
    """
    Find tracker rows whose normalized company and role both
    exactly match the supplied values.

    Returns all matches rather than deciding which one to use.
    """

    normalized_company = normalize_company(company)
    normalized_role = normalize_role(role)

    if normalized_company is None or normalized_role is None:
        return []

    matches: list[TrackerApplication] = []

    for application in applications:
        if (
            normalize_company(application.company) == normalized_company
            and normalize_role(application.role) == normalized_role
        ):
            matches.append(application)

    return matches
