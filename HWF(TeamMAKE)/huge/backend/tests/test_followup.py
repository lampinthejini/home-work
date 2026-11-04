import pytest
from pydantic import ValidationError

from app.interview import engine as en


def test_followupNeedComesFromReasonCode():
    # 이유를 먼저 고르게 해 4B 모델이 판단 없이 need=false 부터 쓰던 문제를 막는다 (2026-11-03)
    assert list(en.FollowupDecision.model_json_schema()["properties"]) == ["reason_code", "question"]
    assert en.FollowupDecision(reason_code="vague", question="어떤 방법을 쓰셨나요?").need is True
    assert en.FollowupDecision(reason_code="none").need is False


def test_followupReasonCodeIsLimited():
    with pytest.raises(ValidationError):
        en.FollowupDecision(reason_code="interesting", question="더 말씀해 주시겠어요?")


def test_followupHasItsOwnTargetTime():
    # 운영 next_question_target_sec(5초) 안에는 T4 + TTS 가 들어가지 않아 꼬리질문만 목표 시간을 따로 둔다 (CONFLICTS U7)
    from app.config import SETTING_DEFAULTS

    prodFollowup, devFollowup = SETTING_DEFAULTS["followup_target_sec"]
    prodNext, _ = SETTING_DEFAULTS["next_question_target_sec"]
    prodMin, _ = SETTING_DEFAULTS["followup_min_sec"]
    assert prodNext == 5 and prodFollowup == 10 and devFollowup == 20
    assert prodFollowup - 2 - en.TTS_AVG_SEC >= prodMin  # STT 2초가 지나도 판단 시간이 남는다
