"""Small privacy helpers for outbound prompts and operational question logs."""
import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def mask_personal_data(text: str) -> str:
    """Mask common direct contact identifiers before external AI or analytics."""
    def mask_phone(match: re.Match[str]) -> str:
        return "[phone]" if sum(character.isdigit() for character in match.group()) >= 9 else match.group()

    return _PHONE.sub(mask_phone, _EMAIL.sub("[email]", str(text or "")))
