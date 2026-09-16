import re
import unicodedata


def _normalize_text(value: str | None) -> str | None:
    """
    Apply conservative lexical normalization.

    This is intentionally not semantic normalization:
    - no acronym expansion
    - no company alias mapping
    - no role equivalence rules
    """
    if value is None:
        return None

    text = unicodedata.normalize("NFKC", value)
    text = text.casefold()

    # Treat ampersands consistently.
    text = text.replace("&", " and ")

    # Convert punctuation/separators to spaces.
    text = re.sub(r"[^\w\s]", " ", text)

    # Underscores count as separators for our purposes.
    text = text.replace("_", " ")

    # Collapse repeated whitespace.
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def normalize_company(company: str | None) -> str | None:
    """
    Normalize a company name for later deterministic comparison.

    Does not modify the original tracker value.
    """
    return _normalize_text(company)


def normalize_role(role: str | None) -> str | None:
    """
    Normalize a role title for later deterministic comparison.

    Does not attempt to determine whether different titles
    are semantically equivalent.
    """
    return _normalize_text(role)
