import re

REDACTION_RULES = (
    (
        re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{35})\b"),
        "[REDACTED_API_KEY]",
    ),
    (
        re.compile(
            r"(?i)(\b(?:api[ _-]?key|llm_api_key)\s*[:=]\s*)"
            r"""["']?[A-Za-z0-9_./+=-]{12,}["']?"""
        ),
        r"\1[REDACTED_API_KEY]",
    ),
    (
        re.compile(r"(?<!\w)[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"(?<!\d)\d(?:[ -]?\d){12}(?!\d)"),
        "[REDACTED_THAI_ID]",
    ),
    (
        re.compile(
            r"(?<![\w+])(?:\+66[ .-]?|0)"
            r"(?:[689](?:[ .-]?\d){8}|[2-57](?:[ .-]?\d){7})(?!\d)"
        ),
        "[REDACTED_PHONE]",
    ),
)


def redact_for_llm(message: str) -> str:
    for pattern, replacement in REDACTION_RULES:
        message = pattern.sub(replacement, message)
    return message