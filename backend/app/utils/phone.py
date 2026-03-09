import re


def normalize_phone_number(raw_phone_number: str) -> str:
    stripped = raw_phone_number.strip()
    digits = re.sub(r"\D", "", stripped)
    if not digits:
        raise ValueError("Phone number must contain digits.")

    normalized = f"+{digits}"
    if len(digits) < 7:
        raise ValueError("Phone number is too short.")
    if len(digits) > 15:
        raise ValueError("Phone number is too long.")
    return normalized
