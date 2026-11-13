# Final\_Project\_API 명세서

Oct 29, 2026 · @혜현

**v1.4 (개인용 개정본)** · 2026-11-13 · 7장 이탈: 코딩테스트 첫 화면 이탈에도 코딩 시계를 멈추지 않음, 경고 창 확인 때 '이탈 후 돌아옴 · 이탈 시간' 기록 (CONFLICTS C-18, 사용자 결정 2026-11-13). 기준 문서 PRD v1.9 · TRD v1.8 · 화면정의서 v0.9

v1.3 (개인용 개정본) · 2026-11-10 · 팀 원본 아님. 2026-11-06·11-09·11-10 검토 보정을 반영했다(자세한 것은 문서 끝 보정 절): 코드 대조로 고친 곳(E7~E18), 논의사항 정리, AI 질문 품질·질문 적용 범위·질문 후보·AI 공고 초안 그래프(CONFLICTS C-13~C-17). 변경 기록은 12장과 문서 끝 보정 절 참고

v1.2 (개인용 개정본) · 2026-11-03 · 변경 기록은 12장 참고

v1.1 · 2026-10-29 · 리뷰 의견과 화면정의서 v0.4 반영(바뀐 점은 12장 A-02\~A-19)

v1.0 · 2026-10-29 · 최초 작성

## 1. 개요

이 문서는 프런트엔드(Next.js)와 백엔드(FastAPI)가 주고받는 REST API 72개(이 중 5개는 현재 구현 없음: 구현 범위 밖 3개, 마이페이지 이력서 올리기 2개)와 면접 실시간 메시지 20종, 답변 음성 이진 프레임을 한곳에 정리한 명세다. 경로·요청·응답·오류를 여기서 맞추고, 칸 하나하나의 DB 정의는 테이블 정의서를 따른다.

| 항목 | 내용 |
| --- | --- |
| 기준 문서 | TRD v1.8(5장·4-3·14장), PRD v1.9, 화면정의서 v0.9(§1.1 결정 D-01\~D-10, §12 추가 API), 테이블 정의서 v1.2, 기술 아키텍처 v1.3(ADR-01·04·05) |
| 화면 주소 | `http://127.0.0.1:8080` — 같은 PC 브라우저에서만 접속 |
| REST 기본 주소 | `http://127.0.0.1:8080/api` — frontend가 Next.js rewrites(`/api/*` → api)로 api(8000)에 넘긴다. 미디어 파일도 `/api/media/…` · `/api/admin/media/…`로 같은 rewrites를 지난다(2-6). 이 문서의 경로는 `/api`를 뺀 값 |
| 실시간 주소 | WebSocket `ws://127.0.0.1:8000/ws/interview/{session_id}` (답변 음성도 이 연결의 이진 메시지로 보낸다. WebRTC·UDP 포트는 쓰지 않는다, CONFLICTS V4) |
| 인증 | 로그인 쿠키 `huge_session`(HttpOnly, SameSite=Lax). 화면과 API가 같은 주소라 쿠키가 그대로 쓰인다 |
| 표기 | 🔒 지원자 로그인 · 🛡 관리자(`require_admin`) · 🌐 로그인 불필요 · ➕ TRD 5-1에 없어 이 문서에서 추가한 API |

➕ 표시 API는 화면정의서 §12에서 필요하다고 정리한 것을 TRD 규칙에 맞춰 경로를 정한 것이다. TRD 다음 개정 때 5-1에 옮겨 적어야 한다.

## 2. 공통 규칙

모든 API는 JSON을 주고받고, 오류는 `{"code", "message"}` 한 가지 모양이다(TRD 4-3). 화면은 `code`로 안내 문구를 고른다.

### 2-1. 데이터 형식

| 규칙 | 내용 |
| --- | --- |
| 형식 정의 | 요청·응답·WebSocket 메시지 모두 Pydantic 모델. 모델에 없는 칸이 오면 거절(`extra="forbid"`, 422). 예외: sendBeacon 수신(POST /interview/{sid}/events)은 본문을 직접 풀어 느슨하게 받는다(6장) |
| id | UUID 문자열 |
| 시각 | 한국 시간이 붙은 ISO 8601 — `2026-11-03T10:00:00+09:00` |
| 점수 | 소수 오차를 막기 위해 문자열 — `"70.15"` (소수점 둘째 자리) |
| 목록 | `?page=1&size=20`, 응답은 `{"items": [...], "total": 0, "page": 1, "size": 20}` |
| 파일 업로드 | `multipart/form-data`. 서버 보호 한도 `upload_max_mb`(50MB)는 화면에 표시하지 않는다 |
| 개인정보 | 이름·연락처는 화면 응답에만 넣고, LLM 입력과 Redis 메시지에는 넣지 않는다 |

### 2-2. 인증·권한

- **로그인 유지**: 쿠키 세션. 마지막 요청 후 2시간이 지나면 만료되고, 인증이 필요한 요청과 WebSocket 연결을 할 때마다 늘린다(녹화 조각 올리기·코딩 자동 저장도 요청이라 면접 중에 늘어난다). WebSocket heartbeat 만으로는 늘어나지 않는다. 화면 주소가 `https://`일 때만 Secure 쿠키를 쓴다(지금은 http 실행이라 꺼짐).
- **관리자 API**(`/admin/*`): `require_admin`. 지원자가 부르면 403.
- **지원자 API**: `require_owner`. 모든 조회에 `user_id = 로그인한 사람` 조건을 넣는다. 다른 사람 데이터 번호로 부르면 있는지도 알 수 없게 404.
- **면접 API**(`/interview/{sid}/*`, `/coding/{sid}/*`, WebSocket): 면접 시작 때 받은 세션 토큰(`sid`)과 로그인 쿠키를 함께 확인한다. WebSocket은 `Origin` 헤더가 `http://127.0.0.1:8080`이 아니면 끊는다.
- **관리자 초기 비밀번호**: 바꾸기 전에는 `/auth/password-change`, `/auth/logout`, `/auth/me` 말고는 403 `PASSWORD_CHANGE_REQUIRED`.
- **결과·결정**: 관리자 API에서도 읽기만 된다. 바꿀 수 있는 것은 메모·설정·다시 돌리기뿐이고, 정해진 판정을 고치는 주소는 없다(AC-14). 자동 채점을 끝내지 못한 건에 결과를 처음 정하는 `POST /admin/analysis/{aid}/decision` 만 예외다.

### 2-3. HTTP 상태 코드

| 코드 | 뜻 | 주로 쓰는 곳 |
| --- | --- | --- |
| 200 · 201 · 202 · 204 | 성공 · 만듦 · 뒤에서 처리 시작 · 내용 없음 | 202는 api 안 백그라운드 작업(이력서 추출·AI 초안) 또는 worker가 이어서 하는 일(재처리) |
| 400 | 요청 값이 규칙에 맞지 않음 | 비밀번호 규칙, 가중치 합계 |
| 401 | 로그인 필요 | 쿠키 없음·만료 |
| 403 | 권한 없음 | 지원자가 `/admin` 호출, 이메일 미인증 |
| 404 | 없음(또는 보여 줄 수 없음) | 남의 데이터, 공개 전 결과 |
| 409 | 지금 상태에서는 안 됨 | 잠긴 기준 수정, 마감 뒤 시작·이어가기, 두 번째 응시 |
| 413 | 서버 보호 한도 초과 | 이력서 파일 > `upload_max_mb` |
| 422 | 형식 오류 | 필수 칸 빠짐, 모델에 없는 칸 |
| 429 | 요청 제한 | 같은 IP 에서 로그인 5번 실패(`LOGIN_BLOCKED`) |
| 429 | 자리가 꽉 참 | 면접 시작(응시 횟수 안 씀) |
| 500 · 503 | 서버·AI 서버 오류 | 면접 중이면 장애 후보(TRD 7-2). 503은 녹화 저장소 장애(`STORAGE_UNAVAILABLE`), 코드 실행 상자 장애(`SANDBOX_BUSY`·`SANDBOX_DOWN`)에도 씀 |
| 307 | 주소 이동 | localhost:8080 → 127.0.0.1:8080 (2-5) |

그 밖에 410(보관 기간이 지난 녹화)과 502(Open API가 답하지 않음 — 공고 불러오기는 미구현이라 현재 나오지 않음)도 정해 두었다. 미디어 파일은 Range 요청을 받지 않고 전체를 보낸다(2-6). 오류 응답 예:

```json
{ "code": "CRITERIA_LOCKED", "message": "첫 응시가 시작되어 평가 기준을 바꿀 수 없습니다." }
```

### 2-4. 응시 상태 값

여러 API가 같이 쓰는 `attempt_status` 값이다. '대기'는 저장하는 상태가 아니라 429 안내 화면일 뿐이다(TRD 7-1).

| 값 | 화면 표시 |
| --- | --- |
| `drafting` | 작성 중 (화면정의서 G-01) |
| `ready` | 면접 준비 중 (U3) |
| `interviewing` | 면접 진행 중 |
| `coding` | 코딩테스트 진행 중 |
| `interrupted` | 장애 중단 |
| `completed` | 응시 완료 |
| `ended` | 응시 종료 (창 닫기·권한 끄기·이어가기 횟수 초과) |
| `ended_closed` | 응시 종료(마감) |
| `cancelled` | 응시 취소 (화면 이탈 2번) |
| `not_taken_closed` | 미응시(마감) |

분석 상태 `analysis_status`: `pending`(분석 대기) · `running`(분석 중) · `decided`(확정) · `needs_review`(평가 지연). 공개 상태 `release_status`: `scheduled` · `delayed`(채점이 늦어 다음 날 10:00 공개) · `released` · `purged`.

### 2-5. 접속 주소와 프록시 주의점

로그인 쿠키는 포트가 아니라 호스트 단위로 붙는다. 8080에서 받은 쿠키가 같은 호스트의 8000(WebSocket)에 붙는 것에 기대므로, 호스트를 하나로 고정한다.

- **호스트 고정**: 화면은 `127.0.0.1`로만 쓴다. `localhost:8080`으로 들어오면 frontend(`proxy.ts`)가 같은 경로의 `127.0.0.1:8080`으로 리다이렉트(307)한다. 다른 호스트로 열면 WebSocket에 쿠키가 안 붙고 `Origin` 검사에도 걸려 면접에 들어갈 수 없다.
- **Origin 허용 목록**: api는 `http://127.0.0.1:8080` 하나만 받는다. `ws_url`도 이 호스트로만 만든다.
- **rewrites 대상**: `/api/*` → api(8000)의 `/*` 하나뿐이다. 미디어도 `/api/media/…` · `/api/admin/media/…`로 이 규칙을 지난다. WebSocket은 rewrites를 거치지 않고 8000에 바로 붙는다.
- **본문 크기 제한**: Next.js 15.5 이후 미들웨어(16에서는 `proxy.ts`)가 걸린 경로는 요청 본문을 기본 10MB까지만 넘긴다. 이력서는 서버 한도 50MB(`upload_max_mb`)까지 받아야 하므로, `proxy.ts`의 matcher에서 `api/`를 뺐다(구현됨, 12장 A-16). 본문 50MB가 실제로 넘어가는지는 실측하지 않았다.
- **응답 시간 제한(확인 필요)**: rewrites 프록시에도 기본 응답 시간 제한이 있다. `POST /coding/{sid}/run`(최대 10초 + 상자 만들기)·`POST /admin/postings/import`처럼 오래 걸리는 요청이 여기에 걸리지 않는지 실측한다.

### 2-6. 미디어 파일

지원자(질문 음성)와 관리자(답변 음성·녹화)가 쓰는 파일 API라 여기 둔다. 세 가지가 있고 모두 권한을 확인한 뒤 api가 직접 전달한다.

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `GET /media/questions/{question_id}` ➕ | 🔒 | 질문 음성(`audio/wav`). `question_id`는 질문 줄 번호(정수)로, WebSocket `question`의 `audio_url`에 들어 있다. 아직 내지 않은 질문은 404 | S-A09 |
| `GET /admin/media/answers/{answer_id}` ➕ | 🛡 | 답변 음성(`audio/wav`). 열 때마다 감사 로그 `answer.listen` | S-R06 |
| `GET /admin/media/recordings/{application_id}/{segment_no}` ➕ | 🛡 | 녹화(`video/webm`). 열 때마다 감사 로그 `recording.play` | S-R06 |

각 주소 앞에 `/api`를 붙여 부른다(예: `/api/media/questions/812`). 객체 저장소는 포트를 열지 않으므로(TRD 2-3) 사전 서명 주소는 브라우저가 열 수 없어 쓰지 않는다(기술 아키텍처 ADR-05). 저장소는 RustFS이고 파일은 앱에서 AES-GCM으로 암호화해 둔다(CONFLICTS B5).

| 종류 | 볼 수 있는 사람 | 보관 |
| --- | --- | --- |
| 질문 음성 | 그 면접의 지원자 | 응시 데이터와 같이 |
| 답변 음성 | 관리자 | 공개 + 7일 |
| 녹화 | 관리자 | 응시 끝 + 3일 (재생은 기한이 지나면 바로 410, 파일은 매시 30분 작업이 지움) |

- **Range 없음**: 세 주소 모두 `Range` 요청을 받지 않고 처음부터 전체를 보낸다(206 없음). 녹화(MediaRecorder WebM)는 탐색 정보가 없어 Range를 줘도 건너뛰기가 잘 안 된다(CONFLICTS R2). 하이라이트 구간(`start_ms`)으로 이동하는 일은 화면이 내려받은 음성의 재생 위치를 옮겨서 한다. 녹화에는 하이라이트가 없다. 〔답변 음성의 Range 여부는 논의사항 #2〕
- **녹화 이어 보내기(CONFLICTS R1)**: 녹화는 조각마다 객체 하나로 저장되고, 재생할 때 서버가 조각을 순서대로 이어서 보낸다. 받는 쪽에서는 구간(`segment_no`)마다 파일 하나와 같다.
- 권한이 없거나 남의 파일이면 404, 녹화 보관 기간이 지났으면 410 `MEDIA_EXPIRED`다.
- `GET /admin/applicants/{aid}`의 `questions[].answer`·`highlights[]`·`recordings[]`에는 이 주소(`media_url`, `/api`로 시작)를 넣어 준다.

## 3. 인증·계정 API

가입은 지원자만 하고, 관리자 계정 1개는 설치할 때 만든다(N8). 비밀번호 규칙은 가입·변경·재설정 세 API가 같은 함수로 확인한다.

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `POST /auth/signup` | 🌐 | 지원자 가입 | S-C02 |
| `POST /auth/login` | 🌐 | 로그인, 쿠키 발급 | S-C01 |
| `POST /auth/logout` ➕ | 🔒🛡 | 로그아웃, 쿠키 삭제 | 공통 머리글 |
| `GET /auth/me` ➕ | 🔒🛡 | 지금 로그인한 사람·역할 (라우트 가드용) | 전체 |
| `POST /auth/password-reset` | 🌐 | 재설정 링크 메일 요청(30분 유효, 같은 주소로 1분에 한 통) | S-C03 ① |
| `POST /auth/password-reset/confirm` ➕ | 🌐 | 링크 토큰으로 새 비밀번호 저장 | S-C03 ② |
| `POST /auth/password-change` ➕ | 🔒🛡 | 현재 비밀번호로 확인 후 변경 (관리자 초기 변경 포함) | S-C04, S-A13 |
| `PATCH /me` ➕ | 🔒 | 이름·휴대전화 수정 (이메일은 못 바꿈) | S-A13 계정 |
| `POST /me/withdraw` ➕ | 🔒 | 탈퇴: 진행 중 응시 취소, 응시 데이터·계정 즉시 삭제 | S-A13 계정 |
| `POST /auth/email-verification` ➕ | 🔒 | 인증 메일 다시 보내기(1분에 1번). **현재 구현 범위 밖(미구현)**, 나중에 붙이는 기능 | 추후 |
| `POST /auth/email-verification/confirm` ➕ | 🌐 | 24시간 토큰으로 인증, `email_verified_at` 기록. **현재 구현 범위 밖(미구현)** (칸만 있음) | 추후 |

### POST /auth/signup

요청

```json
{
  "name": "홍길동",
  "email": "hong@example.com",
  "password": "Hire#2026ai",
  "phone": "010-1234-5678",
  "agreements": { "age_14_plus": true, "terms": true, "privacy": true }
}
```

응답 201 — `{ "user_id": "9f1c…", "email": "hong@example.com" }`. 가입만 하고 로그인은 따로 한다(화면은 S-C01로 이동).

| 오류 | code | 조건 |
| --- | --- | --- |
| 400 | `PASSWORD_POLICY` | 8\~64자, 영문·숫자·특수문자 각 1자, 이메일 아이디 포함 금지, 같은 문자 4번 연속 금지 중 하나라도 어김. `message`에 어긴 규칙 |
| 400 | `AGREEMENT_REQUIRED` | 필수 동의 3개 중 빠진 것 |
| 409 | `EMAIL_TAKEN` | 이미 가입된 이메일 |

### POST /auth/login

요청 — `{ "email": "hong@example.com", "password": "…", "next": "/apply/3a7e…" }`

응답 200 (`Set-Cookie: huge_session=…; HttpOnly; SameSite=Lax`)

```json
{
  "user_id": "9f1c…",
  "role": "applicant",
  "password_change_required": false,
  "redirect": "/apply/3a7e…"
}
```

- `role`: `applicant` · `admin`. 관리자 첫 로그인이면 `password_change_required: true`, `redirect: "/password/change"`.
- `next`는 **화면 경로**만 받는다(API 경로는 받지 않음, CONFLICTS A2). 같은 사이트 안의 `/jobs` · `/apply/` · `/exam/` · `/mypage`로 시작할 때만 쓰고, `//` · `/\` · `://`가 들어 있거나 다른 도메인이거나 위 목록에 없으면 버리고 `/jobs`로 보낸다(TRD 11장). 관리자는 `next`와 상관없이 `/admin/postings`로 보낸다.
- 오류: 401 `INVALID_CREDENTIALS`(이메일·비밀번호 중 무엇이 틀렸는지 알리지 않음. 관리자 계정이 잠겨 있어도 같은 응답) · 429 `LOGIN_BLOCKED`(같은 IP 에서 1시간 안에 5번 실패, `message`에 풀리는 시각과 문의 코드. 맞는 비밀번호도 막히며 관리자만 통과).

### POST /auth/password-reset · /confirm

- 요청: `{ "email": "…" }` → 항상 202 `{ "status": "accepted" }`. 가입 여부를 드러내지 않는다. 가입 여부 확인과 메일 넣기는 **응답을 보낸 뒤** 처리해서 응답 시간으로도 알 수 없다(CONFLICTS P2).
- 같은 주소로는 1분에 한 통만 보낸다(그 안의 요청도 202이지만 메일은 가지 않는다). 새 링크를 보내면 이전 링크는 못 쓴다. 링크의 토큰은 DB·알림 표에 남기지 않고 메일 작업으로만 넘긴다(CONFLICTS P1).
- 확정: `{ "token": "…", "new_password": "…" }` → 204. 토큰은 한 번만 쓰고, 성공하면 모든 기기에서 로그아웃된다. 오류 400 `TOKEN_EXPIRED`(30분 지남·이미 씀) · 400 `PASSWORD_POLICY`(이때 토큰은 그대로 남겨 다시 입력할 수 있다). 로그인 잠금(5회)은 풀어 주지 않는다(CONFLICTS P1).

### POST /auth/password-change

요청 — `{ "current_password": "…", "new_password": "…" }` → 204. 오류 400 `WRONG_PASSWORD` · 400 `PASSWORD_POLICY` · 400 `SAME_AS_OLD`. 바꾸면 관리자의 `password_change_required`가 풀리고, 지금 쓰는 기기 말고 다른 기기의 로그인은 끊긴다.

### PATCH /me · POST /me/withdraw

- `PATCH /me` 요청: `{ "name": "홍길동", "phone": "010-1234-5678" }`(바꿀 칸만) → 200 회원 정보.
- `POST /me/withdraw` 요청: `{ "password": "…", "confirm_text": "탈퇴" }` → 204, 쿠키 삭제. 진행 중 면접이 있으면 자리를 돌려주고 WebSocket으로 `terminate`(`withdrawn`)를 보낸 뒤 지운다(CONFLICTS W5). 지운 기록은 `deletion_logs`에 남고, 같은 이메일로 다시 가입할 수 있다.
- 오류(CONFLICTS W4): 400 `WRONG_PASSWORD`(비밀번호 틀림) · 400 `CONFIRM_TEXT`(확인란이 '탈퇴'가 아님) · 403 `FORBIDDEN`(관리자는 탈퇴할 수 없음).
- 철회·탈퇴 때 응시가 끝난 건(완료·종료·취소·마감 종료·미응시 마감)만 익명 통계(`stats_archive`)에 더하고, 작성 중·면접 준비 중·진행 중·장애 중단 건은 더하지 않는다(CONFLICTS W1).

탈퇴는 `DELETE`가 아니라 `POST`로 둔다. `DELETE` 요청의 본문은 뜻이 정해져 있지 않아 중간 프록시가 버릴 수 있는데, 탈퇴에는 비밀번호와 확인 문구를 본문으로 받아야 하기 때문이다. 화면정의서 §12 #4의 `DELETE /me`는 이 경로로 바꾼다.

## 4. 공고 API

공개 조회는 `/postings`, 관리는 모두 `/admin/postings` 아래에 둔다. TRD 5-1은 관리용을 `POST /postings`처럼 적고 "/admin 아래"라고 덧붙였는데, 이 문서는 주소에 `/admin`을 붙이는 쪽으로 맞춘다.

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `GET /postings` | 🌐 | 접수 중 공고 목록(게시 중이고 접수 기간 안). 로그인했으면 내 지원 상태도 | S-A01 |
| `GET /postings/{id}` | 🌐 | 공고 상세. 로그인했으면 내 지원 상태도. 임시저장 공고는 404 | S-A02 |
| `GET /job-codes` ➕ | 🌐 | 직무 목록(준비 중 직무 포함) | S-A01, S-R03 |
| `GET /admin/postings?status=` ➕ | 🛡 | 관리자 공고 목록: `draft` · `published` · `closed` | S-R01 |
| `POST /admin/postings` | 🛡 | 임시저장 공고 만들기 | S-R03 |
| `GET /admin/postings/{id}` ➕ | 🛡 | 편집용 상세(채점 기준·잠금 여부 포함) | S-R03, S-R04 |
| `PATCH /admin/postings/{id}` | 🛡 | 공고 내용·채점 기준 고치기. 기준이 잠기면 기준 칸만 409 | S-R03 |
| `POST /admin/postings/{id}/publish` | 🛡 | 게시. 예약 작업은 없다. api 가 1분마다 마감 시각이 지난 게시 공고를 닫는다 | S-R03 3단계 |
| `POST /admin/postings/{id}/close` | 🛡 | 지금 마감. 진행 중 면접도 바로 끝남(INT-10) | S-R01 |
| `DELETE /admin/postings/{id}` ➕ | 🛡 | 지원자 0명일 때만 삭제 | S-R01 |
| `POST /admin/postings/import` | 🛡 | Open API·더미 JSON/CSV에서 불러오기 → 임시저장. **현재 구현 범위 밖(미구현)** | S-R01 모달 |
| `POST /admin/postings/{id}/draft-ai` | 🛡 | AI 공고 초안 만들기(llm-rt, 뒤에서). 임시저장 공고에만 | S-R02 |
| `GET /admin/postings/{id}/draft-ai/status` ➕ | 🛡 | 초안 만들기 진행 상태 | S-R02 |
| `POST /admin/postings/{id}/draft-ai/revise` ➕ | 🛡 | AI 초안 한 칸 다시 쓰기 (CONFLICTS C-15) | S-R03 |

### 공고 객체

```json
{
  "posting_id": "3a7e…",
  "status": "published",
  "source": "manual",
  "title": "AI/AX 엔지니어 (신입·경력)",
  "job_code": "AI_AX",
  "company_name": "",
  "company_intro": "…",
  "duties": "…",
  "requirements": "…",
  "preferred": "…",
  "employment_type": "full_time",
  "location": "서울 강남구",
  "headcount": 3,
  "open_at": "2026-11-02T09:00:00+09:00",
  "close_at": "2026-11-10T18:00:00+09:00",
  "release_at": "2026-11-11T10:00:00+09:00",
  "contact_email": "recruit@example.com",
  "has_coding_test": true
}
```

- 회사명은 화면에 표기하지 않는다(한 기업 전용 면접 시스템, CONFLICTS U1). 그래서 입력·게시 필수 항목에서 뺐고, 응답의 `company_name`은 DB 칸이 남아 있어 빈 글자로만 온다. 화면은 쓰지 않는다. 기업 질문은 '우리 회사'로 부른다.
- `company_intro`는 화면에서 **'부서 소개'**로 부른다. 칸 이름은 그대로 `company_intro`다(CONFLICTS V1). 게시 필수 칸이다.
- `source`: `manual` · `ai_draft`(AI 초안을 만든 공고, 화면정의서 §12 #18 추가값). `open_api` · `dummy`는 공고 불러오기(미구현)용 값이라 지금은 나오지 않는다. 〔`ai_draft`는 TRD `source` 목록에 없음, 12장 A-10〕
- `contact_email`은 화면정의서 D-03에서 추가한 칸이다. 기본값은 관리자 이메일.
- `GET /postings/{id}`는 로그인한 지원자에게 `my_application: { "application_id", "attempt_status" }`(없으면 `null`)를 더 주고, 모든 요청에 `revisions`와 `server_time`을 준다. 카드 버튼은 화면정의서 §3.4 표를 따른다.
- `GET /postings`는 `?q=&job_code=&page=&size=`(`q`는 제목 검색, `size` 최대 50). 게시 중(`published`)이면서 접수 기간 안인 공고만 내보내고, 로그인한 지원자에게는 항목마다 `my_attempt_status`(없으면 `null`)를 더 준다. 마감 임박순으로 정렬한다.
- `GET /admin/postings`는 쪽 나누기 없이 `{ "items": [...], "total": N }`을 주고, 항목마다 `criteria`·`applicant_count`(작성 중이 아닌 지원 수)를 더한다.

**게시 후 수정(화면정의서 G-14)**: 게시 중인 공고에 대한 `PATCH /admin/postings/{id}`는 화면정의서 §10.3의 허용 항목만 받는다. 허용하지 않는 칸이 있으면 409 `FIELD_LOCKED_AFTER_PUBLISH`다. 바뀐 칸마다 `posting_revisions`(posting\_id, revised\_at, field, before, after)를 남기고, `GET /postings/{id}` 응답에 아래 `revisions`를 넣어 지원자에게 '수정 사항'을 보여 준다.

```json
"revisions": [ { "revised_at": "2026-11-04T14:00:00+09:00", "field": "location", "summary": "근무지: 서울 강남구 → 서울 서초구" } ]
```

### 채점 기준 객체 (관리자 응답에만)

```json
"criteria": {
  "version": 1,
  "locked": false,
  "weights": { "expertise": 30, "logic": 25, "relevance": 20, "delivery": 10, "culture_fit": 15 },
  "coding_enabled": true,
  "coding_ratio": 30,
  "pass_score": 70
}
```

- 가중치는 5 단위, 항목마다 5 이상, 합계 100. 틀리면 400 `WEIGHT_SUM`.
- `coding_ratio`는 10 단위(기본 30 = 면접 70 : 코딩 30). `coding_enabled: false`면 무시한다.
- `pass_score`는 0\~100 정수, 기본 70.
- 첫 응시가 시작되면 `locked: true`. 그 뒤 `PATCH`에 `criteria`가 있으면 409 `CRITERIA_LOCKED`, 공고 내용 칸은 그대로 바뀐다(JOB-07).

### POST /admin/postings/{id}/publish · /close

- 게시 조건: 필수 칸(제목·부서 소개·주요 업무·자격 요건·고용 형태·근무지·모집 인원·접수 시작·마감·문의 이메일)과 평가 기준이 채워짐, `open_at ≤ close_at`, `close_at`이 지금 뒤, 직무가 AI/AX 엔지니어. 아니면 400 `POSTING_INCOMPLETE` 또는 400 `JOB_NOT_OPEN`. 임시저장이 아니면 409 `ALREADY_PUBLISHED`. 응답 200은 공고 객체(채점 기준 포함).
- `close`: 게시 중이 아니면 409 `NOT_PUBLISHED`. 응답 200 — `{ "closed_at": "…", "not_taken": 4, "ended_by_close": 1 }`. 시작 전 지원은 `not_taken_closed`, 진행 중·장애 중단은 `ended_closed`가 되고 채점 작업이 들어간다(TRD 10장).
- `DELETE` 204: 지원이 하나라도 있으면(작성 중 포함) 409 `HAS_APPLICANTS`. 이 공고를 가리키는 관리자 알림(마감 임박)은 함께 지운다.
- 마감된 공고에 `PATCH`하면 409 `POSTING_CLOSED`.
- 게시가 끝나면 api 가 뒤에서 이 공고의 직무·회사 질문 후보를 만들어 질문관리 '검토 대기'로 넣는다(TRD 7-4 ②, C-17). 응답을 기다리게 하지 않고, 실패해도 게시는 그대로다.

### GET /admin/questions · POST /admin/questions/{id}/approve · /reject

- AI 가 만든 질문(`source=generated`: 면접 때 만든 것 · 공고 기반 · 인터넷 참고)만 다룬다. 엑셀·예비 질문은 404.
- `GET` 쿼리: `status`(pending·active·rejected, 기본 pending), `kind`(personality·company·job). 최근 200개.
- 응답 200 — `{ "items": [{ "id": 6421, "kind": "company", "text": "…", "status": "pending", "category": "공고 기반", "scope": { "type": "posting", "posting_id": "…", "label": "AI/AX 엔지니어 (신입)" } }], "counts": { "pending": 3, "active": 1, "rejected": 0 } }`. `scope.type`은 `posting`(그 공고 전용) · `job`(`job_code`와 직무 이름) · `common`(공통) (C-17, 2026-11-10).
- `approve`는 `active`(질문은행에서 씀), `reject`는 `rejected`로 바꾸고 감사 기록을 남긴다. 응답은 질문 1개(위 모양).

### POST /admin/postings/import

**현재 구현 범위 밖(미구현)이다.** 요구사항(PRD JOB-08, TRD 5-1)은 지우지 않고 이후 범위로 둔다. 필요하면 범위를 정해야 한다. 공고 테이블에는 `external_id` 칸만 있다. 아래는 설계 당시 명세다.

요청 — Open API는 `{ "source": "open_api", "query": { "keyword": "AI", "limit": 20 } }`(JSON), 더미는 `multipart/form-data`로 `source=dummy`와 `file`(JSON·CSV).

응답 200

```json
{ "imported": 12, "skipped_duplicate": 3, "needs_job_check": 2, "posting_ids": ["…"] }
```

같은 `external_id`는 건너뛴다. 모두 `draft`로 들어오고, 직무가 AI/AX가 아니면 `needs_job_check`로 센다. Open API가 답하지 않으면 502 `IMPORT_SOURCE_FAILED`.

### POST /admin/postings/{id}/draft-ai

빈 임시저장 공고를 먼저 만들고(`POST /admin/postings`), 그 id로 부른다(경로 `/admin/postings/{id}/draft-ai`, 공고 id가 경로에 들어간다. CONFLICTS U2). 화면을 떠나도 만들기는 계속되고, 결과는 그 공고에 채워진다(G-06). 이 요청은 1단계에 넣었다(원래 2단계였음, CONFLICTS U2).

```json
{
  "job_code": "AI_AX",
  "career_level": "junior", "career_years": 2,
  "employment_type": "full_time",
  "location": "서울 강남구",
  "headcount": 3,
  "open_at": "…", "close_at": "…",
  "duties": ["LLM 서비스 개발", "데이터 파이프라인"],
  "skills": ["Python", "PyTorch"],
  "preferred": "…",
  "company_intro": "…",
  "emphasis": "…",
  "coding_test": true
}
```

- **`company_name`은 받지 않는다**(보내면 422). 한 기업 전용 시스템이라 회사명을 표기하지 않는다(CONFLICTS U1).
- `company_intro`는 **부서 소개 메모**이고 선택이다(CONFLICTS V1). 비우면 AI가 맡을 일로 부서 소개를 쓴다. 칸 이름은 `company_intro` 그대로다.
- `duties`('주로 맡을 일')는 **선택**이다(CONFLICTS U6). 비우거나 공백만 넣어도 받는다(최대 10개, 공백만 있는 것은 버리고 같은 것은 하나로). 비우면 AI에게 '(지정 없음)'으로 알려 직무·기술·강조점에 맞게 주요 업무를 쓰게 한다. 직접 입력한 말은 AI가 공고 문장으로 다듬는다.
- `career_level`(`junior` · `experienced` · `any`), `employment_type`(`full_time` · `contract` · `intern`), `location`(1~200자), `headcount`(1~999), `open_at`, `close_at`, `coding_test`는 필수다. `career_years`는 선택(0~30), `skills`는 최대 20개, `preferred`·`emphasis`는 500자, `company_intro`는 1000자까지다.
- 오류: 409 `ALREADY_PUBLISHED`(임시저장 공고가 아님) · 409 `DRAFT_RUNNING`(이미 만드는 중) · 400 `JOB_NOT_OPEN`(준비 중 직무) · 400 `POSTING_INCOMPLETE`(접수 시작이 마감보다 뒤이거나 마감이 지금 이전).
- AI 모델은 채점용 8B가 아니라 **llm-rt(Qwen3 4B)**다. 1단계에는 채점용 모델이 없고 GPU 한 장에 모델을 하나만 올릴 수 있어서다(CONFLICTS 'AI 초안 구현 메모'). 실측 약 8초.
- AI가 쓰는 칸은 제목·부서 소개·주요 업무·자격 요건·우대 사항이다. 부서 소개를 너무 짧게 쓰면 맡을 일·기술로 만든 기본 문구로 채운다. 고용 형태·근무지·인원·기간·직무·코딩테스트 여부는 AI를 거치지 않고 그대로 복사한다. 이때 `source`가 `ai_draft`로 바뀌고 감사 로그 `posting.draft_ai`가 남는다.

응답 202 — `{ "job_id": "…", "status": "running" }`(`job_id`는 공고 id와 같다).

`GET …/draft-ai/status` 응답 — `{ "status": "running" | "done" | "failed", "posting_id", "stage": "retrieve" | "draft" | "check" | "rewrite" | null, "bias_warnings": [ { "text": "만 30세 이하", "reason": "나이 제한" } ], "notes": ["같은 직무의 예전 공고 2건을 참고했습니다", "자격 요건 칸을 다시 썼습니다 (…)"], "revision": null, "error": null }`. `stage`는 그래프의 지금 단계(참고 공고 찾기·초안·점검·다시 쓰기), `notes`는 AI가 이번에 한 일, `revision`은 다시 쓰기 결과(`{ "section", "text" }`)다. AI 초안을 만든 적 없는 공고(`source`가 `ai_draft`가 아님)는 404. 진행 상태는 api 프로세스 메모리에 둔다. 재시작되면 제목·주요 업무가 채워져 있으면 `done`, 아니면 `failed`(`error: "lost"`)로 보이고 [다시 시도]할 수 있다.

`bias_warnings`는 화면정의서 O-05대로 **규칙 기반 사전**(나이·성별·혼인·외모·출신 지역·종교)으로 찾는다. 초안을 쓸 때 걸린 칸은 AI가 1번 다시 쓰고, 그래도 남으면 알려 줄 뿐 막지는 않는다. 같은 직무의 예전 공고(게시·마감, 최근 2건)를 참고로 넣고, 그 문장을 40자 넘게 그대로 옮긴 칸도 다시 쓴다(CONFLICTS C-15).

### POST /admin/postings/{id}/draft-ai/revise

AI 초안의 한 칸을 관리자 요청대로 다시 쓴다(CONFLICTS C-15). 요청 `{ "section": "title" | "company_intro" | "duties" | "requirements" | "preferred", "note": "1~300자", "current": "편집 화면의 지금 글(5000자까지)" }`. 처음 입력·참고 공고는 초안 때의 그래프 기록(체크포인트)에서 읽는다. 다시 쓴 글도 같은 검사를 거쳐 차별 표현이 있으면 1번 더 쓴다. 응답 202 — `{ "job_id", "status": "running" }`. 결과는 `…/draft-ai/status`의 `revision`으로 주고 **DB에는 쓰지 않는다**(관리자가 확인하고 저장). 감사 로그 `posting.draft_revise`(칸 이름만). 오류: 404(AI 초안 공고가 아님) · 409 `ALREADY_PUBLISHED`(임시저장 아님) · 409 `DRAFT_RUNNING` · 409 `DRAFT_NOT_REVISABLE`(초안 기록 없음: 아직 만드는 중·실패·기록 삭제) · 422(칸 이름·요청 길이).

## 5. 지원·동의·이력서 API

지원은 `지원 만들기 → 동의 → 이력서 올리기(선택) → 이력서 확정` 순서다. 확정하는 순간 상태가 `ready`가 되고, 서버는 면접 질문 10개 만들기를 뒤에서 시작한다(QST-03).

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `POST /applications` | 🔒 | 지원 만들기(`drafting`). 작성 중인 지원이 있으면 그것을 돌려줌 | S-A02 |
| `GET /applications/{id}` ➕ | 🔒 | 지원 절차 화면의 공통 정보와 상태별 가드(공고 요약·이력서 사본·올린 파일 진행·질문 준비 상태) | S-A03~S-A05 |
| `POST /applications/{id}/consent` | 🔒 | 필수 동의 5개 기록 | S-A03 |
| `POST /applications/{id}/consent/withdraw` ➕ | 🔒 | 동의 철회: 진행 중 응시 취소, 이 지원의 데이터 즉시 삭제 | S-A13 계정 |
| `POST /applications/{id}/resume/upload` ➕ | 🔒 | 이력서 파일 올리기 → 내용 뽑기 시작(OCR 포함) | S-A04 |
| `GET /applications/{id}/resume/extract-status` ➕ | 🔒 | 뽑기 진행 단계·예상 시간·결과·실패 이유 (2초마다 조회) | S-A04 |
| `GET /applications/{id}/resume/file` ➕ | 🔒 | 올린 원본 이력서 파일 돌려받기(확인 화면의 '원본과 비교'용, `private, no-store`) | S-A05 |
| `DELETE /applications/{id}/resume/upload` ➕ | 🔒 | 처리 중 취소, 올린 파일 삭제 | S-A04 \[취소\] |
| `POST /applications/{id}/resume` | 🔒 | 이력서 확정(사본 저장). 이후 수정 불가 | S-A05 |
| `GET /me/resume` ➕ | 🔒 | 마이페이지 등록 이력서(1개) | S-A04, S-A13 |
| `PUT /me/resume` ➕ | 🔒 | 등록 이력서 저장(통째로) | S-A13 이력서 |
| `DELETE /me/resume` ➕ | 🔒 | 등록 이력서 삭제 | S-A13 이력서 |
| `POST /me/resume/upload` ➕ | 🔒 | 등록 이력서용 파일 올리기(같은 추출 과정). **라우터에 없음 — 논의사항 #4** | S-A13 이력서 |
| `GET /me/resume/extract-status` ➕ | 🔒 | 위 추출 진행 상태. **라우터에 없음 — 논의사항 #4** | S-A13 이력서 |

### POST /applications

요청 — `{ "posting_id": "3a7e…" }`

응답 200 (새로 만들 때도 작성 중인 지원을 돌려줄 때도 200) — `{ "application_id": "7b2e…", "attempt_status": "drafting", "next_step": "consent" }`. `next_step`은 `consent` · `resume` 중 하나로, 이어서 쓸 때 어느 화면으로 보낼지 알려 준다(철회하지 않은 동의가 있으면 `resume`). 같은 사용자의 지원 만들기는 한 줄로 세워 두 번 눌러도 지원이 2건 생기지 않는다.

| 오류 | code | 조건 |
| --- | --- | --- |
| 409 | `ALREADY_APPLIED` | 같은 공고에 `drafting`이 아닌 지원이 있음(1회 응시) |
| 409 | `POSTING_CLOSED` | 접수 기간이 아님 |
| 400 | `JOB_NOT_OPEN` | 준비 중 직무 공고 |
| 404 | `NOT_FOUND` | 없는 공고 또는 임시저장 공고 |
| 403 | `EMAIL_NOT_VERIFIED` | `email_verification_required=true`인데 미인증. 이메일 인증이 미구현이라 현재 나오지 않음 |

### POST /applications/{id}/consent

```json
{
  "consent_version": "v1.8",
  "items": {
    "data_collection": true,
    "ai_decision": true,
    "share_with_admin": true,
    "retention": true,
    "exam_rules": true
  }
}
```

응답 201 — `{ "consent_id": "…", "agreed_at": "…" }`. 하나라도 `false`면 400 `AGREEMENT_REQUIRED`. 문구 버전은 서버의 현재 버전과 같아야 하고, 다르면 409 `CONSENT_VERSION_CHANGED`(화면이 새 문구를 다시 보여 줌). 작성 중(`drafting`)이 아닌 지원이면 409 `RESUME_LOCKED`.

### POST /applications/{id}/consent/withdraw

요청 본문 없음. 응답 204. 철회하지 않은 동의가 없으면 409 `NO_CONSENT`(CONFLICTS W3). 진행 중 응시는 자리를 돌려주고 WebSocket `terminate`(`withdrawn`)를 보낸 뒤 이 지원의 데이터를 바로 지운다. 되돌릴 수 없다. 동의 기록은 철회 시각을 적어 증거로 남긴다.

### GET /me/applications 의 `consented`

`GET /me/applications`(9장)의 항목마다 `consented`(철회하지 않은 동의가 있는지)를 준다. 계정 탭의 [동의 철회] 버튼이 이 값을 본다(CONFLICTS W2).

`connected`는 진행 중(`interviewing`·`coding`) 응시의 면접 화면이 지금 서버에 붙어 있는지다. 진행 중이 아니면 `false`. 화면은 진행 중인데 `false`이면 "다른 창에서 응시 중" 대신 미연결 안내를 보여 준다(2026-11-09, 논의사항 E7).

### POST /applications/{id}/resume/upload

`multipart/form-data`의 `file` 하나. PDF·JPG·PNG만 받고, 확장자와 파일 앞부분의 실제 형식을 함께 본다.

응답 202

```json
{
  "upload_id": "c41d…",
  "file_name": "이력서_홍길동.pdf",
  "pages": { "text": 1, "scanned": 8 },
  "estimated_seconds": 85
}
```

`estimated_seconds` = 글자 있는 쪽 수 × 0.5 + 스캔 쪽 수 × `ocr_sec_per_page` + `resume_llm_sec`(TRD 7-6 ①). 오류: 400 `UNSUPPORTED_FILE`(형식 불일치 포함) · 413 `FILE_TOO_LARGE`. 화면은 둘 다 "이력서를 불러오는 데 실패했습니다" 모달로 보여 준다(D-05).

### GET /applications/{id}/resume/extract-status

```json
{
  "upload_id": "c41d…",
  "stage": "ocr",
  "estimated_seconds": 85,
  "elapsed_seconds": 18,
  "method": null,
  "result": null,
  "ocr_confidence": null,
  "ocr_low_conf_fields": [],
  "fail_reason": null,
  "file_name": "이력서_홍길동.pdf"
}
```

올린 파일이 없으면 404 `NOT_FOUND`.

- `stage`: `uploaded` → `checking` → `ocr`(스캔 쪽·사진이 있을 때만) → `structuring` → `done` | `failed`.
- `done`이면 `method`(`text` · `ocr` · `mixed`), `result`(아래 이력서 객체), `ocr_confidence`(평균, 예 `"0.86"`), `ocr_low_conf_fields`(예 `["career[0].company"]`, 신뢰도 0.80 미만)가 채워진다.
- `failed`면 `fail_reason`: `OCR_FAILED`(OCR 서비스 장애·시간 초과로 글자를 하나도 못 얻음), `TIMEOUT`(항목 정리(LLM)가 남은 시간 안에 못 끝남. 남은 시간 = 예상의 2배(최소 60초)에서 이미 쓴 시간을 뺀 값, 최소 5초) · `NO_TEXT`(OCR 은 호출 하나당 60초 제한이며 실패하면 그 쪽을 읽지 못한 채 진행해 이 값이 된다) · `LOW_CONFIDENCE`(평균 0.5 미만) · `INTERNAL`(서버 쪽 오류. api 가 다시 시작되면 끝나지 않은 업로드도 이 값이 된다). 화면은 "직접 입력하시겠어요?" 모달을 띄운다(APP-04).

### POST /applications/{id}/resume (확정)

```json
{
  "method": "upload",
  "upload_id": "c41d…",
  "resume": {
    "name": "홍길동",
    "education": [ { "school": "○○대학교", "major": "컴퓨터공학", "degree": "bachelor", "start": "2018-03", "end": "2024-02" } ],
    "career": [ { "company": "△△", "role": "ML 엔지니어", "start": "2024-03", "end": null, "description": "…" } ],
    "projects": [ { "name": "…", "period": "2025-01~2025-06", "description": "…", "skills": ["PyTorch"] } ],
    "skills": ["Python", "PyTorch", "SQL"],
    "certificates": [ { "name": "정보처리기사", "acquired": "2023-11" } ],
    "cover_letter": null
  },
  "edited_fields": ["career[0].company"]
}
```

- `method`: `upload` · `manual` · `saved`(등록본). `upload`일 때만 `upload_id`가 필요하다.
- `edited_fields`는 지원자가 고친 칸으로, 관리자 이력서 탭에 표시한다.
- 필수 칸은 성명(`resume.name`)과 학력 또는 경력 1건 이상이다(APP-05).
- 응답 200 — `{ "attempt_status": "ready", "close_at": "…", "release_at": "…" }`. 필수 칸이 빠지면 422 `RESUME_REQUIRED_MISSING`(`message`에 칸 이름), 이미 확정했으면 409 `RESUME_LOCKED`. 그 밖에 동의 전이면 409 `CONSENT_REQUIRED`, 접수 기간이 아니면 409 `POSTING_CLOSED`, `method`가 `upload`인데 올린 파일이 없거나 남의 것이면 400 `UPLOAD_REQUIRED`.
- 이력서 읽기는 리더(PyMuPDF·pdfplumber) → LLM 항목 정리 → 읽지 못한 쪽·사진·빈 칸만 OCR(PaddleOCR) 순서다(1단계, CONFLICTS U4). 이력서를 확정하면 상태가 `ready`가 되고 화면에는 '면접 준비 중'으로 보인다(CONFLICTS U3).
- `/me/resume`의 `GET`·`PUT`은 같은 `resume` 객체를 주고받는다. 등록본을 바꿔도 이미 확정한 지원의 사본은 바뀌지 않는다(APP-05).

## 6. 면접 시작·점검 API

면접은 `장치 점검 → 시작(입장 관리 통과) → WebSocket 연결` 순서로 들어간다. 응시 횟수는 시작 API가 아니라 첫 질문이 나갈 때(`attempt_consumed_at`) 쓴다.

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `POST /applications/{id}/precheck` | 🔒 | 장치·인터넷·AI 서버 점검, 통과 표시 발급 | S-A06, S-A15 |
| `GET /applications/{id}/interview/state` ➕ | 🔒 | 지금 응시 상태, 질문 준비 정도, 장애 판단 결과, 이어가기 기한 | `/exam` 가드, S-A15 |
| `POST /applications/{id}/interview/start` | 🔒 | 입장 관리(N) 통과 시 면접 세션 발급 | S-A07 |
| `POST /applications/{id}/interview/resume` ➕ | 🔒 | 장애 중단 면접 이어가기(N 다시 안 봄) | S-A15 |
| `POST /interview/{sid}/events` ➕ | 세션 | 창 닫기·이탈 신호를 `sendBeacon`으로 남김 | S-A09, S-A11 |
| `POST /interview/{sid}/recording` ➕ | 🔒 세션 | 카메라(소리 포함) 녹화 조각 올리기 | S-A09, S-A11 |

### POST /applications/{id}/precheck

요청

```json
{
  "browser": { "name": "chrome", "version": "141" },
  "devices": { "mic": true, "camera": true, "speaker": true },
  "network_mbps": "12.4"
}
```

응답 200

```json
{
  "passed": true,
  "checks": { "browser": "ok", "mic": "ok", "camera": "ok", "speaker": "ok", "network": "ok", "ai_server": "ok" },
  "valid_until": "2026-11-03T10:15:00+09:00"
}
```

- 마이크·카메라·스피커는 화면이 확인한 결과를 그대로 기록하고, 서버는 브라우저(Chrome·Edge **120 이상**)·인터넷(1Mbps 이상)·AI 서버(llm-rt·stt 상태)를 본다. 브라우저 '최신 2개 버전' 목록을 실시간으로 받을 수 없어 하한 버전만 둔다(CONFLICTS C5). 브라우저 종류와 버전은 화면이 알려 준 값을 쓴다.
- 각 항목은 `ok` · `fail`. 하나라도 `fail`이면 `passed: false`. 통과 표시는 15분 동안 유효하며, 시작·이어가기 API가 이를 확인한다.
- 상태가 `ready`(또는 `interrupted`)가 아니면 409 `NOT_READY`.

### GET /applications/{id}/interview/state

```json
{
  "attempt_status": "interrupted",
  "phase": "interview",
  "current_seq": 4,
  "questions": { "ready": true, "composed": 10, "total": 10 },
  "interruption": {
    "judged": "fault",
    "reason": "heartbeat_timeout",
    "at": "2026-11-03T10:07:42+09:00"
  },
  "end_detail": null,
  "precheck_valid_until": null,
  "resumes_left": 2,
  "resume_until": "2026-11-10T18:00:00+09:00",
  "release_at": "2026-11-11T10:00:00+09:00",
  "server_time": "2026-11-03T10:09:01+09:00"
}
```

- `phase`: `interview` · `coding` (어느 화면으로 이어 갈지).
- `interruption.judged`: `fault`(장애 → 이어가기 가능) · `not_fault`(장애 아님 → `ended`). 서버는 끊긴 뒤 15초가 되는 순간 판단하므로(TRD 7-2), 이 API는 그 결과를 읽기만 한다. 판단이 없으면 `interruption`은 `null`이다.
- `reason`: `fault`이면 `heartbeat_timeout` · `ws_abnormal_close` · `device_error` · `upload_failed` · `server_error` · `unknown`. `not_fault`이면 끝난 이유(`end_detail`)인 `unload` · `permission_revoked`가 들어간다. 연결이 끊긴 채 15초 동안 아무 신호가 없었던 경우와 서버 재시작은 장애로 본다(원인 미상은 지원자에게 유리하게, TRD 7-2).
- `end_detail`: 응시가 끝난 이유(`unload` · `permission_revoked` · `exit_twice` · `resume_limit` · `replaced` · `coding_timeout` 등). 없으면 `null`.
- `resumes_left`: 남은 이어가기 횟수(CONFLICTS D1). 설정 `resume_limit`=3에서 지원자 쪽 끊김으로 이어간 횟수를 뺀 값이다. 이어가기 화면이 이 값을 보여 준다.
- `resume_until`은 공고 마감 시각이다(RES-03). `server_time`으로 화면 카운트다운을 맞춘다.

### POST /applications/{id}/interview/start

요청 본문 없음. 응답 200

```json
{
  "session_id": "5d1c2f0e-…",
  "ws_url": "ws://127.0.0.1:8000/ws/interview/5d1c2f0e-…",
  "question_total": 10,
  "questions_ready": false,
  "recording_segment": 1
}
```

- `questions_ready: false`면 화면은 S-A08 '질문 준비 중'을 띄우고, WebSocket `preparing` 메시지를 받다가 첫 `question`이 오면 면접을 시작한다. 기다림 상한은 60초(`question_compose_budget_sec`)이고, 넘으면 서버가 질문 DB·예비 질문으로 채운다. 이 60초에는 질문 음성(TTS) 미리 만들기 시간(질문마다 최대 30초, 차례로)이 들어 있지 않다.
- 시작 성공 시 `interview:active`를 1 올리고 `holds_seat=true`. 상태는 이때 바로 `interviewing`(면접 진행 중)이 된다(TRD 7-1). 응시 횟수만 첫 질문이 나갈 때 쓴다. 그래서 '질문 준비 중' 동안 끊겨도 면접 진행 중과 같은 장애 판단을 받는다.

| 오류 | code | 조건 |
| --- | --- | --- |
| 429 | `CAPACITY_FULL` | 동시 면접 N이 참. 응시 횟수 안 씀. 화면은 '다시 시도'를 10초 막는다. 자동 보호(그래픽카드 메모리 92%·다음 질문 시간)로 입장을 막는 기능은 현재 구현 범위 밖(미구현) |
| 409 | `PRECHECK_REQUIRED` | 점검 통과 표시 없음 또는 15분 지남 |
| 409 | `NOT_READY` | 상태가 `ready`가 아님(이력서 미확정 등) |
| 409 | `ALREADY_ATTEMPTED` | 이미 응시함(1회 제한) |
| 409 | `POSTING_CLOSED` | 마감 시각이 지남(INT-10) |

### POST /applications/{id}/interview/resume

요청 본문 없음. 응답은 start와 같은 모양에 `"phase"`와 `"resume_seq"`(다시 낼 질문 번호)를 더한다. recording\_segment는 직전 구간보다 1 큰 값이다.

- N을 다시 확인하지 않는다. phase가 interview이고 자리를 이미 돌려줬으면(끊긴 뒤 10분) 1을 다시 더한다(TRD 5-3). coding이면 코딩테스트는 동시 면접 수에 세지 않으므로 더하지 않는다.
- 면접은 끊긴 질문을 처음부터 새 답변 시간으로, 코딩테스트는 마지막 자동 저장 코드와 남은 시간으로 이어 간다. 면접은 면접 진행 그래프의 `locate` 단계가 원장(applications)을 읽어 끊긴 질문부터 다시 낸다(CONFLICTS B1).
- **이어가기는 3번까지**다(CONFLICTS D1, 설정 `resume_limit`=3). 지원자 쪽 끊김(네트워크·장치·녹화 업로드 실패 등)만 세고, 서버 오류(`server_error`)·원인 미상(`unknown`, 서버 재시작)은 세지 않는다. 3번을 다 쓴 뒤 또 끊기면 장애 중단 대신 응시를 종료한다. 이때 상태는 `ended`, `end_detail`은 `resume_limit`이고 WebSocket에는 `paused`가 아니라 `terminate`(`ended`, detail `resume_limit`)를 보낸다. 답변한 문항까지 채점한다. 남은 횟수는 `GET …/interview/state`의 `resumes_left`로 안다. (PRD v1.8·TRD v1.7 에 반영됨. 팀 원본에는 없음)
- 오류: 409 `PRECHECK_REQUIRED` · 409 `NOT_INTERRUPTED`(상태가 `interrupted`가 아님) · 409 `POSTING_CLOSED`(재점검 중 마감돼 `ended_closed` 가 된 경우 포함. 화면은 마감 안내로 바뀐다).

### POST /interview/{sid}/events

탭 닫기·새로고침·뒤로 가기 때 `beforeunload`·`pagehide`에서 `navigator.sendBeacon`으로 보낸다. 본문을 문자열로 넣으면 `text/plain`으로 가서 Pydantic 본문 파싱이 422로 실패하고, 그러면 '장애 아님'이 '장애'로 잘못 판정된다. 그래서 두 쪽을 모두 지킨다. ① 서버는 Content-Type에 기대지 않고 `request.body()`를 직접 JSON으로 풀고, 풀지 못해도 204를 돌려주며 원문을 `session_events`에 남긴다. ② 화면은 `new Blob([JSON.stringify(body)], { type: 'application/json' })`로 보낸다. 같은 출처(127.0.0.1:8080 → /api)라 사전 요청(preflight)이 없다.

```json
{ "type": "unload", "at": "2026-11-03T10:07:30+09:00", "detail": "pagehide" }
```

- `type`: `unload` · `permission`(마이크·카메라 권한 해제). 연결이 살아 있을 때의 이탈·장치 신호는 WebSocket으로 보낸다(7장).
- 응답 204. 로그인 쿠키가 없거나 남의 세션이어도 204로 돌려주고 기록하지 않는다. 서버는 `session_events`에 남기고, 끊기기 직전 30초(`unload_lookback_sec`) 안에 이 기록이 있으면 '장애 아님'으로 본다.

### POST /interview/{sid}/recording

`multipart/form-data` — `segment_no`(접속 구간 번호, 1 이상), `chunk_no`(구간 안에서 0부터), `phase`(`interview` · `coding`), `file`(WebM 10초 조각, 카메라 영상과 마이크 소리, 약 300kbps). 응답 204. `segment_no`는 start·resume 응답의 `recording_segment`를 쓴다(시작 1, 이어가기마다 1씩 늘어남). MediaRecorder 조각은 구간의 첫 조각에만 헤더가 있다.

- **저장 방식(CONFLICTS R1)**: 저장소(RustFS)는 이어 쓰기가 없어서 조각마다 객체 하나로 저장하고(`recordings/{지원}/{구간}/00000.webm` …), 재생할 때 순서대로 이어 보낸다. 받는 쪽에서는 구간마다 파일 하나와 같다. 같은 조각을 다시 올리면 한 번만 저장한다. 순서가 바뀌어 늦게 온 작은 번호 조각도 저장하고, 재생은 번호순이다(2026-11-09, 논의사항 E12).
- **상한(CONFLICTS R6)**: 조각 5MB, 구간 400MB. 응시가 끝난 뒤 60초까지만 마지막 조각을 받는다. 구간의 첫 조각은 WebM 머리글을 확인한다. 이를 어기면 4xx이고(413 `FILE_TOO_LARGE`, 400 `INVALID_FILE`, 409 `NOT_IN_PROGRESS`, 409 `SEGMENT_MISMATCH`) 화면은 장애로 보지 않고 그 조각만 버린다.
- **저장소 장애(CONFLICTS R5)**: 저장소에 쓰지 못하면 503 `STORAGE_UNAVAILABLE`을 돌려주고 `session_events`에 `upload_error`를 남긴다.
- **재시도와 실패 알림**: 실패하면 화면이 1·2·4초 간격으로 3번(`upload_retry_limit`) 다시 올리고, 그래도 안 되면 WebSocket으로 `upload_failed`를 보낸다(7장). 서버는 화면이 말한 원인을 믿지 않고 서버 기록으로 정한다. 최근 60초 안에 `upload_error`가 있으면 `server_error`(서버 쪽 장애, 이어가기 횟수에 안 셈), 없으면 `upload_failed`(지원자 쪽, 횟수에 셈)로 장애 중단한다.
- 녹화는 응시 끝 + 3일 뒤 지운다(재생은 기한이 지나면 바로 410, 파일은 매시 30분 작업이 지움, CONFLICTS R3). 답변 음성은 이 API가 아니라 WebSocket의 이진 메시지로 보낸다(7장).

## 7. 면접 실시간 통신 (WebSocket)

면접 중에는 WebSocket 연결 하나를 열어 둔다. 질문·자막·진행 상태·연결 확인은 JSON 글자 메시지로, **답변 음성은 같은 연결의 이진 메시지(16kHz mono PCM16, 약 1초 조각)**로 주고받는다. WebRTC는 쓰지 않는다. 서버가 조각을 받아 STT로 처리하는 구조라 WebRTC 미디어 서버 없이 단순화했다(CONFLICTS V4). 코딩테스트 중에도 같은 WebSocket을 유지해 heartbeat와 이탈 신호를 보낸다.

면접 진행은 LangGraph 그래프(질문 내기 → 답변 기다리기 → STT → 꼬리질문 판단 → 다음 질문/코딩)가 정하고, 진행 상태는 PostgreSQL 체크포인트(thread_id = 지원 번호)에 남긴다. 새 연결(이어가기)마다 그래프의 `locate` 단계가 원장(applications)을 읽어 끊긴 질문부터 다시 낸다(CONFLICTS B1). 이 문서의 메시지 규칙은 그대로다.

### 7-1. 연결

- 주소: `ws://127.0.0.1:8000/ws/interview/{session_id}`. 로그인 쿠키와 `Origin`(`http://127.0.0.1:8080`)을 확인하고, 세션이 없거나 남의 것이거나 이미 끝났거나 응시 상태가 진행 중이 아니면 연결을 받은 뒤 종료 번호 4401로 닫는다(화면이 이유를 알 수 있게 한 번 받은 뒤 닫는다, CONFLICTS C-3). `Origin`이 다르면 연결을 받기 전 핸드셰이크 단계에서 거절하므로 브라우저에는 1006만 보인다.
- 세션은 **한 번만 연결**할 수 있다. 같은 세션으로 다시 붙으면 종료 번호 4409로 닫는다(새로고침 등). 끊기면 '이어가기'로 새 세션을 받는다(CONFLICTS C4). 같은 지원에서 다른 연결이 새로 붙으면 이전 연결은 `terminate`(`ended`, detail `replaced`)로 끝난다.
- 글자 메시지는 `type` 칸이 있는 JSON이다. 형식이 틀리면 `error`(`BAD_MESSAGE`), 모르는 `type`이면 `error`(`UNKNOWN_TYPE`)를 보내고 연결은 유지한다.
- 답변 음성 이진 메시지: 질문의 답변 단계(`answering`)에서만 받는다. 길이가 2바이트의 배수가 아니거나, 경고창이 떠 있는 동안이거나, 답변 시간보다 15초 넘게 긴 분량이면 버린다.
- 시작·이어가기 뒤 90초가 지나도 화면이 연결되지 않았거나 연결된 세션이 없는 진행 중 응시는 api 정리 작업(1분마다, `jobs.py`)이 '원인 미상 장애'(`unknown`)로 장애 중단 처리하고 이어가기를 허용한다(실제로는 90~150초). 서버를 다시 켤 때는 기다리지 않고 시작할 때 바로 같은 처리를 한다(`main.py`).
- 정상 종료는 1000. 서버가 면접을 끝낼 때는 `terminate`를 보낸 뒤 1000으로 닫는다. 1000·1001로 닫혀도 창 닫기 기록이 없으면 장애로 본다(TRD 7-2).

### 7-2. 질문 하나가 오가는 순서

1. 질문이 다 안 만들어졌으면 서버가 `preparing`을 1초마다 보낸다.
2. 서버가 `question`을 보낸다. 화면은 질문 음성을 틀고(없으면 자막만), 3-2-1 뒤 녹음을 시작해 음성 조각을 이진 메시지로 보낸다.
3. 답변 중 서버가 `caption`(임시 자막)을 보낸다.
4. 화면이 `answer_done`을 보내거나 답변 시간이 끝난다. 답변 시간은 화면과 별개로 서버도 마감 시각을 재서 넘으면 끊는다(CONFLICTS C2).
5. 서버가 음성을 글자로 바꾸고(STT, 실패하면 `stt_retry_limit`(2)번 다시 시도), 최종 글자(`caption`, `is_final: true`)를 보내고, 꼬리질문을 판단한 뒤 다음 `question`을 보낸다. 다음 질문은 `next_question_target_sec`을 목표로 하나, 이 값은 13-2 측정으로 지킬 목표값이며 코드가 강제하지 않는다(꼬리질문이 없으면 지체 없이 다음 질문을 낸다). 꼬리질문을 낼 때만 목표 시간을 `followup_target_sec`(운영 10초·개발 20초)로 따로 둔다(CONFLICTS U7). (PRD v1.8·TRD v1.7 에 반영됨. 팀 원본에는 없음)
6. 10번째 기본 질문(꼬리질문 포함)이 끝나면 `phase`로 코딩테스트에 넘어간다. 코딩테스트를 쓰지 않는 공고면 `terminate`(`completed`)로 끝난다.

### 7-3. 화면 → 서버 메시지

| type | 칸 | 보내는 때 |
| --- | --- | --- |
| (이진 메시지) | PCM16 음성 조각 | 답변 중 약 1초마다. JSON이 아니라 이진 프레임(16kHz, mono, 16bit)으로 보낸다(CONFLICTS V4) |
| `heartbeat` | `sent_at` | 5초마다. 3번 연속(15초) 안 오면 장애 판단 |
| `answer_done` | `seq`, `answer_no` | 지원자가 \[답변 완료\]를 누름 |
| `visibility` | `state`(`hidden`), `at` | 탭이 숨겨짐 |
| `blur` | `at`, `duration_ms` | 창이 포커스를 잃고 2초(`blur_threshold_sec`) 넘게 안 돌아옴. 2초 미만은 보내지 않음 |
| `fullscreen` | `state`(`exit`), `at` | 전체 화면 해제 |
| `navigate` | `at`, `href` | 다른 주소로 가려 함. 서버만 받을 준비가 되어 있고 화면은 보내지 않는다(실제로 떠날 때만 `unload`) |
| `device_error` | `device`(`mic` · `camera`), `kind`(`ended` · `open_failed`) | 트랙 `ended` 이벤트, 장치 열기 실패(무음 응시 방지, CONFLICTS C-3), 녹음기(`mic`)·녹화기(`camera`)를 시작하지 못함(`open_failed`). 어느 장치가 어떻게 멈췄는지 기록하고 장애 중단한다. 그 밖의 값은 `unknown`으로 기록한다. 직전 30초 안에 `permission` 기록이 있으면 장애가 아니라 응시 종료다. `kind: ended` 는 바로 정하지 않고 3초 기다린다: 그사이 연결이 끊기면 15초 끊김 판정에 맡기고, `unload`·`permission` 기록이 생기면 응시 종료, 둘 다 없으면 장애 중단이다(창을 닫으면 장치가 먼저 꺼지기 때문, 2026-11-09 논의사항 E18). `open_failed` 는 바로 장애 중단이다 |
| `permission` | `device`(`mic` · `camera`) | 마이크·카메라 권한을 직접 끔. 장애가 아니라 `terminate`(`ended`, detail `permission_revoked`)로 응시 종료(TRD 7-2, OV-07) |
| `autosave_failed` | `problem_no` | 코딩 자동 저장을 3번 다시 해도 실패(8장). 서버는 기록(session_events `autosave_failed`)만 남기고 멈추지 않는다. 끊김 판정은 heartbeat 로 한다 |
| `upload_failed` | (없음) | 녹화 조각을 3번 다시 올려도 실패(6장). 서버가 원인을 기록으로 정해 장애 중단(`paused`) 한다(CONFLICTS R5) |
| `warn_ack` | `seq` | 1번째 이탈 경고 창에서 \[확인\]을 누름 |
| `unload` | `at`, `detail` | 창 닫기·새로고침. 연결이 살아 있으면 여기로, 아니면 `POST /interview/{sid}/events`로 |

`rtc_offer`·`rtc_ice`는 받지 않는다. 보내면 `error`(`RTC_DISABLED`)로 답한다.

### 7-4. 서버 → 화면 메시지

| type | 칸 | 보내는 때 |
| --- | --- | --- |
| `preparing` | `composed`, `total`, `elapsed_sec` | 질문 준비 중(최대 60초) |
| `question` | `seq`, `kind`(`base` · `follow_up`), `text`, `audio_url`(없으면 `null`), `answer_sec`, `progress`(`"3 / 10"`), `resend` | 질문을 낼 때. 면접 중 LLM·TTS가 늦으면 `audio_url: null`. `audio_url`은 `/api/media/questions/{question_id}`(2-6). `resend`는 경고창을 닫은 뒤 같은 질문을 처음부터 다시 낼 때 `true` |
| `caption` | `seq`, `answer_no`, `chunk_no`, `text`, `is_final` | `caption_interval_sec`마다 임시 자막, 답변 끝에 최종 글자(`chunk_no` 10000). 화면은 더 작은 `chunk_no`나 지난 `seq`를 버린다 |
| `warn` | `count`(1), `seq`, `remaining_sec`, `phase`, `label` | 1번째 이탈. 시간을 멈추고 경고 창을 띄운다. `label`은 이탈 종류 글자(다른 탭으로 전환·다른 창으로 이동·전체 화면 해제·다른 주소로 이동) |
| `resume` | `seq`, `remaining_sec`, `phase` | `warn_ack` 뒤 다시 시작. 질문 준비·답변 처리 중이었으면 `seq`·`remaining_sec`이 `null`이고 경고창만 닫는다. (장애 이어가기는 새 세션이므로 이 메시지가 아니라 `question`으로 다시 시작한다) |
| `paused` | `reason`, `resume_until`, `resumes_left` | 장애로 멈춤(연결이 살아 있을 때만 도착). 화면은 OV-01. `reason`: `heartbeat_timeout` · `ws_abnormal_close` · `device_error` · `upload_failed` · `server_error` · `unknown` |
| `phase` | `to`(`coding`), `coding` → 8장 문제 목록(`problems`, `remaining_sec`, `started`, `away_count`, `auto_start_sec`) | AI 면접이 끝남 |
| `terminate` | `reason`, `detail`, `message` | 면접이 끝남. `reason`: `completed` · `cancelled`(2번째 이탈) · `closed`(마감) · `ended`(장애 아님) · `withdrawn`(동의 철회). `detail`: `unload` · `permission_revoked` · `exit_twice` · `resume_limit`(이어가기 횟수 초과, CONFLICTS D1) · `replaced`(다른 연결로 교체) · `coding_timeout`(코딩 시간 끝). 화면이 `detail`로 OV-07·OV-03 등을 고른다(D-09). `withdrawn`일 때 화면은 "동의 철회로 응시가 취소되었습니다" 오버레이를 띄운다(CONFLICTS W5) |
| `error` | `code`, `message` | 형식이 틀린 메시지(`BAD_MESSAGE`)·모르는 `type`(`UNKNOWN_TYPE`)·`rtc_*` 메시지(`RTC_DISABLED`). 연결은 유지 |

음성 글자 변환(STT)이 실패했을 때 같은 질문을 다시 내는 `stt_retry` 메시지는 **없다**(7-6, CONFLICTS A1).

### 7-5. 메시지 예

```json
{ "type": "question", "seq": 3, "kind": "base",
  "text": "최근 프로젝트에서 모델 성능을 높인 방법을 설명해 주세요.",
  "audio_url": "/api/media/questions/812", "answer_sec": 90, "progress": "3 / 10", "resend": false }

{ "type": "caption", "seq": 3, "answer_no": 1, "chunk_no": 7,
  "text": "저는 이전 프로젝트에서 데이터 불균형을", "is_final": false }

{ "type": "warn", "count": 1, "seq": 3, "remaining_sec": 47, "phase": "interview" }

{ "type": "terminate", "reason": "closed", "message": "마감이 되어 면접을 종료합니다." }
```

- 1번째 이탈 뒤에는 같은 질문을 멈춘 시점의 남은 시간부터 이어 답하고, 이탈 전후 음성을 합쳐 하나의 답변으로 채점한다(TRD 7-3). 화면정의서 v0.4 D-08로 확정했다(PRD CHT-02 개정 필요, 12장 A-02).
- 코딩테스트(`phase: "coding"`)는 1번째 이탈에도 코딩 시계를 멈추지 않는다. `warn`·`resume`의 `remaining_sec`은 그 순간 서버 시계로 계산한 값이고, 벗어나 있던 시간도 빠져 있다(TRD 7-3, C-18).
- `warn_ack`를 받으면 서버는 `session_events`에 `away_return`(judged `info`, 내용 '이탈 시간 N초')을 남긴다. 관리자 지원자 상세의 `events`로 보이며, 이탈 횟수(`away_count`)에는 넣지 않는다(PRD CHT-05, C-18).
- 장애로 판단된 구간에 생긴 이탈 신호는 세지 않는다. 면접과 코딩테스트의 이탈 횟수는 합쳐 센다.

### 7-6. 멈춤·다시 답변 규칙

**1번째 이탈 경고창(OV-02)이 떠 있는 동안**

- **화면**: `warn`을 받으면 마이크 트랙을 끄고(`track.enabled = false`) 타이머를 멈춘다. `resume`을 받으면 다시 켠다.
- **서버**: `warn`을 보낸 때부터 `resume`을 보낼 때까지 들어온 음성 조각은 Redis 스트림과 저장소에 넣지 않고 버린다. 그래야 이탈 전후를 이어 붙인 답변에 잡음이 섞이지 않는다.
- **heartbeat**: 숨겨진 탭에서는 브라우저가 타이머를 늦춰 heartbeat가 밀릴 수 있다. 멈춤 상태에서는 heartbeat 15초 누락을 바로 장애로 세지 않는다. 다만 경고창이 떠 있어도 120초 동안 아무 신호가 없으면 연결이 죽은 것으로 보고 평소처럼 판단한다. WebSocket이 비정상으로 닫히거나 `unload`가 오면 멈춤 중에도 평소처럼 판단한다.
- **다시 이탈**: 경고창이 떠 있는 동안 다시 이탈 신호가 오면 2번째 이탈로 보고 `terminate`(`cancelled`, `exit_twice`)를 보낸다(화면정의서 G-13, 임시 결정). 단 경고 직후 3초 안에 오는 신호(탭 전환 한 번에 `visibility`·`blur`가 따로 오는 경우)와 전체 화면 해제는 같은 이탈로 보고 세지 않는다.

**음성 글자 변환(STT) 실패(화면정의서 D-02, CONFLICTS A1)**

- 최종 글자 변환이 실패하면 설정 `stt_retry_limit`(2)번 다시 시도하고(한 번의 시도마다 `stt_attempt_timeout_sec` 제한), 그래도 실패하면 **장애 중단**으로 본다. 〔코드는 처음 시도 + 재시도 2번이라 CONFLICTS A1의 "1회 재시도"와 다름 — 논의사항 #1〕 상태를 `interrupted`로 바꾸고 WebSocket에 `paused`(`reason: "server_error"`)를 보낸 뒤 연결을 닫는다. 서버 쪽 원인이라 이어가기 횟수에 세지 않는다(7장·6장 resume 참고).
- 예전 명세서의 `stt_retry` 메시지(같은 질문을 3초 뒤 다시 내는 방식)와 "같은 질문에서 2번 연속이면 `paused`"라는 상한 제안은 쓰지 않는다. TRD 7-2·7-5(일시 중지·장애)를 따른다.

## 8. 코딩테스트 API

코딩테스트는 면접과 같은 세션(`sid`)을 쓴다. 2문제를 합쳐 60분이고, 시간은 서버가 잰다. 시간이 끝나면 서버가 마지막 저장 코드를 자동 제출한다.

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `GET /coding/{sid}` ➕ | 세션 | 문제 2개, 남은 시간, 마지막 저장 코드 | S-A10, S-A11 |
| `POST /coding/{sid}/start` ➕ | 세션 | 코딩테스트 시작(타이머 시작). 안내 화면에서 60초 뒤 자동으로도 부름 | S-A10 |
| `POST /coding/{sid}/run` | 세션 | 공개 예시로 실행 | S-A11 |
| `POST /coding/{sid}/autosave` | 세션 | 30초마다 자동 저장 | S-A11 |
| `POST /coding/{sid}/submit` | 세션 | 최종 제출 → 응시 완료 | S-A11 |

### GET /coding/{sid}

```json
{
  "started": true,
  "remaining_sec": 2841,
  "problems": [
    {
      "problem_no": 1,
      "title": "구간 합 최댓값",
      "statement": "…",
      "signature": "def solution(nums: list[int], k: int) -> int:",
      "examples": [ { "input": "[1, 3, 2], 2", "output": "5" } ],
      "limits": { "time_sec": 10, "memory_mb": 256 },
      "saved_code": "def solution(nums, k):\n    ...",
      "saved_at": "2026-11-03T10:31:30+09:00"
    }
  ]
}
```

숨겨진 테스트와 정답은 어떤 응답에도 넣지 않는다(TRD 9장). 이어가기 뒤에도 `remaining_sec`는 서버가 계산한 값이다(장애로 멈춘 동안은 시간이 흐르지 않는다).

응답에는 위 칸 말고도 `running`(타이머가 도는 중인지), `attempt_status`, `away_count`(이탈 횟수), `auto_start_sec`(안내 화면 자동 시작 초, 60), `release_at`이 들어 있다. 코딩테스트 단계가 아니면 409 `NOT_CODING`. 시간이 이미 끝났으면 서버가 자동 제출하고 409 `TIME_OVER`를 돌려준다.

### POST /coding/{sid}/run

요청 — `{ "problem_no": 1, "code": "…" }`

응답 200

```json
{
  "results": [ { "example_no": 1, "passed": true, "stdout": "5", "stderr": "", "time_ms": 41 } ],
  "status": "ok"
}
```

`status`: `ok` · `timeout`(10초) · `memory_exceeded`(256MB) · `runtime_error` · `syntax_error`. 예시 결과 항목에는 `expected`(기대값)·`actual`(실제값)도 들어 있고(공개 예시라 넣는다), 응답에는 오류 설명 `error`도 있다. 매번 새 실행 상자(인터넷 없음)에서 돌린다. 코드 실행은 `worker-sandbox`가 맡고 api는 docker.sock을 갖지 않는다(CONFLICTS B4). 실행 상자가 바쁘면 503 `SANDBOX_BUSY`, 실행 환경(작업 큐·상자)에 문제가 있으면 503 `SANDBOX_DOWN`.

### POST /coding/{sid}/autosave

요청 — `{ "problem_no": 1, "code": "…", "paste_blocked": 2 }` → 204. `paste_blocked`는 마지막 저장 뒤 새로 막은 외부 붙여넣기 시도 수로, 서버가 누적한다. 실패하면 화면이 1·2초 간격으로 3번 시도한 뒤 "코드를 자동 저장하지 못했습니다" 토스트만 띄운다. 서버에는 알리지 않으므로 장애 판정에는 연결되지 않고, 서버는 heartbeat 로만 판단한다. 〔설계 의도(장애 후보) 확인 필요: 논의사항 #25〕 시간이 끝난 뒤 들어온 저장은 받지 않고 마지막 저장 코드로 자동 제출한다(409 `TIME_OVER`).

### POST /coding/{sid}/submit

요청 — `{ "codes": [ { "problem_no": 1, "code": "…" }, { "problem_no": 2, "code": "…" } ] }`

응답 200 — `{ "attempt_status": "completed", "release_at": "2026-11-11T10:00:00+09:00" }`. 서버는 숨겨진 테스트로 채점하고 최종 채점·AI 결정 작업을 넣는다. 시간이 지났거나 이미 제출했으면 409 `TIME_OVER`(서버가 이미 자동 제출함). 코딩테스트 중이 아니면 409 `NOT_CODING`. 화면은 이어서 S-A12로 간다.

## 9. 마이페이지·결과·알림 API

지원자에게는 공개 시각 이후에만 결과를 주고, 점수·근거·이유는 어느 응답에도 넣지 않는다(RPT-03, AC-16).

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `GET /me/applications` ➕ | 🔒 | 내 지원 내역과 응시·공개 상태 | S-A13 지원 내역·결과 |
| `GET /me/results/{application_id}` | 🔒 | 공개된 결과(`public_view`). 공개 전 404 | S-A14 |
| `GET /notifications` ➕ | 🔒🛡 | 사이트 알림 최근 20건, 안 읽은 수 | 머리글 🔔 |
| `POST /notifications/{id}/read` ➕ | 🔒🛡 | 읽음 표시 | 머리글 🔔 |
| `POST /notifications/{id}/hide` ➕ | 🔒🛡 | 목록에서 지우기(숨김). 안 읽은 알림이면 읽음으로도 표시 | 머리글 🔔 |
| `POST /notifications/hide-read` ➕ | 🔒🛡 | 읽은 알림을 모두 목록에서 지우기(숨김) | 머리글 🔔 |

### GET /me/applications

```json
{
  "items": [
    {
      "application_id": "7b2e…",
      "posting": { "posting_id": "3a7e…", "title": "AI/AX 엔지니어", "close_at": "2026-11-10T18:00:00+09:00" },
      "attempt_status": "interrupted",
      "next_action": "resume",
      "phase": "interview",
      "session_id": "5d1c2f0e-…",
      "resume_until": "2026-11-10T18:00:00+09:00",
      "release_status": "scheduled",
      "release_at": "2026-11-11T10:00:00+09:00",
      "result_until": null,
      "applied_at": "2026-11-03T09:40:00+09:00",
      "consented": true,
      "connected": false
    }
  ],
  "total": 1, "page": 1, "size": 20
}
```

- `next_action`: `continue_draft` · `precheck` · `resume` · `view_result` · `null`. 화면은 이 값으로 카드 버튼을 그린다(화면정의서 §3.4). 이어가기는 `interrupted`에서만 나온다.
- `phase`(`interview` · `coding`)와 `session_id`(진행 중인 응시일 때 가장 최근 세션 번호, 아니면 `null`)는 화면이 어느 화면으로 이어 갈지 정하는 데 쓴다. `size` 최대 50.
- `consented`: 철회하지 않은 동의가 있으면 `true`. 계정 탭의 [동의 철회] 버튼이 이 값을 본다(CONFLICTS W2).
- 정렬에서 위 세 상태 말고는 최신 지원순이다.
- 정렬은 서버가 한다: `interrupted` → `ready` → `drafting` → 최신 지원순.
- `release_status`가 `delayed`면 "다음 날 10:00 공개"를 보여 준다(EVL-08). `result_until`은 공개 후 열람 끝 시각(공개 + 7일).
- 보관 기간이 지나 지워진 지원은 목록에서 빠진다.

### GET /me/results/{application\_id}

```json
{
  "application_id": "7b2e…",
  "posting": { "posting_id": "3a7e…", "title": "AI/AX 엔지니어" },
  "result": "fail",
  "attempt_status": "completed",
  "status_reason": null,
  "strengths": ["직무 개념을 정확히 설명함"],
  "improvements": ["경험을 수치와 함께 말하면 좋음"],
  "ai_generated": true,
  "contact_email": "recruit@example.com",
  "result_until": "2026-11-18T10:00:00+09:00",
  "status": "released"
}
```

- `result`: `pass` · `fail`. `strengths`·`improvements`는 각 최대 3개.
- `status_reason`: 응시 취소면 `cheating_cancelled`, 마감 종료면 `closed`, 장애 아님 종료면 `ended`, 3일 안에 평가를 못 끝내 불합격 처리됐으면 `evaluation_incomplete`, 담당자가 정했으면 `manual_decision`. 뒤의 두 경우 `ai_generated` 는 false 이고 강점·개선점은 빈 배열이다.
- 공개 전·남의 지원·보관 만료는 모두 404 `NOT_FOUND`다. 화면은 `GET /me/applications`의 `release_at`으로 "아직 공개되지 않았습니다"와 "보관 기간이 지났습니다"를 구분한다.

**미응시(마감) 표시**: `not_taken_closed`는 평가 결과가 없어서 이 API는 항상 404다. 화면은 `GET /me/applications`에서 `attempt_status: "not_taken_closed"`를 보고 결과 탭에 "미응시(마감) — 접수 마감까지 응시하지 않아 평가되지 않았습니다"를 보여 준다(INT-10). 이때 `next_action`은 `null`, `release_status`는 `released`가 되지 않으며, 카드는 다른 지원과 같은 삭제 예정일에 사라진다.

### GET /notifications

```json
{
  "unread": 2,
  "items": [
    { "notification_id": "…", "kind": "result_released", "title": "1차 결과가 공개되었습니다",
      "link": "/mypage/results/7b2e…", "read": false, "created_at": "…" }
  ]
}
```

`kind` — 지원자: `result_released` · `deadline_reminder` · `result_expiring`. 관리자: `posting_closing` · `purge_notice` · `needs_review`. 신규 지원 알림은 두지 않는다(화면정의서 D-10, TRD 10장). 메일 보내기가 실패해도 사이트 알림은 항상 남는다(TRD 10장).

- 목록은 숨기지 않은 알림만 최근 20건이다. `hide`·`hide-read`로 숨긴 알림은 다시 나오지 않는다(`notifications.hidden_at`). `hide`는 204, `hide-read`는 200 `{ "hidden": 지운 수 }`. 남의 알림이면 404.
- **알림 링크(CONFLICTS S6)**: 화면정의서에 링크 주소가 없어 실제 화면 주소로 맞췄다. 결과 공개 알림은 `/mypage/results/{application_id}`, 마감 하루 전 관리자 알림은 `/admin/applicants?posting={posting_id}`다.
- 하루 메일 상한(`mail_daily_limit`)은 아직 없다. 현재 구현 범위 밖(미구현)이다(CONFLICTS S5).

## 10. 관리자 API

관리자는 결과와 결정을 읽기만 한다. 바꿀 수 있는 것은 메모·설정·다시 돌리기 세 가지다(EVL-05, AC-14). 예외로 '평가 지연' 건에는 결과를 처음 정할 수 있다(`/decision`). 주소의 `{aid}`는 지원 1건의 `application_id`다.

| 방식 · 주소 | 권한 | 하는 일 | 화면 |
| --- | --- | --- | --- |
| `GET /admin/postings/{id}/applicants` | 🛡 | 공고별 지원자 목록·점수·판정 | S-R05 |
| `GET /admin/applicants/{aid}` | 🛡 | 지원자 상세: 리포트·질문별 답변·이력서·코딩·기록·메모 | S-R06 |
| `GET /admin/applicants/compare?ids=` | 🛡 | 2\~3명 비교 | S-R07 |
| `POST /admin/applicants/{aid}/memo` | 🛡 | 내부 메모 쓰기 | S-R06 |
| `PATCH /admin/memos/{memo_id}` ➕ | 🛡 | 메모 고치기 | S-R06 |
| `DELETE /admin/memos/{memo_id}` ➕ | 🛡 | 메모 지우기 | S-R06 |
| `GET /admin/postings/{id}/passed` ➕ | 🛡 | 1차 합격자 목록·연락처 | S-R08 |
| `POST /admin/analysis/{aid}/reprocess` | 🛡 | '평가 지연' 건 다시 돌리기 | S-R05, S-R06, S-R09 |
| `POST /admin/analysis/{aid}/decision` | 🛡 | '평가 지연' 건 직접 결정 (3일 안, 사유 필수) | S-R06 |
| `GET /admin/stats` ➕ | 🛡 | 집계 통계(개인 정보 없음) | S-R09 |
| `GET /admin/ops-status` ➕ | 🛡 | 확인 필요 목록, 메일 실패, 예비 질문 수, 로그인 차단 목록(`login_blocks`: code·fail_count·blocked_at·blocked_until) | S-R09 |
| `POST /admin/login-blocks/{code}/release` ➕ | 🛡 | 로그인 차단 해제. 204, 없으면 404. 감사 로그 `login_block.release` | S-R09 |
| `GET /admin/settings` ➕ | 🛡 | 현재 N, 진행 중 수, 최근 변경 | S-R10 |
| `PUT /admin/settings/{key}` | 🛡 | 설정 바꾸기(감사 로그) | S-R10 |

### GET /admin/postings/{id}/applicants

쿼리 — `result`(`undecided` · `pass` · `fail`) · `analysis_status`(`pending` · `running` · `decided` · `needs_review`) · `sort`(`total_score` · `interview_score` · `coding_score` · `applied_at`, 앞에 `-`면 내림차순, 기본 `-applied_at`) · `page` · `size`(기본 50, 최대 200). 그 밖의 정렬 값은 400 `INVALID_SORT`. 작성 중(`drafting`) 지원은 목록에 나오지 않는다. 〔`attempt_status` 쿼리는 코드에 없음〕

```json
{
  "posting": { "posting_id": "3a7e…", "title": "AI/AX 엔지니어", "status": "published" },
  "items": [
    {
      "application_id": "7b2e…",
      "name": "홍길동",
      "email": "hong@example.com",
      "attempt_status": "completed",
      "analysis_status": "decided",
      "review_reason": null,
      "submitted_at": "2026-11-03T09:40:00+09:00",
      "completed_at": "2026-11-03T10:40:00+09:00",
      "away_count": 0,
      "fault_count": 1,
      "interview_score": "72.50",
      "coding_score": "60.00",
      "total_score": "68.75",
      "decision": "fail",
      "purge_at": "2026-11-18T10:00:00+09:00"
    }
  ],
  "has_coding_test": true,
  "total": 24, "page": 1, "size": 50
}
```

`posting`은 공고 객체(4장)다. `away_count`는 화면 이탈로 기록된 건수, `fault_count`는 장애로 판정된 끊김 건수다(관리자 화면의 ⚡n 표시). 분석 전 행은 점수·`decision`이 `null`이다. `not_taken_closed` 행도 `null`이며 통계에서 빠진다. 〔예전 명세서의 `records`(`resumed`·`exits`·`ended_by_close`) 칸은 `away_count`·`fault_count`로 바뀌었다〕

### GET /admin/applicants/{aid}

```json
{
  "application_id": "7b2e…",
  "applicant": { "name": "홍길동", "email": "hong@example.com", "phone": "010-1234-5678" },
  "posting": { "posting_id": "3a7e…", "title": "AI/AX 엔지니어", "criteria": { } },
  "attempt_status": "completed",
  "analysis_status": "decided",
  "review_reason": null,
  "release_status": "scheduled",
  "release_at": "2026-11-11T10:00:00+09:00",
  "purge_at": "2026-11-18T10:00:00+09:00",
  "result": {
    "decision": "fail",
    "reason": "직무 이해는 좋지만 구체적인 근거가 부족했다. …",
    "quotes": ["먼저 원인을 확인하고 그다음 방법을 골랐습니다"],
    "item_scores": { "expertise": "80.00", "logic": "65.00", "relevance": "70.00", "delivery": "75.00", "culture_fit": "60.00" },
    "interview_score": "72.50", "coding_score": "60.00", "total_score": "68.75", "pass_score": "70.00",
    "strengths": ["…"], "improvements": ["…"], "summary": "…",
    "decision_check": "ok", "model_version": "rt:… eval:…", "prompt_version": "eval-v1", "rubric_version": "prd-1.6-5-7",
    "decided_at": "2026-11-03T11:00:00+09:00"
  },
  "highlights": [ { "seq": 3, "kind": "good", "item": "expertise", "start_ms": 12400, "end_ms": 19800, "quote": "…", "media_url": "/api/admin/media/answers/a91c…" } ],
  "instruction_hits": [ { "seq": 3, "phrase": "…" } ],
  "resume": { "education": [ ], "career": [ ], "projects": [ ], "skills": [ ], "certificates": [ ], "cover_letter": null },
  "resume_method": "upload",
  "edited_fields": ["career[0].company"],
  "submitted_at": "2026-11-03T09:40:00+09:00",
  "completed_at": "2026-11-03T10:40:00+09:00",
  "questions": [
    {
      "seq": 3, "kind": "base", "qtype": "job", "text": "…", "source": "generated",
      "substituted": false, "substitute_reason": null, "regen_count": 0, "followup_reason": null,
      "asked_at": "2026-11-03T10:05:00+09:00",
      "scores": [ { "item": "expertise", "score": 4, "quote": "클래스 가중치를 조정해 재현율을 높였습니다", "quote_verified": true } ],
      "answer": { "transcript": "…", "audio_sec": 62.4, "end_reason": "done", "media_url": "/api/admin/media/answers/a91c…" }
    }
  ],
  "events": [ { "type": "disconnect", "detail": "heartbeat_timeout", "judged": "fault", "seq": 3, "at": "2026-11-03T10:07:42+09:00" } ],
  "coding": [ { "problem_no": 1, "code": "…", "passed": 8, "total": 10, "paste_blocked": 2, "grade_status": "…", "saved_at": "…", "feedback": "…" } ],
  "recordings": [ { "segment_no": 1, "media_url": "/api/admin/media/recordings/7b2e…/1", "size_bytes": 5242880, "started_at": "…", "last_chunk_at": "…" } ],
  "recording_until": "2026-11-06T10:40:00+09:00",
  "memos": [ { "memo_id": "…", "body": "…", "created_at": "…", "updated_at": null } ]
}
```

- 분석이 끝나지 않았으면 `result`가 `null`이고 `analysis_status`를 함께 준다. 이력서·기록은 그대로 보인다.
- `questions[]`는 기본 질문과 꼬리질문(`kind: follow_up`)을 질문 번호·답변 순서대로 한 줄씩 담는다. `scores`는 기본 질문 줄에만 들어간다. `qtype`은 `personality` · `company` · `job` · `resume`, `source`는 `generated`(RAG로 만든 질문) · `excel`(질문은행) · `reserve`(예비 질문), 질문은행·예비로 바꾼 경우 `substituted`와 이유(`substitute_reason`)를 준다(CONFLICTS U5). 예전 명세서의 `answers[]`·`follow_ups[]`는 이 `questions[]`로 합쳤다.
- `highlights.kind`: `good`(4\~5점) · `deducted`(1\~2점). 각 최대 3개(TRD 8-4). `quote`는 근거 문장이다.
- 코딩 `feedback`은 점수에 반영하지 않는다. 숨겨진 테스트 내용은 넣지 않는다. 코딩은 문제 목록(배열)이고 점수는 `result.coding_score`에 있다.
- `events`의 `type`은 이탈(`visibility` · `blur` · `fullscreen` · `navigate`, `judged: cheating`)·`disconnect`·`interrupted`·`unload`·`permission`·`device_error`·`resume_limit` 등이다. `judged`는 `cheating` · `fault` · `not_fault` · `info`다(CONFLICTS T2).
- `instruction_hits`: 답변에 채점 지시로 보이는 구절이 있으면 질문 번호와 앞뒤 15자씩 포함한 구절(관리자 확인용). 없으면 빈 배열이다.
- 이 API를 부르면 '결과 보기' 감사 로그(`applicant.view`)가 남는다.
- 원본 이력서 파일과 표준 양식 이력서는 저장소에 보관하지만 이 API로는 볼 수 없다. 관리자 원본 보기 API는 현재 구현 범위 밖(미구현)이다.

### 메모

- `POST /admin/applicants/{aid}/memo` — `{ "body": "…" }` → 201 메모 객체.
- `PATCH /admin/memos/{memo_id}` — `{ "body": "…" }` → 200. `DELETE` → 204.
- 1\~2000자. 공백뿐이면 400 `MEMO_EMPTY`. 지원자 응답에는 절대 넣지 않는다(ADM-05).
- 감사 로그는 `memo.create` · `memo.update` · `memo.delete`로 남기고 본문은 남기지 않는다(`memo_id`만, CONFLICTS M1).

### GET /admin/applicants/compare · GET /admin/postings/{id}/passed

- `compare` — 쿼리 `ids=a,b,c`(쉼표로 구분, 2~3개). 아니면 400 `COMPARE_COUNT`. 응답은 `{ "items": [ { application_id, name, posting_id, posting_title, attempt_status, analysis_status, decision, total_score, interview_score, coding_score, pass_score, item_scores, strengths, improvements } ], "same_posting": true }`. 서로 다른 공고도 비교는 되지만 `same_posting: false`로 알려 화면이 "기준이 달라 비교 어려움" 경고를 띄운다. 목록 화면에서는 같은 공고 안에서만 고른다. 감사 로그 `applicant.compare`.
- `passed` — 쿼리 `q`(이름 검색, 선택). 응답은 `{ "posting": {…}, "items": [ { application_id, name, email, phone, total_score, decided_at, purge_at } ], "undecided": 아직 판정 안 난 응시 수, "purge_at": 가장 이른 삭제 예정일 }`. 1차 합격자는 결과 공개 전에도 관리자에게 보인다(지원자 목록과 같은 기준). 연락처를 보여 주므로 열 때마다 감사 로그 `passed.view`를 남긴다(CONFLICTS F7).

### POST /admin/analysis/{aid}/reprocess

요청 본문 없음. 응답 202 — `{ "analysis_status": "running" }`. 같은 응시 자료로 채점·결정을 처음부터 다시 돌리고, 판정을 사람이 고치지는 않는다. 감사 로그는 `analysis.reprocess`이고, 사유가 `instruction_suspected`이면 `analysis.reprocess_ack_instruction`(걸린 구절의 해시 포함)이다.

**채점 지시 의심(`instruction_suspected`)**: 답변에 "만점 주세요", "합격시켜", "이전 지시 무시", "채점 기준 바꿔", "ignore previous instructions" 같은 말이 있으면 채점하지 않고 '평가 지연'(`instruction_suspected`)로 두며 관리자에게 알린다. 상세(`GET /admin/applicants/{aid}`)의 `instruction_hits`에 걸린 구절이 보이고, 관리자가 [확인했습니다, 채점하기](이 reprocess 호출)를 누르면 확인 기록을 남기고 그대로 채점한다. 결과를 사람이 고치는 것은 아니다(EVL-05 유지). 확인은 그때 본 구절에만 유효하다. 'AI'·'프롬프트' 같은 낱말만으로는 걸지 않고, 쉬운 표현만 잡는 보조 장치이며 실제 방어는 구분자 바꾸기·JSON 형식·근거 확인이 맡는다. 응시 취소 건은 검사하지 않는다. 다시 돌릴 때도 검증은 같다: ① 형식 ② 값 범위 ③ 근거 문장이 원문에 있음 ④ 판정이 '총점 ≥ 합격 기준'과 일치(D-06). 하나라도 틀리면 1회 다시 판정하고, 그래도 틀리면 다시 `needs_review`가 된다. `needs_review`가 아니면 409 `NOT_NEEDS_REVIEW`.

### POST /admin/analysis/{aid}/decision

요청 `{ "decision": "pass" | "fail", "reason": "10~1000자" }`. 응답 200 — `{ "analysis_status": "decided", "decision": "pass", "release_at": "..." }`.
`analysis_status` 가 `needs_review` 인 건만 된다. 아니면 409 `NOT_NEEDS_REVIEW`(이미 정해진 결과는 바꿀 수 없음). 사유가 짧으면 400 `REASON_TOO_SHORT`.
`results.decision_check` 는 `manual`, 점수는 응답에서 null 이다. 감사 로그는 `analysis.manual_decision`(결정만 기록, 사유 글은 넣지 않음). 사유는 관리자에게만 보인다.
3일 안에 결정이 없으면 AI 가 정상일 때 마지막 재채점까지 실패한 뒤(늦어도 7일) 5분 점검이 `decision_check = incomplete` 인 불합격으로 닫는다(감사 로그 `analysis.auto_fail`, 고정 문구, LLM 호출 없음).
응답의 `review_deadline`(`GET /admin/applicants/{aid}`)이 그 기한이다. `reprocess` 를 눌러도 기한은 늘어나지 않는다.

### GET /admin/stats · /ops-status

- `stats` 쿼리 — `posting_id`(없으면 전체). 응답은 `applications`(지원 수)·`taken`(응시 수)·`taken_this_month`·`completion_rate`(응시 완료율)·`pass_rate`·`average_total`·`item_averages`(항목별 평균)·`score_bins`(10점 구간 10칸 `{from,to,count}`)·`resumed`(이어가기 수)·`cheating_cancelled`(부정행위 취소)·`monthly`(최근 12개월 응시 수)·`postings`(공고별 응시 수·합격률·평균 총점)다. 이름·연락처는 없다. 미응시(마감)는 뺀다.
- 보관 기간이 지나 지운 건은 지울 때 월별 숫자만 `stats_archive`에 더해 두고 `/admin/stats`가 남은 건과 합쳐 보여 준다. 지원 건·회원 정보는 남기지 않고 공고를 지워도 숫자는 남는다(CONFLICTS F1). 철회·탈퇴 건은 응시가 끝난 건만 더한다(CONFLICTS W1).
- `ops-status` 응답:

```json
{
  "needs_review": [ { "application_id": "…", "name": "홍길동", "posting_title": "…", "since": "…", "reason": "threshold_mismatch" } ],
  "mail_failed": { "count": 3, "items": [ { "to": "ho***@example.com", "kind": "result_released", "title": "…", "reason": "550 no such user", "at": "…" } ] },
  "mail_deferred_today": 0,
  "questions": { "bank": 5900, "reserve_total": 21 },
  "reserve_questions": [ { "category": "personality", "count": 5, "below_minimum": false } ],
  "coding_problems": { }
}
```

`mail_failed`는 최근 7일 최종 실패, `mail_deferred_today`는 오늘 미룬 메일 수다(하루 상한 기능이 없어 지금은 거의 0). `reserve_questions[].category`는 질문 종류(`personality` · `company` · `resume` · `job`)이고 5개 미만이면 `below_minimum`이 `true`다. `coding_problems`는 난이도별 문제 수다.

`needs_review[].reason` 값: `threshold_mismatch`(AI 판정이 합격 기준과 어긋나 1회 다시 판정해도 같음, 화면정의서 D-06) · `invalid_format`(형식·값 범위 검증 실패) · `quote_not_found`(근거 문장이 원문에 없음) · `analysis_timeout`(3회 재시도·30분 초과) · `sandbox_error`(코드 실행 환경 오류) · `instruction_suspected`(답변에 채점 지시로 보이는 말이 있어 채점하지 않음, 이전 명세서 사유 목록에 없던 새 값. 위 reprocess 참고). 화면은 이 값으로 평가 지연 사유를 보여 준다.

### GET /admin/settings · PUT /admin/settings/{key}

`GET` 응답

```json
{
  "max_concurrent_interviews": 2,
  "active_interviews": 1,
  "history": [ { "key": "max_concurrent_interviews", "from": 3, "to": 2, "at": "…" } ],
  "items": { }
}
```

- `active_interviews`는 지금 자리를 잡고 있는 면접 수(AI 면접 진행 + 끊긴 지 10분 이내 장애 중단)다. `history`는 최근 10건이고 별도 설정 기록 테이블이 아니라 감사 로그(`settings.change`)의 전·후 값을 읽는다(CONFLICTS F8). `items`는 모든 설정의 현재 값이다.
- `PUT` 요청 — `{ "value": 3 }` → 200 `{ "key": "max_concurrent_interviews", "value": 3 }`. 다음 시작 요청부터 바로 적용되고, 이미 진행 중인 면접은 끊지 않는다(TRD 5-3). 본문에 `value` 말고 다른 칸이 있거나 정수가 아니면(불리언 포함) 400 `INVALID_SETTING`.
- **설정 API로 바꿀 수 있는 키는 `max_concurrent_interviews` 하나이고 범위는 1~20이다**(CONFLICTS F10·D2). 그 밖의 키(TRD 14장)는 서버 설정 파일에서 관리하며, 이 API로 보내면 400 `INVALID_SETTING`이다. 아예 없는 키는 404, 범위 밖은 400 `INVALID_SETTING`이다. 〔상한 20은 사용자 확인, 2026-10-30〕
- 예전 명세서의 응답 칸 `admission_guard`(`open` · `blocked`)는 **없다**. 자동 보호로 입장을 막는 기능이 구현되지 않았기 때문이다(CONFLICTS F6). 현재 구현 범위 밖(미구현)이며 필요하면 정의가 필요하다.

## 11. 오류 코드 목록

화면은 아래 `code`로 안내 문구를 고른다. 문구는 화면정의서의 문구를 기준으로 하고, 서버의 `message`는 개발자 확인용이다.

| 분야 | code | HTTP | 화면 안내 |
| --- | --- | --- | --- |
| 공통 | `LOGIN_REQUIRED` | 401 | 로그인 화면으로(현재 주소를 `next`로). 예전 명세서의 `UNAUTHORIZED`는 구현에서 `LOGIN_REQUIRED`로 쓴다 |
| 공통 | `FORBIDDEN` | 403 | 접근할 수 없는 페이지입니다 |
| 공통 | `NOT_FOUND` | 404 | 찾을 수 없는 정보입니다 |
| 공통 | `VALIDATION_ERROR` | 422 | 입력값을 확인해 주세요 (`message`에 칸 이름) |
| 공통 | `SERVER_ERROR` | 500 | 잠시 후 다시 시도해 주세요 |
| 공통 | `AI_UNAVAILABLE` | 503 | AI 서버를 확인하지 못했습니다 |
| 계정 | `PASSWORD_POLICY` | 400 | 비밀번호 규칙 체크리스트에 ✕ 표시 |
| 계정 | `AGREEMENT_REQUIRED` | 400 | 필수 항목에 모두 동의해 주세요 |
| 계정 | `EMAIL_TAKEN` | 409 | 이미 가입된 이메일입니다 |
| 계정 | `INVALID_CREDENTIALS` | 401 | 이메일 또는 비밀번호가 올바르지 않습니다 |
| 계정 | `LOGIN_BLOCKED` | 429 | 로그인 실패가 반복되어 이 네트워크의 로그인을 제한했습니다 (문의 코드 포함) |
| 계정 | `TOKEN_EXPIRED` | 400 | 링크가 만료되었습니다 |
| 계정 | `WRONG_PASSWORD` | 400 | 현재 비밀번호가 맞지 않습니다 (탈퇴 때는 비밀번호가 맞지 않습니다) |
| 계정 | `CONFIRM_TEXT` | 400 | 확인란에 '탈퇴'를 입력해 주세요 (`POST /me/withdraw`) |
| 계정 | `SAME_AS_OLD` | 400 | 이전과 다른 비밀번호를 입력해 주세요 |
| 계정 | `PASSWORD_CHANGE_REQUIRED` | 403 | 초기 비밀번호 변경 화면(S-C04)으로 |
| 계정 | `EMAIL_NOT_VERIFIED` | 403 | 이메일 인증 후 지원할 수 있습니다 (이메일 인증 미구현이라 현재 나오지 않음) |
| 공고 | `CRITERIA_LOCKED` | 409 | 🔒 첫 응시가 시작되어 평가 기준을 바꿀 수 없습니다 |
| 공고 | `WEIGHT_SUM` | 400 | 합계가 100%가 되어야 합니다 |
| 공고 | `POSTING_INCOMPLETE` | 400 | 빈 필수 칸으로 스크롤 |
| 공고 | `JOB_NOT_OPEN` | 400 | 아직 준비 중인 직무입니다 |
| 공고 | `HAS_APPLICANTS` | 409 | 지원자가 있는 공고는 삭제할 수 없고 마감만 가능합니다 |
| 공고 | `CODING_RATIO` | 400 | 코딩테스트 반영 비율은 10% 단위(10~90)여야 합니다 |
| 공고 | `ALREADY_PUBLISHED` | 409 | 이미 게시했거나 마감된 공고 / AI 초안은 임시저장 공고에만 |
| 공고 | `CRITERIA_MISSING` | 409 | 이 공고의 평가 기준을 찾을 수 없습니다 |
| 공고 | `NOT_PUBLISHED` | 409 | 게시 중인 공고만 마감할 수 있습니다 |
| 공고 | `DRAFT_RUNNING` | 409 | 이미 초안을 만들고 있습니다 |
| 공고 | `IMPORT_SOURCE_FAILED` | 502 | 공고를 불러오지 못했습니다 (공고 불러오기 미구현이라 현재 나오지 않음) |
| 지원 | `ALREADY_APPLIED` | 409 | 이미 지원한 공고입니다 |
| 지원 | `POSTING_CLOSED` | 409 | 마감이 되어 면접을 진행할 수 없습니다 |
| 지원 | `CONSENT_VERSION_CHANGED` | 409 | 동의 문구가 바뀌었습니다. 다시 확인해 주세요 |
| 지원 | `CONSENT_REQUIRED` | 409 | 필수 동의를 먼저 해 주세요 (이력서 확정 때) |
| 지원 | `NO_CONSENT` | 409 | 철회할 동의가 없습니다 (`POST /applications/{id}/consent/withdraw`) |
| 이력서 | `UNSUPPORTED_FILE` | 400 | 이력서를 불러오는 데 실패했습니다 (실패 모달) |
| 이력서 | `FILE_TOO_LARGE` | 413 | 이력서를 불러오는 데 실패했습니다 (실패 모달, 용량 숫자는 말하지 않음). PDF 50MB·사진 15MB 초과. 본문을 받기 전에 Content-Length 로 거절하며, 길이가 없으면 411 `LENGTH_REQUIRED` |
| 이력서 | `PDF_ENCRYPTED` | 400 | 열람 암호가 걸린 PDF |
| 이력서 | `PDF_BROKEN` | 400 | 손상되어 열 수 없는 PDF |
| 이력서 | `PDF_TOO_COMPLEX` | 400 | 시간(30초)·메모리 제한을 넘겼거나 리더가 비정상 종료한 PDF |
| 이력서 | `RESUME_REQUIRED_MISSING` | 422 | 빠진 항목으로 스크롤 + 빨간 테두리 |
| 이력서 | `RESUME_LOCKED` | 409 | 제출한 이력서는 수정할 수 없습니다 |
| 지원 | `APPLICATION_LOCKED` | 409 | 제출한 지원서에는 동의를 다시 할 수 없습니다 |
| 이력서 | `UPLOAD_REQUIRED` | 400 | 올린 이력서 파일을 찾을 수 없습니다 |
| 면접 | `CAPACITY_FULL` | 429 | 동시 면접 인원이 찼습니다. 응시 기회는 그대로입니다 + \[다시 시도\] (자동 보호는 미구현, CONFLICTS F6) |
| 면접 | `PRECHECK_REQUIRED` | 409 | 환경 점검(S-A06)으로 |
| 면접 | `NOT_READY` | 409 | 지원 절차를 마쳐 주세요 |
| 면접 | `ALREADY_ATTEMPTED` | 409 | 이미 응시한 면접입니다 |
| 면접 | `NOT_INTERRUPTED` | 409 | 이어갈 수 있는 면접이 없습니다 |
| 면접 | `STORAGE_UNAVAILABLE` | 503 | 녹화를 저장하지 못했습니다(화면이 다시 올림, 서버 쪽 장애로 기록, CONFLICTS R5) |
| 면접 | `NOT_IN_PROGRESS` · `SEGMENT_MISMATCH` · `INVALID_FILE` | 409 · 409 · 400 | 녹화 조각 거절(진행 중이 아님·구간 번호 불일치·WebM 아님). 화면은 그 조각만 버리고 장애로 보지 않음 |
| 코딩 | `SANDBOX_BUSY` | 503 | 잠시 후 다시 실행해 주세요 |
| 코딩 | `SANDBOX_DOWN` | 503 | 코드 실행 환경에 문제가 있습니다. 잠시 후 다시 실행해 주세요 |
| 코딩 | `NOT_CODING` | 409 | 코딩테스트 단계가 아닙니다 |
| 코딩 | `TIME_OVER` | 409 | 시간이 끝나 자동 제출되었습니다 |
| 관리자 | `MEDIA_EXPIRED` | 410 | 보관 기간 만료(녹화) |
| 관리자 | `NOT_NEEDS_REVIEW` | 409 | 재처리 대상이 아닙니다 |
| 관리자 | `INVALID_SETTING` | 400 | 화면에서 바꿀 수 없는 설정이거나 형식이 맞지 않음, 범위 밖(1~20을 입력해 주세요) |
| 관리자 | `INVALID_SORT` | 400 | 정렬 기준이 올바르지 않습니다 |
| 관리자 | `COMPARE_COUNT` | 400 | 2~3명을 골라 주세요 |
| 관리자 | `MEMO_EMPTY` | 400 | 메모 내용을 입력해 주세요 |
| WebSocket | `BAD_MESSAGE` · `UNKNOWN_TYPE` · `RTC_DISABLED` | — | WebSocket `error` 메시지의 `code`(HTTP 상태 없음). 형식 오류·알 수 없는 메시지·WebRTC 메시지 거절 |
| 공고 | FIELD\_LOCKED\_AFTER\_PUBLISH | 409 | 게시 중인 공고에서는 이 항목을 고칠 수 없습니다 (G-14) |

## 12. 확인 필요 사항

문서끼리 말이 다르거나 어느 문서에도 없는 것은 아래처럼 임시로 정했다. 팀이 정하면 이 문서와 해당 문서를 같이 고친다.

| # | 항목 | 문서별 내용 | 이 문서의 선택 | 고칠 문서 |
| --- | --- | --- | --- | --- |
| A-01 | 기준 PRD 버전 | TRD v1.5·화면정의서 v0.4는 PRD v1.6 기준, 팀에 공유된 PRD는 v1.3 | TRD v1.5 + 화면정의서 v0.4 결정(D-01\~D-10)을 따름 | PRD v1.6 공유 후 다시 대조 |
| A-02 | 1번째 화면 이탈 뒤 답변 시간 | PRD v1.3 CHT-02: 새로 부여 / TRD 7-3·화면정의서 D-08: 남은 시간부터 | **해결(D-08)**. `warn`·`resume`에 `remaining_sec`, 멈춘 동안의 음성은 버림(7-6) | PRD CHT-02, TRD 7-3(음성 버리기 명시) |
| A-03 | 음성 글자 변환 최종 실패 | PRD INT-04·화면정의서 D-02: 같은 질문 다시 답변 / TRD 7-2·7-5: 장애 | ~~해결(D-02). `stt_retry` 후 같은 질문, 같은 질문에서 2번 연속이면 `paused`~~ → **v1.2: TRD를 따름.** 다시 시도해도 실패하면 장애 중단(`paused`, `server_error`). `stt_retry` 메시지 없음(CONFLICTS A1) | TRD 7-2·7-5 |
| A-04 | 자리 꽉 참 오류 코드 | TRD 4-3 `SEATS_FULL` / 5-3·화면정의서 §12 #27 `CAPACITY_FULL` | **해결**. `CAPACITY_FULL` | TRD 4-3 |
| A-05 | 관리자 공고 경로 | TRD 5-1은 `POST /postings` 표기 + "/admin 아래" 설명 | `/admin/postings/…`로 통일 | TRD 5-1, 화면정의서 S-R01·S-R03 |
| A-06 | 답변 음성 올리기 | 화면정의서 v0.2의 파일 업로드 API / TRD v1.5: WebRTC | **해결**. v0.4에서도 빠짐. 파일 API 없음. v1.2: WebRTC 대신 WebSocket 이진 메시지(16kHz PCM)로 보낸다(CONFLICTS V4) | TRD 5-2 수정 또는 승인 |
| A-07 | 장애 판단 시점 | 화면정의서 v0.2 S-A15: 들어와서 판단 / TRD 7-2: 끊긴 뒤 15초에 바로 | **해결(D-09)**. `interview/state`는 결과를 읽기만 함, 브라우저가 살아 있는 '장애 아님'은 `terminate`(`ended`, detail)로 OV-07 | TRD 5-2(terminate 사유 값) |
| A-08 | 응시 상태 칸·값 이름 | TRD에는 `not_taken_closed`·`ended_closed`·`needs_review`만, 화면정의서는 `drafting`까지, 기술 아키텍처는 칸 이름을 `exam_status`로 씀 | 2-4의 값, 칸 이름은 `attempt_status` | 테이블 정의서, 기술 아키텍처 5-2 |
| A-09 | 결과 화면 문의 이메일 | 화면정의서 D-03: 공고에 `contact_email` / PRD N7·RPT-03에는 없음 | 공고·결과 응답에 `contact_email` 넣음 | PRD N7·RPT-03(O-06), TRD 4-1 |
| A-10 | AI 초안 출처·차별 표현 | TRD `source`는 `manual`·`open_api`·`dummy`만, 차별 표현은 화면정의서 O-05에서 규칙 기반 사전으로 설계 | `ai_draft` 추가, `bias_warnings`(규칙 기반 사전으로 구현) | TRD 4-1·15장 T-08 |
| A-11 | 녹화 올리기 | TRD에 경로 없음 / 기술 아키텍처 ADR-04: MediaRecorder 10초 WebM 조각 REST | `POST /interview/{sid}/recording`, 10초 조각 | TRD 5-1 |
| A-12 | 코딩테스트 시작 | 화면정의서 G-03: 안내 화면 + 60초 뒤 자동 시작 / TRD에 없음 | `POST /coding/{sid}/start` 추가 | TRD 9장 |
| A-13 | 접속 범위·호스트 | TRD·기술 아키텍처 ADR-01: 127.0.0.1만 | `localhost`는 127.0.0.1로 리다이렉트, Origin·`ws_url`은 127.0.0.1 하나(2-5). 다른 PC 접속으로 바꾸면 HTTPS·`cookie_secure`·WebRTC 주소를 바꿈 | PRD 10-2(전제) |
| A-14 | AI 판정 검증 | TRD 1-2·8-2⑤: 기준 비교 안 함 / 화면정의서 D-06: 기준과 어긋난 판정은 확정하지 않음 | **D-06을 따름**. 1회 다시 판정 → `needs_review`(`threshold_mismatch`) | TRD 1-2·8-2⑤ |
| A-15 | 신규 지원 알림 | PRD ADM-08: 있음 / TRD 10장·화면정의서 D-10: 없음 | **해제(D-10)**. `new_application` 삭제 | PRD ADM-08 |
| A-16 | Next.js 프록시 본문 크기·응답 시간 제한 | 미들웨어(`proxy.ts`)가 걸린 경로는 본문 기본 10MB, rewrites에도 응답 시간 제한이 있음 | `/api`는 `proxy.ts` matcher에서 뺌(구현됨, 2-5). 미디어도 `/api` 아래라 같은 규칙. 응답 시간 제한은 실측하지 않음 | 없음 |
| A-17 | 경고창 중 다시 이탈 | PRD·TRD에 정의 없음 / 화면정의서 G-13: 2번째 이탈 | G-13(임시 결정)을 따름(7-6) | PRD CHT-02·TRD 7-3 |
| A-18 | 게시 후 공고 수정 | PRD JOB-07은 기준 잠금만 / 화면정의서 G-14: 허용 항목만, 수정 사항 표시 | `posting_revisions`·`revisions[]`, `FIELD_LOCKED_AFTER_PUBLISH`(4장) | PRD JOB-01·07, TRD 4-1 |
| A-19 | sendBeacon 수신 경로 | 기술 아키텍처 6-4: `POST /sessions/{sid}/beacon` 예시 / 화면정의서 §12 #11: `POST /interview/{sid}/events` | `POST /interview/{sid}/events` 유지, 본문은 Content-Type과 상관없이 JSON으로 풀어 받음(6장) | 기술 아키텍처 6-4, TRD 5-1 |

### v1.2 변경 기록 (개인용 개정본, 2026-11-03)

기준은 구현(`huge/backend/app`)과 `huge/CONFLICTS.md`다. 팀 원본 v1.1은 고치지 않았다. 아래에 없는 API는 v1.1과 같다. 앞의 A-xx는 v1.1까지의 기록이다.

| 경로·항목 | 변경 | 근거 |
| --- | --- | --- |
| 머리말·1장·2장 | 버전 v1.2·개인용 표시, 기준 문서 TRD v1.6 · PRD v1.7 · 화면정의서 v0.7 · 테이블 정의서 v1.1 · 기술 아키텍처 v1.2, REST 70개·메시지 20종, 쿠키 이름 `huge_session`, Secure 쿠키는 https일 때만, `/auth/me`도 초기 비밀번호 변경 전 허용, localhost 리다이렉트 307, 미디어 주소 `/api` 아래 | 코드 대조, A-16 |
| WebSocket 7장 전체 | WebRTC·`rtc_*` 메시지·UDP 포트 삭제, 답변 음성은 이진 16kHz PCM, `permission`·`upload_failed` 클라이언트 메시지 추가, `terminate`에 `detail`(`resume_limit` 등), `question.resend`, `warn.label`, 4401·4409, `error` 코드 | V4, R5, D1, C4, 코드 대조 |
| `stt_retry` 메시지 | 삭제. STT 실패는 다시 시도한 뒤 장애 중단(`paused`·`server_error`) | A1 |
| `POST /auth/login` | `next`는 화면 경로(`/jobs` · `/apply/` · `/exam/` · `/mypage`)만, 기본 `/jobs`, 관리자 `/admin/postings`·`/password/change` | A2, 코드 대조 |
| `POST /auth/password-reset`(+`/confirm`) | 같은 주소 1분에 한 통, 새 링크 시 이전 링크 무효, 응답 뒤 처리, 토큰 1회용·모든 기기 로그아웃 | P1, P2 |
| `POST /me/withdraw` | 오류 `WRONG_PASSWORD`·`CONFIRM_TEXT`·관리자 403, 진행 중이면 `terminate`(`withdrawn`), 통계 반영 범위 | W4, W5, W1 |
| `POST /applications/{id}/consent/withdraw` | 204, 409 `NO_CONSENT` | W3 |
| `GET /me/applications` | 항목 `consented`, `phase`, `session_id` 추가 | W2, 코드 대조 |
| `POST /admin/postings/{id}/draft-ai`(+`/status`) | `company_name` 제거(받으면 422), 부서 소개 메모(칸 이름 `company_intro`), '주로 맡을 일' 선택, llm-rt(Qwen3 4B) 사용, `bias_warnings`는 규칙 기반 사전, 오류 코드, 진행 상태는 메모리 | U1, U2, U6, V1, 코드 대조 |
| 공고 객체 | `company_name`은 빈 글자로만 옴, `source` 값 `ai_draft`, `company_intro`=부서 소개 | U1, V1, A-10 |
| `POST /admin/postings/import` | 현재 구현 범위 밖(미구현) 표시 | V2 |
| `POST /interview/{sid}/recording` | 조각마다 객체 하나로 저장, 소리 포함 녹화, 상한(조각 5MB·구간 400MB), 503 `STORAGE_UNAVAILABLE` | R1, R4, R5, R6 |
| 미디어 2-6장 | `/media/{kind}/{path}` 하나를 실제 3개 주소(`/media/questions/{question_id}`, `/admin/media/answers/{id}`, `/admin/media/recordings/{aid}/{segment}`)로 바꿈, Range·206 삭제 | R1, R2, 코드 대조 |
| `POST /applications/{id}/interview/resume`·`GET …/interview/state` | 이어가기 3회(`resume_limit`), `resumes_left`·`end_detail` 추가, 초과 시 `ended`·`resume_limit`, reason 값 정리 | D1, 코드 대조 |
| `GET /admin/settings`·`PUT /admin/settings/{key}` | 응답에서 `admission_guard` 삭제(미구현), 설정 API는 `max_concurrent_interviews`(1~20)만, 다른 키 400 | F6, F10, D2, F8 |
| `POST /interview/{sid}/events` | 쿠키가 없거나 남의 세션이면 기록 없이 204 | 코드 대조 |
| `POST /applications` | 새로 만들 때도 200 | 코드 대조 |
| `GET /applications/{id}`, `GET /applications/{id}/resume/file` | 실제에만 있어 추가 | 코드 대조 |
| `POST /notifications/{id}/hide`, `POST /notifications/hide-read` | 추가(🔔 숨기기), 알림 링크 주소 | T37, S6 |
| `POST /admin/analysis/{aid}/reprocess`, ops-status | `instruction_suspected` 사유, `instruction_hits`, 확인 기록 감사 로그 | 채점 지시 감지(2026-10-30 승인) |
| `GET /admin/applicants/{aid}` | 응답 모양을 실제로 정정(`questions[]`, `events[]`, `coding[]` 등), 미디어 주소, 감사 로그 | 코드 대조, M1, V3 |
| `GET /admin/postings/{id}/applicants` | 응답 칸(`email`·`away_count`·`fault_count`·`review_reason` 등)·쿼리·기본 크기 정정 | 코드 대조 |
| compare·passed·stats·ops-status | 응답 모양 정정, 철회·보관 만료 통계 | F1, F5, F7, W1, 코드 대조 |
| 오류 코드 11장 | `UNAUTHORIZED`→`LOGIN_REQUIRED`, 새 코드 추가(`CONFIRM_TEXT` · `NO_CONSENT` · `CONSENT_REQUIRED` · `UPLOAD_REQUIRED` · `STORAGE_UNAVAILABLE` · `SANDBOX_DOWN` · `NOT_CODING` · `ALREADY_PUBLISHED` · `NOT_PUBLISHED` · `DRAFT_RUNNING` · `CODING_RATIO` · `INVALID_SORT` · `COMPARE_COUNT` · `MEMO_EMPTY` 등) | 코드 대조 |
| 이메일 인증 API 2개 | 현재 구현 범위 밖(미구현) 표시 | 코드 대조 |
| 감사 로그 표기 | `memo.create` 등 점 표기 | M1 |
| 12장 A-03·A-06·A-10·A-16 | 결정 행에 v1.2 결과를 덧붙임 | A1, V4 |
| 검토 반영(1장·2-2·2-3·4장 publish·5장 extract-status·6장 start·7장·8장 autosave·9장 알림) | REST 개수(구현 없음 5개), 세션 연장 조건, 202 구분, publish 예약 작업 없음, `TIMEOUT`·`NO_TEXT` 조건, 시작 대기 60초에 TTS 제외, Origin 거절은 1006, 미연결 90초(api 1분 작업·재시작 즉시), `next_question_target_sec`은 목표값, `navigate`는 서버만 지원, autosave 실패는 토스트만, 알림 링크 `/mypage/results/…`·종류 `purge_notice`, 논의사항 #21·#25~27 | 검토(백엔드·프론트엔드·UI/UX) 반영 |

## 논의사항

> 2026-11-04 사용자 결정: 개인용으로 진행한다. '확정(현행 유지)' 항목은 구현대로 확정했고, 미구현 항목(V2·V3·F6·S5)은 이후 범위로 둔다. 권장·조치 칸은 당시 제안 기록이다.

문서와 구현이 달라 어느 쪽이 맞는지 판단이 필요한 것, 코드가 이상해 보이는 것을 모았다. 코드는 고치지 않았다.

| # | 분류 | 문서·위치 | 내용 | 권장 |
| --- | --- | --- | --- | --- |
| 1 | 처리함 | 7-6 STT 실패, CONFLICTS A1 (본문 〔논의사항 #1〕) | **2026-11-06:** CONFLICTS A1 은 지금 '처음 1번 + 재시도 2번'으로 적혀 있어 코드와 같다. (이전 기록) CONFLICTS A1 은 "1회 재시도 후 장애 중단"이라고 적었으나 코드는 처음 시도 + `stt_retry_limit`(2)번 다시 해서 최대 3번 시도한다(`engine.py:637-649`, 주석도 "2번 다시 해도 실패"). 본문은 코드(설정 `stt_retry_limit`=2)대로 적었다. | CONFLICTS A1 표현을 "2번 다시"로 고치거나, 1회로 줄일지 결정 |
| 2 | 처리함 | 2-6 답변 음성 Range | **2026-11-06:** CONFLICTS R2 는 지금 '답변 음성도 Range 없음'으로 적혀 있어 코드와 같다. (이전 기록) CONFLICTS R2는 "답변 음성은 그대로(Range 지원)"라고 하는데 `admin.py:393-401`의 답변 음성 응답에는 Range 처리가 없다(전체를 `Response`로 보냄). 본문은 세 주소 모두 Range 없음으로 적었다. | Range를 구현할지, 지금처럼 전체 전송이면 CONFLICTS R2를 고칠지 결정 |
| 3 | 처리함 | 2-6, 화면정의서 | **2026-11-06:** 옛 주소 `/media/{kind}` 는 이 문서의 변경 기록·논의에만 남아 있다. (이전 기록) 문서는 `/media/{kind}/{path}` 하나였으나 실제는 지원자용 `/media/questions/{question_id}`와 관리자용 `/admin/media/…` 3개이고 `question_id`는 정수다. 화면정의서·기술 아키텍처가 옛 주소를 적었는지 확인 필요. | 개인용 화면정의서 v0.8·기술 아키텍처 v1.3도 이 주소로 통일 |
| 4 | 처리함(2026-11-09: 화면은 이 두 API 를 쓰지 않음(이력서는 `/applications/{id}/resume/...` 사용). 미구현 표시 유지) | 5장 `POST /me/resume/upload`, `GET /me/resume/extract-status` | 문서(S-A13 이력서 탭)에 있으나 라우터에 없다(`routers/applications.py:225-255`에는 `GET/PUT/DELETE /me/resume`만 있고, `acceptUpload`의 `applicationId` 선택값만 마이페이지 업로드를 염두에 둔 흔적). 미구현 표시로 남겼다. | 화면이 이 두 API를 쓰는지 확인. 안 쓰면 요구사항을 미구현 범위로 유지 |
| 5 | 처리함(2026-11-09: `SERVER_ERROR` 구현됨. `AI_UNAVAILABLE` 은 쓰는 곳 없음(문서에 '미사용'으로 둠)) | 11장 `SERVER_ERROR`(500)·`AI_UNAVAILABLE`(503) | **2026-11-06: `SERVER_ERROR` 는 공통 500 처리기로 구현함. `AI_UNAVAILABLE` 은 쓰는 곳 없음.** 이전 기록: 읽은 라우터와 `errors.py`에는 이 코드를 돌려주는 곳이 없고 500 처리기도 없다(처리 안 된 예외는 FastAPI 기본 응답 모양). 다른 파일(`llm.py` 등)에서 쓰는지는 이름으로 검색하지 못해 확인하지 못했다. | 쓰는 곳이 없으면 오류 모양 통일(TRD 4-3)을 위해 500 처리기 필요 여부 결정 |
| 6 | 처리함(2026-11-09: 화면정의서 v0.8 도 `/password/change`·`/jobs` 로 같음) | 3장 로그인 `redirect` | 관리자 첫 로그인 이동은 문서 `/admin/password`, 코드 `/password/change`(`auth.py:87`). 지원자 기본 이동은 문서 `/me`, 코드 `/jobs`. 본문은 코드로 맞췄다. | 화면정의서 v0.8 경로와 일치하는지 확인 |
| 7 | 처리함(2026-11-09: 화면 코드는 오류 코드 이름을 보지 않음(상태 코드만 봄). TRD 에 `UNAUTHORIZED` 없음) | 11장 `LOGIN_REQUIRED` | 문서의 `UNAUTHORIZED`(401)를 코드는 `LOGIN_REQUIRED`로 돌려준다(`deps.py:18`). 화면이 어느 값을 보는지 확인 필요. | 문서를 코드에 맞춤(적용함). TRD 4-3 코드 목록 확인 |
| 8 | 처리함(2026-11-09: 307 로 충분(경로를 바꾸는 GET 이동뿐). 코드 그대로) | 2-5 리다이렉트 | 문서는 308인데 `proxy.ts:9`의 `NextResponse.redirect` 기본값은 307이다. 본문은 307로 고쳤다. | 308이 필요하면 코드 수정 |
| 9 | 처리함(2026-11-09: 화면정의서에 201 가정 없음. 200 유지) | 6장 `POST /applications` | 새 지원도 200이다(`applications.py:39` 상태 코드 지정 없음). 문서의 201은 틀렸고 200으로 고쳤다. 화면정의서가 201을 가정하는지 확인. | 200 유지 또는 코드를 201로 |
| 10 | 처리함 | 7-3 `device_error` | **2026-11-06:** 화면은 `ended`·`open_failed` 만 보내고 `silent` 는 보내지 않는다. `device` 는 실패한 장치다. (이전 기록) 문서는 `kind`가 `ended` · `silent`였으나 서버는 `ended` · `open_failed`만 알고 그 밖의 값은 `unknown`으로 기록한다(`engine.py:414-421`). 화면이 `silent`를 보내는지 확인 필요(보내도 장애 중단은 된다). | 화면 코드의 `kind` 값 확인 |
| 11 | 처리함(2026-11-09: 동의 단계는 `APPLICATION_LOCKED`(409), 이력서 올리기·저장은 `RESUME_LOCKED` 그대로) | 5장 동의·업로드 오류 | 작성 중이 아닌 지원에 동의·이력서 올리기·취소를 하면 `RESUME_LOCKED`(409)를 돌려준다(`applications.py:34-36`). 동의 단계에도 같은 코드를 써서 이름이 맞지 않는다. | 오류 코드 이름 정리 여부 결정 |
| 12 | 처리함(2026-11-09: 확인: 삭제 버튼은 임시 저장(draft) 공고에만 있고 draft 공고에는 지원을 만들 수 없어 두 기준이 어긋날 일이 없음. 코드 그대로) | 4장 `DELETE /admin/postings/{id}` | 삭제 가능 여부는 지원 건 전체(작성 중 포함, `admin.py:154`)로 보는데, 목록의 `applicant_count`는 작성 중을 뺀다(`admin.py:53`). 목록에 지원자 0명인데 삭제가 409가 될 수 있다. | 두 기준을 맞출지 결정 |
| 13 | 처리함(2026-11-09: 화면은 `size=200` 으로 받아 응시 상태·이름 필터를 화면에서 함(S-R05 요구 충족). 행마다 세는 쿼리는 지원자가 많아지면 손볼 것) | 10장 지원자 목록 | 문서에 있던 `attempt_status` 필터 쿼리가 코드에 없다(`admin.py:169-174`). 목록 크기 기본 50(문서 20). 각 행마다 이벤트 건수를 따로 세어(`admin.py:194-195`) 크기 200이면 쿼리가 많다. | 필터가 필요한지 화면정의서 S-R05 확인 |
| 14 | 확정(현행 유지, 2026-11-09 사용자 결정: 문서를 구현에 맞춤) | 6장 precheck | 네트워크 속도(`network_mbps`)를 보내지 않으면 통과 처리하고, 하한 1Mbps는 코드에 고정(`interview.py:28,49-58`)이라 문서·설정에 근거가 없다. | 하한값을 TRD에 정할지 결정 |
| 15 | 확정(현행 유지) | CONFLICTS V2 | 공고 불러오기(`/admin/postings/import`) 미구현. 범위 결정 필요. | 이후 범위로 두거나 삭제 결정 |
| 16 | 확정(현행 유지) | CONFLICTS V3 | 관리자 원본 이력서 보기 API 없음(원본은 저장소에 있음). | 필요하면 추가 승인 |
| 17 | 확정(현행 유지) | CONFLICTS V4 | 답변 음성 WebSocket 이진 PCM 전송, TRD 5-2 수정 또는 승인 필요. | TRD v1.7에 반영 |
| 18 | 확정(현행 유지) | CONFLICTS F5 | 서로 다른 공고 비교는 허용하고 경고만 한다. 문서에 규정 없음. | 규정할지 결정 |
| 19 | 확정(현행 유지) | CONFLICTS F6 | 자동 보호(`admission_guard`) 미구현. 응답 칸 삭제. 기능이 필요하면 정의 필요. | 이후 범위로 정의 |
| 20 | 확정(현행 유지) | CONFLICTS S5·S6 | 하루 메일 상한 미구현(`mail_deferred_today`는 남아 있음), 알림 링크 주소는 화면정의서에 없어 실제 주소로 맞춤. | 개인용 화면정의서에 링크 표기 |
| 21 | 확정(현행 유지) | CONFLICTS C11 | 연결 없는 진행 중 응시를 90초 뒤 원인 미상 장애로 처리. 코드 위치는 `jobs.py:23,33-46`(90초 유예, 1분마다 점검), `main.py:40-53`(재시작은 즉시)로 확인했다. 사용자 결정은 아직 없다. | 확인 후 확정 |
| 22 | 확정(현행 유지) | CONFLICTS D1·U7 | 이어가기 3회, 꼬리질문 목표 시간 `followup_target_sec`은 (PRD v1.8·TRD v1.7 에 반영됨. 팀 원본에는 없음) | PRD v1.8·TRD v1.7에 반영 |
| 23 | 처리함 | CONFLICTS D2 vs F10 | **2026-11-06:** CONFLICTS D2 는 지금 F10 과 같게 적혀 있다. (이전 기록) CONFLICTS D2는 "다른 키는 형식만 검사"라고 하는데 F10과 코드는 다른 키를 400으로 거절한다(`admin.py:375-376`). 본문은 F10·코드를 따랐다. | D2 설명 정정 |
| 24 | 처리함(2026-11-09: TRD 논의사항 13(확정, 현행 유지)과 같은 항목) | AI 초안 모델 | AI 공고 초안을 채점용 8B가 아니라 llm-rt(Qwen3 4B)로 쓴다(CONFLICTS 'AI 초안 구현 메모', 확인 필요). | 8B 도입 뒤 다시 측정 |
| 25 | 처리함(2026-11-09: 3번 실패하면 WebSocket `autosave_failed` 로 서버 기록(session_events)에 남김. 장애 판정은 heartbeat 그대로) | 8장 autosave | 자동 저장이 3번 실패해도 화면은 토스트만 띄우고 서버에 알리지 않아(`Coding.tsx:97-112`) 설계의 "장애 후보"로 이어지지 않는다. | 서버에 알릴지(`upload_failed` 등) 결정 |
| 26 | 확정(알려진 한계, 2026-11-09): 화면은 `navigate` 를 보내지 않음 | 7-3 `navigate`, 11장 `SERVER_ERROR` | 화면이 `navigate`를 보내지 않는다. 처리 안 된 서버 예외의 응답 모양은 2026-11-06 해결함(#5). | `navigate` 사용 여부 결정 |
| 27 | 확정(현행 유지, 2026-11-09 사용자 결정: 문서를 구현에 맞춤) | 6장 precheck | 하한 1Mbps 점검은 화면이 `network_mbps`를 보낼 때만 걸리고, PRD 의 "5Mbps 이상 권장"은 어디서도 강제하지 않는다. | PRD·TRD 와 구분해 적기 |
| 28 | 처리함(2026-11-04) | 3장 `POST /auth/login` | 로그인 응답으로는 계정 존재가 드러나지 않게 IP 단위 차단으로 교체함. 알려진 한계: 회원가입의 `EMAIL_TAKEN` 으로도 드러난다. 서버 PC 안에서만 접속하는 현재 범위에서는 그대로 둔다. 외부 접속을 열 때 함께 고친다 | 사용자 결정 2026-11-04 |

## 2026-11-06 검토 보정

코드와 대조해 고친 내용이다. 이 내용은 v1.3 에 들어 있다.

- 1장 REST 개수를 72개로 고쳤다(구현 67개 + 구현 없음 5개). `/health` 는 세지 않는다.
- 11장에 빠져 있던 `CRITERIA_MISSING` 을 넣었다.
- 2-6 의 MinIO 표기를 객체 저장소로 고쳤다.
- `device_error`·`fail_reason` 설명을 구현에 맞췄다. 논의사항 1·2·3·10·23 을 처리함으로 고쳤다.
- 코딩테스트로 다시 연결되면 `phase` 메시지의 `coding.started` 는 `true`이고 `problems[].saved_code`·`saved_at` 에 저장된 코드가 온다. 서버는 이때부터 남은 시간을 다시 잰다.

## 2026-11-09 검토 보정

코드와 대조해 고친 내용이다. 이 내용은 v1.3 에 들어 있다.

- 9장 `GET /me/applications` 에 `connected` 를 넣었다(E7).
- 6장 녹화 조각: 늦게 온 작은 번호 조각도 저장한다(E12).
- 7-3 `device_error`: `kind: ended` 는 3초 기다린 뒤 판정한다(E18).
- 동시 시작 요청이 둘 다 통과하던 문제를 고쳤다(E10). `POST /applications/{id}/interview/start` 의 응답·오류는 그대로다.
- 동의 단계 409 는 `APPLICATION_LOCKED`(이력서는 `RESUME_LOCKED` 그대로). `consent_version` 은 v1.8(동의 ⑤ 문구).
- WebSocket: 화면 → 서버 `autosave_failed`(`problem_no`), 서버 → 화면 `paused` 에 `resumes_left`(앞으로 이어갈 수 있는 끊김 횟수). `/interview/state` 의 `resumes_left` 와 같은 값.
- 논의사항 남은 항목을 사용자 결정으로 정리했다(설정·고정값은 문서를 구현에 맞춤, AI 설계는 구현대로).

## 2026-11-10 보정

사용자 결정과 코드에 맞춰 고친 내용이다. 이 내용은 v1.3 에 들어 있다.

- `POST /admin/postings/{id}/draft-ai/revise` 추가, `draft-ai/status` 에 `stage`·처리 기록 (C-15).
- `POST /admin/postings/{id}/publish`: 게시 뒤 질문 후보를 '검토 대기'로 만든다(응답과 무관, C-17).
- `GET /admin/questions`: 출처(`category`)와 적용 범위(`scope`)를 함께 준다 (C-17).
