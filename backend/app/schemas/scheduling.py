from datetime import date, datetime

from app.schemas.common import ORMModel


class SlotRead(ORMModel):
    start_datetime: datetime
    end_datetime: datetime


class SlotQuery(ORMModel):
    provider_id: int
    start_date: date
    end_date: date
    service_id: int | None = None
