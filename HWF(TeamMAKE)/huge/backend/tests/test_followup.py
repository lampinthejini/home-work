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
