"""모든 시각 계산은 Asia/Seoul (기술 아키텍처 11장)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    return datetime.now(KST)


def asKst(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:  # SQLite 는 시간대를 저장하지 않으므로 KST 로 본다
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def iso(value: datetime | None) -> str | None:
    value = asKst(value)
    return value.isoformat(timespec="seconds") if value else None


def releaseAtFor(closeAt: datetime, releaseHour: int = 10) -> datetime:
    """결과 공개 시각 = 마감일 다음 날 10:00 (RPT-02)."""
    closeAt = asKst(closeAt)
    nextDay = (closeAt + timedelta(days=1)).date()
    return datetime(nextDay.year, nextDay.month, nextDay.day, releaseHour, 0, tzinfo=KST)
