"""기존 표에 새 칸 넣기. create_all 은 이미 있는 표를 바꾸지 않으므로 PostgreSQL 에서만 직접 더한다.

2단계(채점·결과 공개)·RAG(질문 임베딩)에서 늘어난 칸. 같은 문장을 여러 번 돌려도 안전하다 (IF NOT EXISTS).
"""

import logging

from sqlalchemy import text

log = logging.getLogger("huge.migrate")

STATEMENTS = [
    "ALTER TABLE applications ADD COLUMN IF NOT EXISTS release_at timestamptz",
    "ALTER TABLE applications ADD COLUMN IF NOT EXISTS purge_at timestamptz",
    "ALTER TABLE applications ADD COLUMN IF NOT EXISTS review_reason varchar(24)",
    "CREATE INDEX IF NOT EXISTS ix_applications_release_at ON applications (release_at)",
    "CREATE INDEX IF NOT EXISTS ix_applications_purge_at ON applications (purge_at)",
    "ALTER TABLE coding_submissions ADD COLUMN IF NOT EXISTS feedback text",
    # 동의는 지원 건이 지워져도 남긴다 (테이블 정의서 4-9)
    "ALTER TABLE consents ADD COLUMN IF NOT EXISTS subject_hash varchar(64)",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS hidden_at timestamptz",
    "ALTER TABLE consents ALTER COLUMN application_id DROP NOT NULL",
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'consents'::regclass "
    "AND confrelid = 'applications'::regclass AND confdeltype = 'n') THEN "
    "ALTER TABLE consents DROP CONSTRAINT IF EXISTS consents_application_id_fkey; "
    "ALTER TABLE consents ADD CONSTRAINT consents_application_id_fkey FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE SET NULL; "
    "END IF; END $$",
]
# 테이블 정의서에 맞춘 덧붙이기 (CONFLICTS.md T19·T22·T25·T28·T32·T34·T35, 2026-11-02)
ALIGN_STATEMENTS = [
    # 값 목록이 늘어서 지우면 addChecks 가 새 목록으로 다시 만든다 (CONFLICTS U8)
    "ALTER TABLE results DROP CONSTRAINT IF EXISTS ck_results_decision_check",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at timestamptz",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
    "ALTER TABLE applications ADD COLUMN IF NOT EXISTS needs_review_since timestamptz",
    "ALTER TABLE applications ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
    "ALTER TABLE evaluation_criteria ADD COLUMN IF NOT EXISTS locked_at timestamptz",
    # 이미 잠긴 기준은 그 공고의 첫 응시 시각을 잠근 시각으로 본다
    "UPDATE evaluation_criteria c SET locked_at = (SELECT min(a.attempt_consumed_at) FROM applications a WHERE a.posting_id = c.posting_id) "
    "WHERE c.locked AND c.locked_at IS NULL",
    "ALTER TABLE posting_revisions ADD COLUMN IF NOT EXISTS summary varchar(300) NOT NULL DEFAULT ''",
    "ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS external_id varchar(100)",
    "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS updated_by varchar(36) REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE answers ADD COLUMN IF NOT EXISTS is_empty boolean NOT NULL DEFAULT false",
    # 질문 적용 범위 (CONFLICTS C-17, 2026-11-10). 기존 질문은 둘 다 비어 모든 공고에서 쓴다 (지금과 같다)
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS posting_id varchar(36) REFERENCES job_postings(id) ON DELETE CASCADE",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS job_code varchar(32)",
    "CREATE INDEX IF NOT EXISTS ix_questions_posting_id ON questions (posting_id)",
]
# 중복 행이 이미 있으면 만들지 못한다. 그때는 경고만 남기고 서비스는 뜬다 (2026-11-09)
UNIQUE_STATEMENTS = [
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_posting_user ON applications (posting_id, user_id)",
]
# 질문 DB 임베딩 (테이블 정의서 4-16: embedding vector(1024), HNSW vector_cosine_ops). 실패하면 RAG 만 꺼진다
VECTOR_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS embedding vector(1024)",
    "CREATE INDEX IF NOT EXISTS ix_questions_embedding ON questions USING hnsw (embedding vector_cosine_ops)",
]


def fillConsentSubjects(engine) -> None:
    """동의자 표시(subject_hash)가 빈 행을 채운다. 해시는 서버 비밀키 HMAC 이라 이메일 목록으로 되돌릴 수 없다."""
    from .crypto import subjectHash

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT c.id, u.email FROM consents c JOIN applications a ON a.id = c.application_id "
                                 "JOIN users u ON u.id = a.user_id WHERE c.subject_hash IS NULL")).all()
        for consentId, email in rows:
            conn.execute(text("UPDATE consents SET subject_hash = :h WHERE id = :id"), {"h": subjectHash(email), "id": consentId})


def addChecks(engine) -> None:
    """상태 칸 CHECK 제약 (models.CHECK_VALUES). 이미 있으면 건너뛴다. 기존 값이 어긋나면 그 제약만 빼고 경고한다 (서비스는 뜬다)."""
    from .models import CHECK_VALUES, checkName, checkSql

    for (table, column), values in CHECK_VALUES.items():
        name = checkName(table, column)
        try:
            with engine.begin() as conn:
                if conn.execute(text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name}).first():
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({checkSql(column, values)})"))
        except Exception as exc:  # noqa: BLE001
            log.warning("check %s not added (existing rows out of list?): %s", name, type(exc).__name__)


def addColumns(engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for statement in STATEMENTS + ALIGN_STATEMENTS:
            conn.execute(text(statement))
    fillConsentSubjects(engine)
    addChecks(engine)
    try:
        with engine.begin() as conn:
            for statement in UNIQUE_STATEMENTS:
                conn.execute(text(statement))
    except Exception as exc:  # noqa: BLE001
        log.warning("unique index not added (duplicate rows?): %s", type(exc).__name__)
    try:
        with engine.begin() as conn:
            for statement in VECTOR_STATEMENTS:
                conn.execute(text(statement))
    except Exception as exc:  # noqa: BLE001 — pgvector 가 없는 DB 에서도 서비스는 뜬다 (질문은 질문은행으로)
        log.warning("pgvector unavailable, RAG disabled: %s", type(exc).__name__)
