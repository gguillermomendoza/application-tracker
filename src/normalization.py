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

ROLE_TOKEN_ALIASES = {
    "swe": "software engineer",
    "sde": "software development engineer",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "mle": "machine learning engineer",
    "de": "data engineer",
    "pm": "product manager",
    "qa": "quality assurance",
}

def normalize_role(role: str | None) -> str | None:
    normalized = _normalize_text(role)

    if normalized is None:
        return None

    tokens = normalized.split()

    expanded_tokens: list[str] = []

    for token in tokens:
        alias = ROLE_TOKEN_ALIASES.get(token)

        if alias is None:
            expanded_tokens.append(token)
        else:
            expanded_tokens.extend(alias.split())

    return " ".join(expanded_tokens)
