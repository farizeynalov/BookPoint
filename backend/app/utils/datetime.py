from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware.")
    return value.astimezone(timezone.utc)


def combine_local_datetime(target_date: date, target_time: time, timezone_name: str) -> datetime:
    local_zone = ZoneInfo(timezone_name)
    return datetime.combine(target_date, target_time).replace(tzinfo=local_zone)


def daterange(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)
