"""app_settings: 재시작 없이 바꾸는 설정값 (TRD 14장). 행이 없으면 프로필 기본값."""

from sqlalchemy.orm import Session

from .config import SETTING_DEFAULTS, defaultSetting
from .models import AppSetting


def getSetting(db: Session, key: str):
    row = db.get(AppSetting, key)
    if row is not None:
        return row.value["v"]
    return defaultSetting(key)


def setSetting(db: Session, key: str, value) -> None:
    if key not in SETTING_DEFAULTS:
        raise KeyError(key)
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value={"v": value}))
    else:
        row.value = {"v": value}
    db.commit()


def allSettings(db: Session) -> dict:
    return {key: getSetting(db, key) for key in SETTING_DEFAULTS}
