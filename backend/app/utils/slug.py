import re
import unicodedata


_MULTI_DASH_PATTERN = re.compile(r"-+")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower().strip()
    slug = _NON_ALNUM_PATTERN.sub("-", lowered).strip("-")
    slug = _MULTI_DASH_PATTERN.sub("-", slug)
    return slug or "organization"
