"""환경 설정(.env)과 재시작 없이 바꾸는 설정값(app_settings)의 기본값.

설정값의 키와 값은 TRD 14장을 따른다. APP_PROFILE=dev 이면 '개발 환경' 열의 값을 쓴다.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Env:
    profile: str
    databaseUrl: str
    redisUrl: str
    encryptionKey: str
    llmRtUrl: str
    llmEvalUrl: str
    sttUrl: str
    ttsUrl: str
    ocrUrl: str
    embedUrl: str
    smtpHost: str
    smtpPort: int
    adminEmail: str
    adminInitialPassword: str
    publicOrigin: str
    itQuestionsPath: str
    personalityQuestionsPath: str
    trustedProxyHost: str
    loginExemptIps: str


def loadEnv() -> Env:
    return Env(
        profile=os.environ.get("APP_PROFILE", "dev"),
        databaseUrl=os.environ.get("DATABASE_URL", "sqlite:///./huge-dev.db"),
        redisUrl=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        encryptionKey=os.environ.get("APP_ENCRYPTION_KEY", ""),
        llmRtUrl=os.environ.get("LLM_RT_URL", "http://localhost:8081/v1"),
        llmEvalUrl=os.environ.get("LLM_EVAL_URL", "http://localhost:8082/v1"),
        sttUrl=os.environ.get("STT_URL", "http://localhost:9000"),
        ttsUrl=os.environ.get("TTS_URL", "http://localhost:9001"),
        ocrUrl=os.environ.get("OCR_URL", "http://localhost:9002"),
        embedUrl=os.environ.get("EMBED_URL", "http://localhost:9003"),
        smtpHost=os.environ.get("SMTP_HOST", "localhost"),
        smtpPort=int(os.environ.get("SMTP_PORT", "1025")),
        adminEmail=os.environ.get("ADMIN_EMAIL", "admin@huge.local"),
        adminInitialPassword=os.environ.get("ADMIN_INITIAL_PASSWORD", ""),
        publicOrigin=os.environ.get("PUBLIC_ORIGIN", "http://127.0.0.1:8080"),
        itQuestionsPath=os.environ.get("IT_QUESTIONS_PATH", "/data/it_questions.xlsx"),
        personalityQuestionsPath=os.environ.get("PERSONALITY_QUESTIONS_PATH", "/data/personality_questions.xlsx"),
        trustedProxyHost=os.environ.get("TRUSTED_PROXY_HOST", "frontend"),
        loginExemptIps=os.environ.get("LOGIN_EXEMPT_IPS", ""),
    )


ENV = loadEnv()

# TRD 14장. (운영 서버, 개발 환경)
SETTING_DEFAULTS: dict[str, tuple] = {
    "max_concurrent_interviews": (2, 1),
    "disconnect_seat_hold_min": (10, 10),
    "resume_limit": (3, 3),  # 지원자 쪽 끊김으로 이어갈 수 있는 횟수 (CONFLICTS D1)
    "heartbeat_interval_sec": (5, 5),
    "heartbeat_miss_limit": (3, 3),
    "unload_lookback_sec": (30, 30),
    "blur_threshold_sec": (2, 2),
    "upload_retry_limit": (3, 3),
    "stt_retry_limit": (2, 2),
    "stt_attempt_timeout_sec": (20, 60),
    "caption_interval_sec": (1, 3),
    "next_question_target_sec": (5, 20),
    "followup_min_sec": (2, 3),
    # 꼬리질문을 낼 때만 쓰는 목표 시간 (답변 끝 → 꼬리질문). 5초 안에는 T4 판단 + TTS(실측 5~7초)가 들어가지 않아
    # 2026-11-03 사용자 결정(①)으로 따로 둔다. 꼬리질문이 없으면 next_question_target_sec 그대로 (CONFLICTS U7)
    "followup_target_sec": (10, 20),
    "question_regen_limit": (3, 3),
    "rag_example_count": (3, 3),
    "question_attempt_timeout_sec": (8, 30),
    "question_compose_budget_sec": (60, 180),
    "compose_slots": (1, 1),
    "upload_max_mb": (50, 50),
    "ocr_sec_per_page": (8, 8),
    "resume_llm_sec": (20, 20),
    "precheck_valid_min": (15, 15),
    "base_answer_sec": (90, 90),
    "followup_answer_sec": (60, 60),
    "followup_total_limit": (4, 4),
    "coding_limit_sec": (3600, 3600),
    "coding_intro_auto_start_sec": (60, 60),
    "session_idle_hours": (2, 2),
    "login_fail_limit": (5, 5),
    "login_lock_min": (10, 10),
    "login_block_window_min": (60, 60),
    "login_block_hours": (24, 24),
    "release_hour": (10, 10),
    "consent_version": ("v1.8", "v1.8"),  # 2026-11-09 ⑤ "응시 취소(1차 불합격)"
}


def defaultSetting(key: str):
    prod, dev = SETTING_DEFAULTS[key]
    return dev if ENV.profile == "dev" else prod
