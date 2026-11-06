from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Base(DeclarativeBase):
    pass
