"""DB 테이블 (1단계 범위). 칸 이름은 API 명세서·TRD 4-1 의 이름을 따른다(snake_case, DB 규칙 예외)."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .crypto import EncryptedJson, EncryptedText
from .db import Base
from .timeutil import now


def newId() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="applicant")  # applicant · admin
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agreements: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JobCode(Base):
    __tablename__ = "job_codes"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="preparing")  # open · preparing
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class JobPosting(Base):
    __tablename__ = "job_postings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft · published · closed
    source: Mapped[str] = mapped_column(String(16), default="manual")
    title: Mapped[str] = mapped_column(String(200), default="")
    job_code: Mapped[str] = mapped_column(String(32), default="AI_AX")
    company_name: Mapped[str] = mapped_column(String(200), default="")
    company_intro: Mapped[str] = mapped_column(Text, default="")
    duties: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[str] = mapped_column(Text, default="")
    preferred: Mapped[str] = mapped_column(Text, default="")
    employment_type: Mapped[str] = mapped_column(String(32), default="full_time")
    location: Mapped[str] = mapped_column(String(200), default="")
    headcount: Mapped[int] = mapped_column(Integer, default=1)
    open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(254), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    criteria: Mapped[list["EvaluationCriteria"]] = relationship(back_populates="posting", order_by="EvaluationCriteria.version",
                                                                cascade="all, delete-orphan", passive_deletes=True)


class EvaluationCriteria(Base):
    __tablename__ = "evaluation_criteria"
    __table_args__ = (UniqueConstraint("posting_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    posting_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    weights: Mapped[dict] = mapped_column(JSON)
    coding_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    coding_ratio: Mapped[int] = mapped_column(Integer, default=30)
    pass_score: Mapped[int] = mapped_column(Integer, default=70)

    posting: Mapped[JobPosting] = relationship(back_populates="criteria")


class PostingRevision(Base):
    __tablename__ = "posting_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    posting_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    revised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    field: Mapped[str] = mapped_column(String(64))
    before: Mapped[str] = mapped_column(Text, default="")
    after: Mapped[str] = mapped_column(Text, default="")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    posting_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id"), index=True)
    attempt_status: Mapped[str] = mapped_column(String(24), default="drafting")
    analysis_status: Mapped[str] = mapped_column(String(16), default="pending")
    release_status: Mapped[str] = mapped_column(String(16), default="scheduled")
    criteria_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resume_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resume_snapshot: Mapped[dict | None] = mapped_column(EncryptedJson, nullable=True)
    resume_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    edited_fields: Mapped[list] = mapped_column(JSON, default=list)
    resume_upload_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    questions_status: Mapped[str] = mapped_column(String(16), default="none")  # none · composing · ready
    precheck_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    holds_seat: Mapped[bool] = mapped_column(Boolean, default=False)
    seat_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase: Mapped[str] = mapped_column(String(16), default="interview")  # interview · coding
    current_seq: Mapped[int] = mapped_column(Integer, default=1)
    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    away_count: Mapped[int] = mapped_column(Integer, default=0)
    interrupted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interruption_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    interruption_judged: Mapped[str | None] = mapped_column(String(16), nullable=True)  # fault · not_fault
    end_detail: Mapped[str | None] = mapped_column(String(32), nullable=True)
    coding_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    coding_remaining_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interview_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)  # 이 건의 결과 공개 시각
    purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)  # 공개 + 7일
    review_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)  # needs_review 사유 (API 명세서 ops-status)

    posting: Mapped[JobPosting] = relationship()
    user: Mapped[User] = relationship()


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    # 지원 건이 지워져도 동의는 증거로 남긴다 (테이블 정의서 4-9: ON DELETE SET NULL)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    subject_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 이메일 SHA-256 — 지운 뒤에도 누가 동의했는지 맞춰 봄
    consent_version: Mapped[str] = mapped_column(String(16))
    items: Mapped[dict] = mapped_column(JSON)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResumeUpload(Base):
    __tablename__ = "resume_uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    file_key: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(16), default="uploaded")
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pages_text: Mapped[int] = mapped_column(Integer, default=0)
    pages_scanned: Mapped[int] = mapped_column(Integer, default=0)
    estimated_seconds: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(EncryptedJson, nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SavedResume(Base):
    __tablename__ = "saved_resumes"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    resume: Mapped[dict] = mapped_column(EncryptedJson)
    name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("sheet", "row_no"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16))  # excel · generated · reserve
    kind: Mapped[str] = mapped_column(String(16), index=True)  # personality · company · job · resume
    category: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text)
    sheet: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_group: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active · preparing · pending(검토 대기) · rejected · excluded(다른 회사명·무관 글)
    answer_seconds: Mapped[int] = mapped_column(Integer, default=90)
    eval_items: Mapped[list] = mapped_column(JSON, default=list)


class QuestionUsage(Base):
    __tablename__ = "question_usage"
    posting_id: Mapped[str] = mapped_column(ForeignKey("job_postings.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"
    __table_args__ = (UniqueConstraint("application_id", "seq", "kind", "answer_order"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16), default="base")  # base · follow_up
    answer_order: Mapped[int] = mapped_column(Integer, default=1)  # 1 = 기본, 2 = 꼬리질문
    qtype: Mapped[str] = mapped_column(String(16))  # personality · company · job · resume
    text: Mapped[str] = mapped_column(Text)
    source_question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="excel")
    regen_count: Mapped[int] = mapped_column(Integer, default=0)
    substituted: Mapped[bool] = mapped_column(Boolean, default=False)
    substitute_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answer_sec: Mapped[int] = mapped_column(Integer, default=90)
    eval_items: Mapped[list] = mapped_column(JSON, default=list)
    audio_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_sec: Mapped[float | None] = mapped_column(nullable=True)
    followup_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    interview_question_id: Mapped[int] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"), unique=True)
    transcript: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    words: Mapped[list | None] = mapped_column(EncryptedJson, nullable=True)
    audio_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_sec: Mapped[float | None] = mapped_column(nullable=True)
    stt_elapsed_sec: Mapped[float | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)  # done · timeout


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recording_segment: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Recording(Base):
    """카메라 녹화 (테이블 정의서 4-10). 접속 구간마다 하나. 평가에는 쓰지 않는다 (부정행위 확인용).

    저장소(S3)는 이어 쓰기가 안 되므로 10초 조각을 file_key 아래 chunk_no 순서 객체로 두고, 재생할 때 순서대로 이어 보낸다.
    """
    __tablename__ = "recordings"
    __table_args__ = (UniqueConstraint("application_id", "segment_no"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    segment_no: Mapped[int] = mapped_column(Integer)
    file_key: Mapped[str] = mapped_column(String(255))
    last_chunk_no: Mapped[int] = mapped_column(Integer, default=-1)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_chunk_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # 응시 끝 + 3일


class SessionEvent(Base):
    __tablename__ = "session_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    type: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    judged: Mapped[str | None] = mapped_column(String(16), nullable=True)  # fault · not_fault · cheating · info
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CodingSubmission(Base):
    __tablename__ = "coding_submissions"
    __table_args__ = (UniqueConstraint("application_id", "problem_no"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    problem_no: Mapped[int] = mapped_column(Integer)
    problem_key: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(Text, default="")
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paste_blocked: Mapped[int] = mapped_column(Integer, default=0)
    final: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)  # T8 코드 리뷰. 점수에 반영하지 않음


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)  # {"v": ...}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class DeletionLog(Base):
    """보관 기간·탈퇴·동의 철회로 지운 기록. 지운 내용은 남기지 않는다 (테이블 정의서 4-13)."""
    __tablename__ = "deletion_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cause: Mapped[str] = mapped_column(String(12))  # retention · withdraw · consent
    scope: Mapped[str] = mapped_column(String(16))  # recording · interview_data · account
    deleted_items: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StatsArchive(Base):
    """보관 기간이 지나 지운 지원 건의 익명 집계 (PRD 10-2 '통계 숫자 기한 없음', CONFLICTS F1).

    공고·응시 월별 숫자만 더해 둔다. 지원 건·회원을 가리키는 칸은 두지 않는다.
    """
    __tablename__ = "stats_archive"
    __table_args__ = (UniqueConstraint("posting_id", "month"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    posting_id: Mapped[str] = mapped_column(String(36), index=True)  # 공고를 지워도 숫자는 남도록 외래 키를 걸지 않는다
    posting_title: Mapped[str] = mapped_column(String(200), default="")
    month: Mapped[str] = mapped_column(String(7), default="")  # 응시 끝난 달(KST) YYYY-MM, 응시하지 않은 건은 ""
    applications: Mapped[int] = mapped_column(Integer, default=0)
    taken: Mapped[int] = mapped_column(Integer, default=0)
    decided: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    total_sum: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    score_bins: Mapped[list] = mapped_column(JSON, default=list)  # 10점 구간 10칸
    item_sums: Mapped[dict] = mapped_column(JSON, default=dict)  # {항목: [합계 문자열, 개수]}
    resumed: Mapped[int] = mapped_column(Integer, default=0)
    cheating_cancelled: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Result(Base):
    """지원 1건의 최종 점수와 결정 (테이블 정의서 4-12). 확정 뒤 고치지 않는다.

    합격 여부는 코드가 '총점 ≥ 합격 기준'으로 정하고, AI(T10)는 이유만 쓴다 (AI 아키텍처 v1.4).
    답변 인용이 들어가는 글은 암호화해 둔다.
    """
    __tablename__ = "results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    criteria_id: Mapped[int] = mapped_column(ForeignKey("evaluation_criteria.id"))
    item_points: Mapped[dict] = mapped_column(JSON, default=dict)
    interview_score: Mapped[float] = mapped_column(Numeric(5, 2))
    coding_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_score: Mapped[float] = mapped_column(Numeric(5, 2))
    pass_score: Mapped[float] = mapped_column(Numeric(5, 2))
    ai_decision: Mapped[str] = mapped_column(String(4))
    ai_reason: Mapped[str] = mapped_column(EncryptedText)
    ai_reason_quotes: Mapped[list] = mapped_column(EncryptedJson, default=list)
    strengths: Mapped[list] = mapped_column(EncryptedJson, default=list)
    improvements: Mapped[list] = mapped_column(EncryptedJson, default=list)
    summary: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    decision_check: Mapped[str] = mapped_column(String(12), default="ok")
    model_version: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    rubric_version: Mapped[str] = mapped_column(String(80))
    public_view: Mapped[dict] = mapped_column(EncryptedJson)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ItemScore(Base):
    """질문 번호마다 AI 가 매긴 항목 점수 (테이블 정의서 4-19). 꼬리질문 답변을 합쳐 채점한다."""
    __tablename__ = "item_scores"
    __table_args__ = (UniqueConstraint("interview_question_id", "eval_item"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    interview_question_id: Mapped[int] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"))
    eval_item: Mapped[str] = mapped_column(String(12))
    score: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    quote_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    regenerated: Mapped[bool] = mapped_column(Boolean, default=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Highlight(Base):
    """관리자가 다시 들어 볼 답변 구간 (테이블 정의서 4-20, TRD 8-4)."""
    __tablename__ = "highlights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    interview_question_id: Mapped[int] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))  # good · deducted
    eval_item: Mapped[str] = mapped_column(String(12))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(EncryptedText)


class Memo(Base):
    """지원자에 대한 관리자 내부 메모 (테이블 정의서 4-21). 지원자 응답에는 넣지 않는다 (ADM-05)."""
    __tablename__ = "memos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    """사이트 알림(머리글 🔔)과 같은 내용의 메일 발송 상태 (테이블 정의서 4-22)."""
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=newId)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_status: Mapped[str] = mapped_column(String(10), default="pending")  # pending · sent · deferred · failed · skipped
    email_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    email_fail_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
