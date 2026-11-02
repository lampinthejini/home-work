"""요청 형식. 모델에 없는 칸이 오면 거절한다 (extra="forbid", TRD 4-3)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignupAgreements(Strict):
    age_14_plus: bool
    terms: bool
    privacy: bool


class SignupRequest(Strict):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=128)
    phone: str = Field(pattern=r"^01[0-9]-\d{3,4}-\d{4}$")
    agreements: SignupAgreements


class LoginRequest(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    next: str | None = None


class PasswordChangeRequest(Strict):
    current_password: str
    new_password: str


class PasswordResetRequest(Strict):
    email: str = Field(max_length=254)


class PasswordResetConfirm(Strict):
    token: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class WithdrawRequest(Strict):
    password: str = Field(max_length=128)
    confirm_text: str = Field(max_length=20)


class MePatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^01[0-9]-\d{3,4}-\d{4}$")


class MemoIn(Strict):
    body: str = Field(max_length=2000)


class CriteriaIn(Strict):
    weights: dict[str, int]
    coding_enabled: bool
    coding_ratio: int = 30
    pass_score: int = Field(default=70, ge=0, le=100)


class PostingIn(Strict):
    title: str | None = Field(default=None, max_length=200)
    job_code: str | None = None
    company_name: str | None = Field(default=None, max_length=200)
    company_intro: str | None = None
    duties: str | None = None
    requirements: str | None = None
    preferred: str | None = None
    employment_type: str | None = None
    location: str | None = Field(default=None, max_length=200)
    headcount: int | None = Field(default=None, ge=1, le=999)
    open_at: datetime | None = None
    close_at: datetime | None = None
    contact_email: str | None = None
    criteria: CriteriaIn | None = None


class DraftAiRequest(Strict):
    """AI 공고 초안 질문 (화면정의서 S-R02). 회사명은 받지 않는다 (단일 기업, 2026-10-30 사용자 결정)."""
    job_code: str
    career_level: str = Field(pattern="^(junior|experienced|any)$")
    career_years: int | None = Field(default=None, ge=0, le=30)
    employment_type: str = Field(pattern="^(full_time|contract|intern)$")
    location: str = Field(min_length=1, max_length=200)
    headcount: int = Field(ge=1, le=999)
    open_at: datetime
    close_at: datetime
    duties: list[str] = Field(min_length=1, max_length=10)
    skills: list[str] = Field(default_factory=list, max_length=20)
    preferred: str = Field(default="", max_length=500)
    company_intro: str = Field(min_length=1, max_length=1000)
    emphasis: str = Field(default="", max_length=500)
    coding_test: bool


class ApplicationCreate(Strict):
    posting_id: str


class ConsentItems(Strict):
    data_collection: bool
    ai_decision: bool
    share_with_admin: bool
    retention: bool
    exam_rules: bool


class ConsentRequest(Strict):
    consent_version: str
    items: ConsentItems


class EducationIn(Strict):
    school: str = ""
    major: str = ""
    degree: str = ""
    start: str = ""
    end: str | None = ""


class CareerIn(Strict):
    company: str = ""
    role: str = ""
    start: str = ""
    end: str | None = ""
    description: str = ""


class ProjectIn(Strict):
    name: str = ""
    period: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)


class CertificateIn(Strict):
    name: str = ""
    acquired: str = ""


class ResumeIn(Strict):
    name: str = Field(default="", max_length=100)
    education: list[EducationIn] = Field(default_factory=list, max_length=20)
    career: list[CareerIn] = Field(default_factory=list, max_length=30)
    projects: list[ProjectIn] = Field(default_factory=list, max_length=30)
    skills: list[str] = Field(default_factory=list, max_length=60)
    certificates: list[CertificateIn] = Field(default_factory=list, max_length=30)
    cover_letter: str | None = Field(default=None, max_length=5000)


class ResumeSubmit(Strict):
    method: str = Field(pattern="^(upload|manual|saved)$")
    upload_id: str | None = None
    resume: ResumeIn
    edited_fields: list[str] = Field(default_factory=list)


class Browser(Strict):
    name: str
    version: str


class Devices(Strict):
    mic: bool
    camera: bool
    speaker: bool


class PrecheckRequest(Strict):
    browser: Browser
    devices: Devices
    network_mbps: str | None = None


class CodeRun(Strict):
    problem_no: int = Field(ge=1, le=2)
    code: str = Field(max_length=50_000)


class CodeAutosave(Strict):
    problem_no: int = Field(ge=1, le=2)
    code: str = Field(max_length=50_000)
    paste_blocked: int = Field(default=0, ge=0, le=10_000)


class CodeItem(Strict):
    problem_no: int = Field(ge=1, le=2)
    code: str = Field(max_length=50_000)


class CodeSubmit(Strict):
    codes: list[CodeItem] = Field(max_length=2)
