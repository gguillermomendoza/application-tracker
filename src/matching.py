from enum import Enum

from rapidfuzz.fuzz import ratio

from src.normalization import normalize_company, normalize_role
from src.tracker_reader import TrackerApplication


ROLE_SIMILARITY_THRESHOLD = 92.0


# These tokens represent meaningful differences in role seniority/type.
# Fuzzy matching must never erase them.
PROTECTED_ROLE_QUALIFIERS = frozenset(
    {
        "intern",
        "internship",
        "junior",
        "jr",
        "senior",
        "sr",
        "staff",
        "principal",
        "lead",
        "manager",
        "director",
        "i",
        "ii",
        "iii",
        "iv",
    }
)


class MatchResult(str, Enum):
    NONE = "none"
    UNIQUE = "unique"
    MULTIPLE = "multiple"


def _role_qualifiers(role: str) -> set[str]:
    """
    Extract protected role qualifiers from an already-normalized role.

    These qualifiers must match exactly before fuzzy role matching
    is allowed.
    """

    return {
        token
        for token in role.split()
        if token in PROTECTED_ROLE_QUALIFIERS
    }


def _roles_are_typo_match(
    left: str,
    right: str,
) -> bool:
    """
    Determine whether two normalized roles are close enough to be
    treated as the same role despite a likely typo.

    This is intentionally conservative:
      - protected qualifiers must match exactly
      - similarity must exceed a high threshold
    """

    if left == right:
        return True

    if _role_qualifiers(left) != _role_qualifiers(right):
        return False

    similarity = ratio(left, right)

    return similarity >= ROLE_SIMILARITY_THRESHOLD


def find_exact_application_matches(
    *,
    company: str | None,
    role: str | None,
    applications: list[TrackerApplication],
) -> list[TrackerApplication]:
    """
    Find tracker rows whose normalized company and role both
    exactly match the supplied values.

    This remains available for callers that specifically require
    strict exact matching.
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


def find_application_matches(
    *,
    company: str | None,
    role: str | None,
    applications: list[TrackerApplication],
) -> list[TrackerApplication]:
    """
    Find tracker rows representing the same application.

    Matching strategy:

    1. Company must match exactly after normalization.
    2. Exact normalized role matches take precedence.
    3. If no exact role exists, allow conservative typo-tolerant
       role matching.
    4. Protected role qualifiers must match exactly.
    5. Return every acceptable match rather than choosing between
       ambiguous rows.

    Company names are deliberately NOT fuzzily matched.
    """

    normalized_company = normalize_company(company)
    normalized_role = normalize_role(role)

    if normalized_company is None or normalized_role is None:
        return []

    same_company: list[
        tuple[TrackerApplication, str]
    ] = []

    for application in applications:
        application_company = normalize_company(
            application.company
        )
        application_role = normalize_role(
            application.role
        )

        if (
            application_company == normalized_company
            and application_role is not None
        ):
            same_company.append(
                (application, application_role)
            )

    # Exact/canonical matches always win.
    exact_matches = [
        application
        for application, application_role in same_company
        if application_role == normalized_role
    ]

    if exact_matches:
        return exact_matches

    # Only fall back to typo tolerance when there was no exact match.
    typo_matches = [
        application
        for application, application_role in same_company
        if _roles_are_typo_match(
            normalized_role,
            application_role,
        )
    ]

    return typo_matches


def classify_application_matches(
    *,
    company: str | None,
    role: str | None,
    applications: list[TrackerApplication],
) -> tuple[MatchResult, list[TrackerApplication]]:
    matches = find_application_matches(
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


def classify_exact_matches(
    *,
    company: str | None,
    role: str | None,
    applications: list[TrackerApplication],
) -> tuple[MatchResult, list[TrackerApplication]]:
    """
    Backwards-compatible exact-match classifier.
    """

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
