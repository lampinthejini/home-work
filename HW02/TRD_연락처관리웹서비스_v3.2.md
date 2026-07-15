# 연락처 관리 웹 서비스

## TRD (기술 요구사항 정의서) — v3.2

> 목적: 이 문서 하나만으로 FastAPI + PostgreSQL 기반 연락처 관리 웹 서비스를
> AI가 오차 없이 구현할 수 있도록, 상세 명세(v1.0 TRD)와 압축 구조(v2.0
> ADS+TRD)의 장점을 결합하고, 코드 골격·시퀀스 다이어그램·와이어프레임·
> 미확정 설정값 부록을 추가해 재구성한 통합 명세서.

---

## 문서 이력

| 버전 | 특징 |
|---|---|
| v1.0 | 상세 TRD. 배경·근거·엣지케이스·48개 테스트 케이스까지 포함하나 분량이 많고 표 구조가 복잡함 |
| v2.0 | 압축 ADS+TRD. 구조가 간결하나 API 상세, 예외 상황, 테스트 시나리오가 부족함 |
| v3.0 | v1.0의 구체성 + v2.0의 간결한 구조를 결합 |
| v3.1 | Model/Schema 코드 골격, CRUD 흐름도, Sequence Diagram, 화면 와이어프레임 추가 |
| **v3.2 (본 문서)** | 부록 A 추가 — 쿠키 옵션, Argon2 파라미터, CORS, 비밀번호 정책, main.py 설정, 테스트 프레임워크 등 이전에 "AI 임의 판단"이던 항목을 명시적 기본값으로 확정 |

---

## 1. 프로젝트 개요

### 1-1. 목표

- 회원가입 / 로그인 / 로그아웃 (Session Cookie 인증)
- 연락처 CRUD + 이름 검색
- 카테고리 CRUD (사용 중인 카테고리는 삭제 거부)
- 사용자별 데이터 완전 격리
- PostgreSQL 영속화 (서버 재시작 후에도 로그인·데이터 유지)

### 1-2. 개발 원칙

- 계층 분리: 화면 → Router → CRUD → Model/DB (계층 건너뛰기 금지)
- REST API, SQLAlchemy 2.0 ORM, Pydantic 2 Validation
- 모든 쓰기 작업은 단일 트랜잭션(Commit/Rollback)으로 처리
- 형식 검증(Pydantic)과 비즈니스 검증(코드)을 분리
- 모든 조회는 `user_id`를 조건에 반드시 포함 (데이터 격리의 핵심)
- 남의 데이터 접근 시 403이 아니라 **404**로 응답 (존재 여부 자체를 숨김)

---

## 2. 기술 스택

| 구성 | 버전 | 비고 |
|---|---|---|
| Python | 3.12.x | FastAPI는 3.10+ 요구 |
| FastAPI | 0.139.x | Pydantic v2 전용 |
| Pydantic | 2.13.x | FastAPI 0.139.x와 호환 확인된 조합 |
| SQLAlchemy | 2.0.x | `Mapped[...]` 스타일 문법 사용 |
| psycopg | 3.x | 접속 문자열에 `postgresql+psycopg://` 명시 필수 |
| pwdlib[argon2] | 0.3.x | `[argon2]` extra 누락 시 런타임 오류 |
| Uvicorn | standard | `--reload` 사용 시 `uvicorn[standard]` 필요 |
| PostgreSQL | 16 (Docker) | 컨테이너로 로컬 구동 |

### 2-1. 버전 고정 이유 (충돌 방지)

| 관계 | 충돌 위험 |
|---|---|
| FastAPI ↔ Pydantic | Pydantic v1로 설치되면 `BaseModel` 문법이 달라 전면 오류 |
| SQLAlchemy ↔ psycopg | 접속 문자열에 `+psycopg` 누락 시 기본값(psycopg2)을 찾다가 `ModuleNotFoundError` |
| SQLAlchemy 2.0 문법 | 1.4 이하 설치 시 `Mapped[...]` 모델 정의 자체가 임포트 단계에서 실패 |
| pwdlib[argon2] | extra 없이 설치하면 해싱 시도 시 런타임 오류 |
| Python 버전 | 3.9 이하에서는 `X | None` 같은 타입 힌트 문법 오류 |

```
# requirements.txt
fastapi==0.139.0
pydantic==2.13.4
sqlalchemy==2.0.51
psycopg[binary]==3.3.4
pwdlib[argon2]==0.3.0
uvicorn[standard]==0.50.0
```

---

## 3. 프로젝트 구조

```
contact_app/
├── main.py            # 앱 조립: FastAPI 생성, 라우터 등록, 화면 제공
├── database.py         # engine, SessionLocal, get_db
├── models.py           # SQLAlchemy 모델
├── schemas.py           # Pydantic 입출력 모델
├── crud.py              # DB 비즈니스 로직
├── security.py          # hash_password, verify_password
├── routers/
│   ├── auth.py          # 인증 엔드포인트 4개 + get_current_user 의존성
│   ├── contacts.py       # 연락처 엔드포인트 4개
│   └── categories.py     # 카테고리 엔드포인트 4개
└── static/
    ├── index.html        # 화면
    └── app.js             # fetch 호출 + DOM 갱신
```

> **이름 충돌 주의**: SQLAlchemy DB 세션(`Session`)과 로그인 세션(`sessions`
> 테이블)은 다른 개념이다. 로그인 세션의 모델 클래스명은 `LoginSession`으로
> 정한다(테이블명은 `sessions` 유지). `from sqlalchemy.orm import Session`과
> 이름이 겹치면 임포트 순서에 따라 찾기 어려운 버그가 발생한다.

---

## 4. 시스템 아키텍처

```
Browser (HTML/JS)
   ↓
표현 계층 (routers/*.py)   ─ URL·메서드 연결, 상태 코드 결정, 세션 확인
   ↓
로직 계층 (crud.py, security.py) ─ 조회·생성·수정·삭제, user_id 격리
   ↓
데이터 계층 (models.py, database.py) ─ 테이블 정의, DB 연결
   ↓
PostgreSQL
```

각 계층은 바로 아래 계층만 호출한다. Router에는 SQL을 작성하지 않으며,
DB 접근은 CRUD 계층만 수행한다.

### 4-1. 요청 처리 파이프라인 (공통 5단계)

```
화면(fetch) → ① 세션 확인(401) → ② 형식 검증(422, Pydantic 자동)
           → ③ 비즈니스 검증(404/409, 코드 직접 작성)
           → ④ 처리 + 커밋(INSERT/SELECT/UPDATE/DELETE)
           → ⑤ JSON 응답(200/201/204)
```

어느 단계에서 실패하든 이후 단계는 실행되지 않고 즉시 오류 응답이
나가므로, 정상적인 흐름에서는 500이 발생하지 않는다.

### 4-2. Sequence Diagram (핵심 흐름 4가지)

복잡도가 높은 흐름만 뽑아 시퀀스로 표현한다. 나머지 단순 CRUD(연락처
수정/삭제, 카테고리 목록 조회 등)는 4-1의 5단계 파이프라인을 그대로
따르므로 별도 다이어그램 없이 그 규칙을 적용하면 된다.

**(1) 회원가입 — POST /auth/signup (2개 INSERT 단일 트랜잭션)**

```
Browser          Router(auth.py)      CRUD(crud.py)         DB
  │  POST /auth/signup   │                    │                │
  │──────────────────────▶│                    │                │
  │                       │ Pydantic 검증(422) │                │
  │                       │───────────────────▶│ create_user()  │
  │                       │                    │ SELECT username│
  │                       │                    │───────────────▶│
  │                       │                    │◀───────────────│
  │                       │                    │ (중복) → 409   │
  │                       │                    │ (통과)          │
  │                       │                    │ hash_password() │
  │                       │                    │ INSERT users    │
  │                       │                    │───────────────▶│
  │                       │                    │ INSERT category×3│
  │                       │                    │───────────────▶│
  │                       │                    │ COMMIT          │
  │                       │                    │───────────────▶│
  │                       │◀───────────────────│ User 반환       │
  │◀──────────────────────│ 201 JSON           │                │
```

**(2) 로그인 — POST /auth/login (세션 발급)**

```
Browser          Router(auth.py)      CRUD(crud.py)         DB
  │  POST /auth/login    │                    │                │
  │──────────────────────▶│                    │                │
  │                       │───────────────────▶│authenticate_user()│
  │                       │                    │ SELECT username │
  │                       │                    │───────────────▶│
  │                       │                    │◀───────────────│
  │                       │                    │ verify_password()│
  │                       │                    │ (실패) → 401     │
  │                       │◀───────────────────│ (성공) User 반환 │
  │                       │───────────────────▶│create_login_session()│
  │                       │                    │ token_hex(32)    │
  │                       │                    │ INSERT sessions  │
  │                       │                    │───────────────▶│
  │                       │◀───────────────────│ session_id 반환  │
  │◀──────────────────────│ 200 + Set-Cookie    │                │
```

**(3) 연락처 등록 — POST /contacts (검증 4단계)**

```
Browser      Router(contacts.py)   CRUD(crud.py)          DB
  │ POST /contacts(본문) │                    │                │
  │──────────────────────▶│                    │                │
  │                       │ Depends(get_current_user) → 세션 확인│
  │                       │  (무효) → 401 종료  │                │
  │                       │ ContactCreate 검증(422)│             │
  │                       │───────────────────▶│ 내 카테고리인가?│
  │                       │                    │───────────────▶│
  │                       │                    │◀───────────────│
  │                       │                    │ (아니면) → 404  │
  │                       │                    │ 전화번호 중복?  │
  │                       │                    │───────────────▶│
  │                       │                    │◀───────────────│
  │                       │                    │ (중복) → 409    │
  │                       │                    │ create_contact()│
  │                       │                    │ INSERT + COMMIT │
  │                       │                    │───────────────▶│
  │                       │◀───────────────────│ Contact 반환    │
  │◀──────────────────────│ 201 JSON            │                │
```

**(4) 카테고리 삭제 — DELETE /categories/{id} (사용 중 확인)**

```
Browser     Router(categories.py)  CRUD(crud.py)          DB
  │ DELETE /categories/{id}│                    │                │
  │──────────────────────▶│                    │                │
  │                       │ 세션 확인(401)      │                │
  │                       │───────────────────▶│ 내 카테고리인가?│
  │                       │                    │───────────────▶│
  │                       │                    │◀───────────────│
  │                       │                    │ (아니면) → 404  │
  │                       │                    │ count_contacts_in_category()│
  │                       │                    │───────────────▶│
  │                       │                    │◀── count=N ─────│
  │                       │                    │ N>0 → 409 반환   │
  │                       │                    │ N=0 → delete_category()│
  │                       │                    │ DELETE + COMMIT  │
  │                       │                    │───────────────▶│
  │◀──────────────────────│ 204 또는 409         │                │
```

---

## 5. 데이터베이스 설계

```
sessions          users            categories
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│session_id(PK)│─▶│id (PK)       │◀─│id (PK)       │
│user_id (FK)  │  │username(UQ)  │  │user_id (FK)  │
│created_at    │  │password_hash │  │name          │
└──────────────┘  │created_at    │  │UQ(user_id,   │
                   └──────────────┘  │   name)      │
                          ▲          └──────────────┘
                          │                  ▲
                          │                  │
                   ┌──────────────────────────────┐
                   │ contacts                      │
                   │ id (PK)                       │
                   │ user_id (FK → users.id)       │
                   │ category_id (FK → categories.id)│
                   │ name / phone / addr            │
                   │ UQ(user_id, phone)             │
                   └──────────────────────────────┘
```

### users

| 열 | 타입 | 제약 | 설명 |
|---|---|---|---|
| id | 정수(자동증가) | PK | 사용자 고유 번호 |
| username | 문자열 4~20자 | UNIQUE, NOT NULL | 영문 소문자+숫자 |
| password_hash | 문자열 | NOT NULL | Argon2 해시만 저장 (원문 저장 금지) |
| created_at | 일시 | 기본값=현재 시각 | 가입일 |

### sessions

| 열 | 타입 | 제약 | 설명 |
|---|---|---|---|
| session_id | 문자열 64자 | PK | `secrets.token_hex(32)` |
| user_id | 정수 | FK→users.id, NOT NULL | 세션 소유자 |
| created_at | 일시 | 기본값=현재 시각 | 로그인 시각 |

### categories

| 열 | 타입 | 제약 | 설명 |
|---|---|---|---|
| id | 정수(자동증가) | PK | 카테고리 번호 |
| user_id | 정수 | FK→users.id, NOT NULL | 소유 사용자 |
| name | 문자열 1~10자 | NOT NULL | 카테고리명 |
| (테이블 제약) | - | UNIQUE(user_id, name) | 같은 사용자 내 이름 중복 금지 |

### contacts

| 열 | 타입 | 제약 | 설명 |
|---|---|---|---|
| id | 정수(자동증가) | PK | 연락처 고유 번호 |
| user_id | 정수 | FK→users.id, NOT NULL | 소유자 |
| category_id | 정수 | FK→categories.id, NOT NULL | 소속 카테고리 |
| name | 문자열 1~5자 | NOT NULL | 이름 |
| phone | 문자열 11자 | NOT NULL | `010` + 숫자 8자리 |
| addr | 문자열 | 빈 값 허용 | 주소(검증 없음) |
| (테이블 제약) | - | UNIQUE(user_id, phone) | 같은 사용자 내 전화번호 중복 금지 |

> **설계 근거 — PK를 전화번호가 아닌 id로 하는 이유**: 전화번호는 수정
> 가능한 값이므로 PK로 부적합하다. 대리키(surrogate key)를 PK로 쓰고,
> 중복 방지는 `UNIQUE(user_id, phone)` 복합 제약으로 처리한다. 서로 다른
> 사용자가 같은 번호를 각자 저장할 수 있어야 하기 때문이다.

---

## 6. SQLAlchemy 모델

> `models.py`에 아래 골격을 그대로 사용한다. 관계(`relationship`)는
> 필수는 아니지만, `category_name`을 응답에 포함해야 하므로(9-2 참고)
> `Contact.category` 관계를 정의해두면 CRUD 조회가 단순해진다.

```python
# models.py
import datetime
from sqlalchemy import String, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class LoginSession(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(10), nullable=False)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("user_id", "phone"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(5), nullable=False)
    phone: Mapped[str] = mapped_column(String(11), nullable=False)
    addr: Mapped[str] = mapped_column(String, default="")

    category: Mapped["Category"] = relationship()
```

---

## 7. Pydantic 스키마

> `schemas.py`에 아래 골격을 그대로 사용한다. 정규식은 8장 Validation
> 규칙과 동일해야 한다. `ContactUpdate`는 전 필드가 Optional이며, 라우터
> 단에서 `model_dump(exclude_unset=True)`로 부분 수정을 처리한다.

```python
# schemas.py
from typing import Optional
from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9]{4,20}$")
    password: str = Field(min_length=4, max_length=20)
    password_confirm: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=5)
    phone: str = Field(pattern=r"^010\d{8}$")
    addr: str = ""
    category_id: int


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=5)
    phone: Optional[str] = Field(default=None, pattern=r"^010\d{8}$")
    addr: Optional[str] = None
    category_id: Optional[int] = None


class ContactResponse(BaseModel):
    id: int
    name: str
    phone: str
    addr: str
    category_id: int
    category_name: str

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=10)


class CategoryResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}
```

---

## 8. Validation 규칙

| 항목 | 규칙 | 정규식 |
|---|---|---|
| username | 영문 소문자+숫자, 4~20자 | `^[a-z0-9]{4,20}$` |
| password | 4~20자 | - |
| name (연락처) | 1~5자 | - |
| phone | 010으로 시작, 총 11자 | `^010\d{8}$` |
| category name | 1~10자 | - |

---

## 9. API 명세

### 공통 규칙

- Base URL: `http://127.0.0.1:8000`
- 인증: 세션 쿠키(`session_id`, HttpOnly). 로그인 성공 시 `Set-Cookie` 발급
- Content-Type: `application/json`
- 오류 응답 형식: `{"detail": "사람이 읽을 수 있는 한국어 메시지"}` (422는 Pydantic 자동 응답이라 detail이 배열)
- 연락처·카테고리 API는 예외 없이 로그인 필수 (세션 없으면 401)

### 9-1. 인증 API

**POST /auth/signup** — 인증 불필요

| 항목 | 내용 |
|---|---|
| Request | `{"username":"happyday","password":"pass1234","password_confirm":"pass1234"}` |
| 처리 순서 | ① 형식 검증 ② 아이디 중복 확인 ③ Argon2 해시 ④ users INSERT ⑤ 기본 카테고리 3개(가족/친구/기타) 자동 생성(같은 트랜잭션) |
| 성공 | 201 — `{"id":1,"username":"happyday"}` |
| 실패 | 409 아이디 중복 / 422 형식 위반 |

**POST /auth/login** — 인증 불필요

| 항목 | 내용 |
|---|---|
| Request | `{"username":"happyday","password":"pass1234"}` |
| 처리 순서 | ① 사용자 조회 ② `verify_password` 대조 ③ `secrets.token_hex(32)`로 세션 발급 ④ sessions INSERT ⑤ Set-Cookie 포함 응답 |
| 성공 | 200 — `{"message":"로그인 성공"}` + Set-Cookie |
| 실패 | 401 — 아이디 존재 여부는 알리지 않는 동일 문구 |

**POST /auth/logout** — 인증 필요

| 항목 | 내용 |
|---|---|
| 처리 | sessions에서 해당 행 삭제 + 커밋 → 쿠키 만료 |
| 성공 | 200 — `{"message":"로그아웃 되었습니다"}` (이미 로그아웃 상태여도 동일) |

**GET /auth/me** — 인증 필요

| 항목 | 내용 |
|---|---|
| 용도 | 화면 로드 시 로그인 여부 판별 |
| 성공 | 200 — `{"id":1,"username":"happyday"}` |
| 실패 | 401 — 세션 없음/무효 |

### 9-2. 연락처 API (모두 로그인 필수)

**POST /contacts**

| 항목 | 내용 |
|---|---|
| Request | `{"name":"윤아","phone":"01012345678","addr":"서울시","category_id":2}` |
| 처리 순서 | ① 세션 확인 ② 형식 검증 ③ `category_id`가 내 카테고리인지 확인 ④ 내 연락처 중 전화번호 중복 확인 ⑤ `user_id` 붙여 INSERT + 커밋 |
| 성공 | 201 — 등록된 연락처 JSON(`category_name` 포함) |
| 실패 | 401 / 404(내 카테고리 아님·없음) / 409(전화번호 중복) / 422 |

**GET /contacts**

| 항목 | 내용 |
|---|---|
| Query | `name`(부분 일치 검색, 선택) · `category_id`(필터, 선택) |
| 처리 | 내(`user_id`) 연락처만 조회 |
| 성공 | 200 — `{"total":3,"items":[...]}` (검색 결과 0건도 200 + 빈 배열, 오류 아님) |

**PATCH /contacts/{id}** (부분 수정)

| 항목 | 내용 |
|---|---|
| Request | 바꿀 항목만 전송. 예: `{"addr":"제주시"}` |
| 처리 순서 | ① 세션 확인 ② `{id}`가 내 연락처인지 확인 ③ 보낸 항목만 형식 검증 후 갱신 ④ phone 변경 시 중복 확인 ⑤ category_id 변경 시 내 카테고리 확인 ⑥ 커밋 |
| 성공 | 200 — 수정 완료된 연락처 전체 JSON |
| 실패 | 401 / 404(없는 id·남의 연락처) / 409(전화번호 중복) / 422 |

**DELETE /contacts/{id}**

| 항목 | 내용 |
|---|---|
| 처리 순서 | ① 세션 확인 ② 내 연락처인지 확인 ③ DELETE + 커밋 |
| 성공 | 204 No Content |
| 실패 | 401 / 404 |

### 9-3. 카테고리 API (모두 로그인 필수)

| API | Request | 성공 | 실패 |
|---|---|---|---|
| GET /categories | - | 200, `[{"id":1,"name":"가족"},...]` | 401 |
| POST /categories | `{"name":"동호회"}` | 201, `{"id":4,"name":"동호회"}` | 401 / 409(이름 중복) / 422 |
| PATCH /categories/{id} | `{"name":"베프"}` | 200, 소속 연락처의 표시 이름도 즉시 반영 | 401 / 404 / 409(이름 중복) / 422 |
| DELETE /categories/{id} | - | 204 | 401 / 404 / **409(사용 중)** |

> **FR-12 핵심 규칙**: 삭제 요청 시 해당 카테고리를 사용 중인 연락처 수를
> 먼저 count로 확인한다. 1건이라도 있으면 `409`로 거부하고
> `"이 카테고리를 사용하는 연락처가 N건 있어 삭제할 수 없습니다."` 안내를
> 반환한다. FK 제약 위반이 500으로 노출되는 것을 막기 위한 처리다.

### 9-4. 엔드포인트 요약표

| 그룹 | 기능 | Method | URL | 인증 |
|---|---|---|---|---|
| 인증 | 회원가입 | POST | /auth/signup | 불필요 |
| 인증 | 로그인 | POST | /auth/login | 불필요 |
| 인증 | 로그아웃 | POST | /auth/logout | 필요 |
| 인증 | 내 정보 확인 | GET | /auth/me | 필요 |
| 연락처 | 추가 | POST | /contacts | 필요 |
| 연락처 | 목록/검색 | GET | /contacts | 필요 |
| 연락처 | 수정 | PATCH | /contacts/{id} | 필요 |
| 연락처 | 삭제 | DELETE | /contacts/{id} | 필요 |
| 카테고리 | 목록 | GET | /categories | 필요 |
| 카테고리 | 추가 | POST | /categories | 필요 |
| 카테고리 | 수정 | PATCH | /categories/{id} | 필요 |
| 카테고리 | 삭제 | DELETE | /categories/{id} | 필요 |
| 화면 | 웹 화면 제공 | GET | / | 불필요 |

---

## 10. 화면 설계

**로그인/회원가입 화면**: 아이디, 비밀번호, (회원가입 시) 비밀번호 확인,
로그인 버튼, 회원가입 버튼. 비밀번호 확인은 클라이언트 단에서만 일치
검사하고 서버로는 `password`만 전송한다.

```
┌───────────────────────────────┐
│        연락처 관리 서비스        │
│                                 │
│  아이디   [______________]     │
│  비밀번호  [______________]     │
│                                 │
│         [   로그인   ]          │
│                                 │
│  계정이 없으신가요? [회원가입]   │
├ ─ ─ ─ (회원가입 모드일 때만) ─ ─ ┤
│  비밀번호 확인 [______________] │
│         [   가입하기  ]         │
└───────────────────────────────┘
```

**관리 화면**: 상단 좌측에 서비스 타이틀, 우측에 `{아이디} 님` +
로그아웃 버튼. 본문에 연락처 등록 폼, 검색창, 연락처 목록(수정/삭제
버튼 포함), 카테고리 관리 영역.

```
┌───────────────────────────────────────────────┐
│ 연락처 관리 서비스        {아이디} 님  [로그아웃] │
├───────────────────────────────────────────────┤
│ [연락처 등록/수정 폼]                            │
│  이름[____]  전화번호[____]  주소[________]      │
│  카테고리[▼가족/친구/기타]        [ 추가 ]        │
├───────────────────────────────────────────────┤
│ 검색 [_____________________] [검색] [전체]        │
├───────────────────────────────────────────────┤
│ 총 N건                                           │
│ ┌─────┬───────────┬────────┬────────┬────┬────┐ │
│ │이름  │전화번호     │주소    │카테고리 │수정│삭제│ │
│ ├─────┼───────────┼────────┼────────┼────┼────┤ │
│ │윤아  │01012345678│서울시   │친구     │[수]│[삭]│ │
│ └─────┴───────────┴────────┴────────┴────┴────┘ │
├───────────────────────────────────────────────┤
│ 카테고리 관리                                     │
│  · 가족 [수정][삭제]  · 친구 [수정][삭제]          │
│  · 기타 [수정][삭제]                              │
│  새 카테고리 [____________] [ 추가 ]              │
└───────────────────────────────────────────────┘
```

화면 전이는 페이지 이동이 아니라 `GET /auth/me` 응답에 따라 같은 페이지
안에서 섹션을 보이거나 숨기는 방식이다.

```
GET / 접속
 └─▶ fetch("GET /auth/me")
      ├─ 200 (로그인 상태) ─▶ 관리 화면 표시
      └─ 401 (로그인 안 됨) ─▶ 로그인/회원가입 화면 표시
```

---

## 11. Router / CRUD 설계

### routers/auth.py
`signup()` · `login()` · `logout()` · `me()` · `get_current_user()` 의존성

### routers/contacts.py
`create()` · `read()` · `update()` · `delete()`

### routers/categories.py
`create()` · `read()` · `update()` · `delete()`

### crud.py 주요 함수

| 함수 | 역할 |
|---|---|
| `create_user(db, username, password)` | 중복 확인 → 해시 → INSERT → 기본 카테고리 3개 생성 |
| `authenticate_user(db, username, password)` | 사용자 조회 + 비밀번호 대조 |
| `create_login_session(db, user_id)` | 세션 발급 + INSERT |
| `delete_login_session(db, session_id)` | 세션 삭제 (로그아웃) |
| `list_contacts(db, user_id, name=None, category_id=None)` | 내 연락처 SELECT (+필터) |
| `get_my_contact(db, user_id, contact_id)` | `WHERE id=? AND user_id=?` — 데이터 격리의 핵심 |
| `create_contact(db, user_id, data)` | INSERT + 커밋 |
| `update_contact(db, contact, data)` | 부분 갱신(`exclude_unset`) + 커밋 |
| `delete_contact(db, contact)` | DELETE + 커밋 |
| `list_categories(db, user_id)` | 내 카테고리 SELECT |
| `create_category / update_category(db, ..., name)` | 이름 중복 확인 후 INSERT/UPDATE |
| `delete_category(db, category)` | DELETE |
| `count_contacts_in_category(db, user_id, category_id)` | 삭제 전 필수 호출, 1건 이상이면 409 |

> **데이터 격리 원칙**: 모든 조회 함수의 첫 번째 규칙은 조건에 `user_id`가
> 반드시 들어간다는 것이다. `get_my_contact`가 격리의 전부이며, 남의
> 연락처는 id가 맞아도 결과가 `None`이 되어 라우터가 자동으로 404를
> 응답한다.

### 11-1. 핵심 CRUD 함수 흐름도

분기(중복/실패 시 즉시 종료)가 있는 함수만 흐름도로 표현한다. 단순
SELECT/INSERT/DELETE 함수는 위 표의 설명으로 충분하다.

**create_user(db, username, password)**

```
SELECT username
   ↓
이미 존재? ──Yes──▶ raise Conflict409("아이디 중복")
   │No
hash_password(password)
   ↓
INSERT users(username, password_hash)
   ↓
INSERT categories × 3 ("가족","친구","기타", user_id=신규id)
   ↓
COMMIT
   ↓
Return User
```

**authenticate_user(db, username, password)**

```
SELECT user WHERE username=?
   ↓
존재? ──No──▶ Return None
   │Yes
verify_password(password, user.password_hash)
   ↓
일치? ──No──▶ Return None
   │Yes
Return User
```

**create_contact(db, user_id, data)**

```
SELECT category WHERE id=data.category_id AND user_id=user_id
   ↓
없음? ──Yes──▶ raise NotFound404("카테고리 없음")
   │No
SELECT contact WHERE user_id=user_id AND phone=data.phone
   ↓
있음? ──Yes──▶ raise Conflict409("전화번호 중복")
   │No
INSERT contacts(user_id, category_id, name, phone, addr)
   ↓
COMMIT → refresh
   ↓
Return Contact (+ category.name JOIN)
```

**delete_category(db, user_id, category_id)**

```
SELECT category WHERE id=category_id AND user_id=user_id
   ↓
없음? ──Yes──▶ raise NotFound404
   │No
COUNT contacts WHERE category_id=category_id
   ↓
count > 0 ? ──Yes──▶ raise Conflict409(f"연락처 {count}건 있어 삭제 불가")
   │No
DELETE category
   ↓
COMMIT
```

---

## 12. 인증 설계

- Session Cookie, HttpOnly
- `sessions` 테이블에 저장 (서버 재시작 후에도 로그인 유지)
- MVP 범위에서는 세션 만료 없음(로그아웃 전까지 유지). 확장 시
  `sessions.expires_at` 컬럼 추가 검토

---

## 13. Workflow

**회원가입**: 입력 → Validation → 중복확인 → Hash → User 생성 → 기본
카테고리 생성 → Commit → 201

**로그인**: 입력 → Validation → 사용자조회 → 비밀번호검증 → Session
생성 → Cookie 발급

**연락처 등록**: Session 확인 → Validation → Category 소유 확인 →
전화번호 중복확인 → INSERT → Commit

**카테고리 삭제**: Session 확인 → 사용 중 확인(count) → 삭제 또는 409

**화면 초기화**: 페이지 로드 → `GET /auth/me` → (200) `GET /categories`
→ `GET /contacts` → 버튼 이벤트 연결. 카테고리 목록을 먼저 불러오는
이유는 연락처 등록 폼의 드롭다운이 카테고리 데이터에 의존하기 때문이다.

---

## 14. 예외 처리

### 14-1. 상태 코드 매트릭스

| 코드 | 의미 | 발생 상황 |
|---|---|---|
| 401 | 인증 실패 | 세션 쿠키 없음/무효, 로그인 시 아이디·비밀번호 불일치 |
| 404 | 대상 없음 | 없는 id, 남의 데이터 id, 없는/남의 카테고리 지정 |
| 409 | 규칙 충돌 | 아이디 중복, 전화번호 중복, 카테고리 이름 중복, 사용 중 카테고리 삭제 |
| 422 | 형식 위반 | Pydantic 자동 검증 실패(길이·패턴·타입 오류) |
| 500 | 서버 오류 | 발생하면 안 됨 (발생 시 예외 처리 누락으로 간주) |

### 14-2. 반드시 지킬 두 가지 원칙

1. 남의 데이터는 403이 아니라 **404**로 응답한다 — 조회 조건에 `user_id`를
   항상 포함하면 남의 데이터는 조회 자체가 안 되어 자연스럽게 404가 된다.
2. 모든 오류 응답은 `{"detail": "..."}` 형태로 통일한다 — 화면은 어떤
   오류든 `detail`만 꺼내 보여주면 되므로 오류 표시 코드가 한 벌로 끝난다.

### 14-3. 추가로 대비해야 할 엣지 케이스

| 구분 | 상황 | 권장 처리 |
|---|---|---|
| 동시성 | 같은 연락처를 두 탭에서 거의 동시에 수정/삭제 | 대상 재조회 시 이미 없으면 404 (삭제 로직과 동일 케이스) |
| 동시성 | 같은 전화번호로 거의 동시에 두 번 POST(더블클릭) | 화면에서 이중 제출 방지(버튼 비활성화) + 서버 UNIQUE 제약으로 두 번째 요청은 409 |
| 입력 | PATCH 본문이 완전히 빈 객체 `{}` | 오류 아님. 변경 없이 200 + 기존 값 반환 (`exclude_unset`이 자연히 처리) |
| 입력 | 존재하지만 남의 소유인 `category_id` 지정 | 없는 카테고리와 동일하게 404 (존재 여부를 숨기는 원칙과 일관) |
| 레이스 컨디션 | 카테고리 삭제 count 확인 직후 다른 요청이 연락처를 추가 | 동일 트랜잭션 내에서 count와 DELETE를 함께 처리, 또는 FK `ON DELETE RESTRICT`로 DB 레벨 이중 방어 |
| 리소스 | PostgreSQL 커넥션 풀 고갈 | `get_db()`의 `finally`에서 세션을 반드시 반납해 누수 방지 |
| 인프라 | DB 컨테이너가 꺼져 있음 | 요청 시 연결 오류 발생 — 실행 전 Docker 기동 확인 |

---

## 15. 테스트 시나리오

모든 시나리오는 계정 2개(A, B)를 만들어 데이터 격리를 함께 검증한다.

### 15-1. 인증

| TC | 시나리오 | 기대 결과 |
|---|---|---|
| TC-01 | 정상 회원가입 | 201, 기본 카테고리 3개 자동 생성 |
| TC-02 | 아이디 중복 가입 | 409 |
| TC-03 | 아이디/비밀번호 형식 위반 | 422 |
| TC-04 | 정상 로그인 | 200 + Set-Cookie |
| TC-05 | 틀린 비밀번호 / 존재하지 않는 아이디 | 401, 동일한 문구(구분 불가) |
| TC-06 | 로그인 없이 관리 화면 접속 | 로그인 화면 노출, 관리 화면 비노출 |
| TC-07 | 정상 로그아웃 후 같은 쿠키로 보호 API 호출 | 401 |
| TC-08 | 서버 재시작 후 재접속 | 로그인 유지, 데이터 그대로 |

### 15-2. 연락처

| TC | 시나리오 | 기대 결과 |
|---|---|---|
| TC-09 | 정상 등록 | 201, total +1 |
| TC-10 | 이름/전화번호 형식 위반 | 422 |
| TC-11 | 없는/남의 category_id 지정 | 404 |
| TC-12 | 전화번호 중복(내 연락처 내) | 409 |
| TC-13 | 동일 전화번호를 다른 사용자가 등록 | 201 성공 (사용자별 독립 UNIQUE) |
| TC-14 | 이름 검색(동명이인 2건) | 200, 2건 모두 각기 다른 id로 반환 |
| TC-15 | 검색 결과 0건 | 200, `{"total":0,"items":[]}` (오류 아님) |
| TC-16 | B 계정으로 A의 연락처 목록·직접 접근 시도 | 목록에 없음 / 직접 접근 시 404 |
| TC-17 | 부분 수정(주소만 변경) | 200, 나머지 항목은 그대로 |
| TC-18 | 남의 연락처 id로 수정/삭제 | 404 (403 아님) |

### 15-3. 카테고리

| TC | 시나리오 | 기대 결과 |
|---|---|---|
| TC-19 | 가입 직후 기본 카테고리 확인 | 200, [가족, 친구, 기타] 3건 |
| TC-20 | 정상 추가 / 이름 중복 | 201 / 409 |
| TC-21 | 카테고리 신설이 다른 계정에 노출되지 않음 | B의 목록에 나타나지 않음 |
| TC-22 | 이름 변경 시 소속 연락처의 표시명 연동 | 200, 연락처 표시명도 즉시 변경 |
| TC-23 | 미사용 카테고리 삭제 | 204 |
| TC-24 | 사용 중 카테고리 삭제 시도 | 409, "N건 있어 삭제할 수 없습니다" 안내 |

### 15-4. 통합

| TC | 시나리오 | 기대 결과 |
|---|---|---|
| TC-25 | 가입→로그인→등록→수정→삭제→로그아웃 전체 흐름 | 각 단계 기대 상태 코드 모두 통과 |
| TC-26 | 계정 A·B 완전 격리 검증 | 목록·검색·직접 id 접근 어디서도 상대 데이터 노출 없음 |
| TC-27 | 모든 실패 케이스 재실행 | 500 발생 없이 401/404/409/422 중 하나로만 응답 |
| TC-28 | 이중 제출 방지(빠른 두 번 클릭) | 두 번째 클릭이 차단되거나 서버가 409로 안전 처리 |

---

## 16. 구현 순서

1. DB 연결(`database.py`)
2. Models
3. Schemas
4. Security(해싱)
5. CRUD
6. Router
7. HTML
8. JavaScript
9. 통합 테스트

---

## 17. 완료 기준

- 13개 엔드포인트(FR-01~FR-13) 모두 정상 동작
- Swagger(`/docs`) 정상
- HTML 화면에서 회원가입~로그아웃 전체 흐름 정상
- 연락처·카테고리 CRUD 완료
- PostgreSQL에 데이터 영속 저장 확인 (서버 재시작 후에도 유지)
- 15장 테스트 시나리오 전체 통과
- 어떤 요청에도 500이 발생하지 않음

---

## 18. AI 구현 지침

AI는 다음 원칙을 반드시 따른다.

1. Router에는 SQL을 작성하지 않는다.
2. CRUD만 DB 접근을 수행한다.
3. 모든 쓰기 작업은 Commit/Rollback 처리한다.
4. 모든 조회는 `user_id`를 조건에 포함한다.
5. Pydantic Validation과 Business Validation을 분리한다.
6. Password는 Argon2 Hash만 저장한다.
7. Response는 JSON으로 통일하고, 오류는 `{"detail": "..."}` 형태로 통일한다.
8. 상태 코드는 REST 규칙을 따르며, 남의 데이터는 403이 아닌 404로 응답한다.
9. 화면은 Fetch API를 사용한다.
10. 회원가입 시 User INSERT와 기본 카테고리 3개 INSERT는 같은 트랜잭션으로 묶는다.
11. 카테고리 삭제 전에는 반드시 소속 연락처 수를 확인한다.
12. 코드 생성 시 본 문서를 최우선 명세로 사용하고, 명시되지 않은 부분은 14장의 엣지 케이스 처리 원칙을 따른다.
13. 6장(모델)·7장(스키마)의 코드 골격은 임의로 문법을 바꾸지 않고 그대로 사용하며, 4-2장 Sequence Diagram과 11-1장 흐름도에 표시된 분기·종료 지점을 누락하지 않는다.
14. 부록 A에 명시된 설정값(쿠키 옵션, 해싱 파라미터, CORS 등)을 AI가 임의로 다른 값으로 바꾸지 않는다.

---

## 부록 A. 로컬 개발 환경 기준 설정값

> 이전 버전까지는 "AI가 합리적으로 판단"하도록 열어뒀던 항목들이다.
> 판단 편차를 없애기 위해 로컬 개발/학습 환경 기준으로 기본값을 확정한다.
> 운영 배포 시에는 별도 검토가 필요하다는 점만 유의한다.

### A-1. 세션 쿠키 옵션

로그인 성공 시 `Set-Cookie`에 아래 옵션을 사용한다.

| 옵션 | 값 | 이유 |
|---|---|---|
| `httponly` | `True` | JS에서 쿠키 탈취 방지 (12장 원칙과 동일) |
| `secure` | `False` | 로컬 개발은 `http://127.0.0.1`이라 HTTPS가 아님. 운영 배포 시 `True`로 전환 |
| `samesite` | `"lax"` | 같은 오리진에서만 쓰는 MVP라 CSRF 위험이 낮고, 일반 링크 이동 시에도 쿠키가 유지됨 |
| `max_age` | 미설정(세션 쿠키) | 12장 원칙대로 "로그아웃 전까지 유지" — 브라우저 종료와 무관하게 서버의 `sessions` 테이블 존재 여부로 유효성을 판단하므로 클라이언트 만료 시간은 두지 않는다 |

```python
response.set_cookie(
    key="session_id",
    value=session_id,
    httponly=True,
    secure=False,      # 운영 배포(HTTPS) 시 True로 변경
    samesite="lax",
)
```

로그아웃 시에는 `response.delete_cookie("session_id")`로 만료 처리한다.

### A-2. Argon2 해싱 파라미터

`pwdlib[argon2]`의 기본 파라미터를 그대로 사용한다(별도 튜닝 없음).
로컬 학습 환경에서는 기본값으로 충분하며, 임의로 `time_cost`/`memory_cost`를
낮추지 않는다(보안 저하 방지).

```python
# security.py
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()

def hash_password(raw: str) -> str:
    return password_hash.hash(raw)

def verify_password(raw: str, hashed: str) -> bool:
    return password_hash.verify(raw, hashed)
```

### A-3. 비밀번호 정책

8장 Validation 규칙의 "4~20자" 외에 추가 복잡도 규칙(대소문자/특수문자
포함 의무)은 **적용하지 않는다**. 학습용 MVP 범위이므로 길이 제약만
유지하고, 문자 종류 제한은 두지 않는다(단, `username`처럼 소문자+숫자로
제한하지도 않음 — 비밀번호는 모든 문자 허용).

### A-4. CORS 설정

프론트엔드(`static/index.html`)와 백엔드가 동일 오리진(`GET /`)에서
서빙되므로 **CORS 미들웨어를 추가하지 않는다**. 별도 포트의 프론트
개발 서버(예: Vite `localhost:5173`)에서 API를 호출하는 구성으로
바뀔 경우에만 `CORSMiddleware`를 도입한다.

### A-5. main.py 기본 설정

```python
# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="연락처 관리 웹 서비스", version="1.0.0")
# /docs, /redoc, /openapi.json은 기본값 그대로 노출 (학습용이므로 비공개 처리 안 함)

app.include_router(auth_router)
app.include_router(contacts_router)
app.include_router(categories_router)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")
```

### A-6. 테스트 프레임워크

`pytest` + FastAPI `TestClient`(`httpx` 기반)를 사용한다. 15장의
TC-01~TC-28을 각각 하나의 테스트 함수로 매핑하는 것을 권장하며,
계정 A/B는 매 테스트마다 고유한 `username`으로 생성해 테스트 간
데이터가 섞이지 않게 한다.

```python
# 예시
def test_signup_creates_default_categories(client):
    res = client.post("/auth/signup", json={
        "username": "testuser1", "password": "pass1234",
        "password_confirm": "pass1234",
    })
    assert res.status_code == 201
```

### A-7. 환경 변수 / DB 접속 정보

`.env` + `python-dotenv`(또는 `pydantic-settings`)로 관리하며,
`DATABASE_URL` 하나만 필수로 둔다. 하드코딩하지 않는다.

```
# .env 예시
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/contact_db
```

### A-8. 페이지네이션 (범위 밖 — 명시적 보류)

`GET /contacts`는 MVP 범위에서 페이지네이션을 적용하지 않고 전체 목록을
반환한다. 데이터 양이 많아지는 시나리오는 본 프로젝트 범위 밖으로
명시적으로 보류하며, 확장 시 `limit`/`offset` 쿼리 파라미터 추가를
검토한다.
