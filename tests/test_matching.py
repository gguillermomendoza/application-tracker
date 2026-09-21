from src.matching import find_application_matches
from src.tracker_reader import TrackerApplication


def make_application(
    row_number: int,
    company: str,
    role: str,
) -> TrackerApplication:
    return TrackerApplication(
        row_number=row_number,
        applied_date="9/10",
        role=role,
        company=company,
        hiring_manager=None,
        link=None,
        connections=None,
        status="Applied",
        date_updated="9/10",
    )


def test_exact_role_matches():
    applications = [
        make_application(
            10,
            "Salesforce",
            "Software Engineer",
        )
    ]

    matches = find_application_matches(
        company="Salesforce",
        role="Software Engineer",
        applications=applications,
    )

    assert len(matches) == 1
    assert matches[0].row_number == 10


def test_minor_role_typo_matches():
    applications = [
        make_application(
            10,
            "Salesforce",
            "Software Engineer",
        )
    ]

    matches = find_application_matches(
        company="Salesforce",
        role="Softwate Engineer",
        applications=applications,
    )

    assert len(matches) == 1
    assert matches[0].row_number == 10


def test_different_company_does_not_match_even_with_same_role():
    applications = [
        make_application(
            10,
            "Salesforce",
            "Software Engineer",
        )
    ]

    matches = find_application_matches(
        company="Google",
        role="Software Engineer",
        applications=applications,
    )

    assert matches == []


def test_senior_role_does_not_match_non_senior_role():
    applications = [
        make_application(
            10,
            "Salesforce",
            "Software Engineer",
        )
    ]

    matches = find_application_matches(
        company="Salesforce",
        role="Senior Software Engineer",
        applications=applications,
    )

    assert matches == []


def test_role_level_one_does_not_match_level_two():
    applications = [
        make_application(
            10,
            "Salesforce",
            "Software Engineer II",
        )
    ]

    matches = find_application_matches(
        company="Salesforce",
        role="Software Engineer I",
        applications=applications,
    )

    assert matches == []


def test_intern_role_does_not_match_full_time_role():
    applications = [
        make_application(
            10,
            "Salesforce",
            "Software Engineer",
        )
    ]

    matches = find_application_matches(
        company="Salesforce",
        role="Software Engineer Intern",
        applications=applications,
    )

    assert matches == []


def test_exact_match_takes_precedence_over_fuzzy_candidates():
    applications = [
        make_application(
            10,
            "Salesforce",
            "Software Engineer",
        ),
        make_application(
            11,
            "Salesforce",
            "Software Enginer",
        ),
    ]

    matches = find_application_matches(
        company="Salesforce",
        role="Software Engineer",
        applications=applications,
    )

    assert len(matches) == 1
    assert matches[0].row_number == 10


def test_multiple_typo_matches_are_returned_for_ambiguity():
    applications = [
        make_application(
            10,
            "Example Corp",
            "Software Engineer",
        ),
        make_application(
            11,
            "Example Corp",
            "Softwaie Engineer",
        ),
    ]

    matches = find_application_matches(
        company="Example Corp",
        role="Softwate Engineer",
        applications=applications,
    )

    assert len(matches) == 2

def test_missing_role_never_matches_by_company():
    applications = [
        make_application(
            10,
            "Tata Consultancy Services",
            "Data Scientist",
        ),
        make_application(
            11,
            "Tata Consultancy Services",
            "Software Engineer",
        ),
    ]

    matches = find_application_matches(
        company="Tata Consultancy Services",
        role=None,
        applications=applications,
    )

    assert matches == []
