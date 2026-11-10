# 패치 내역

새 내용이 위에 온다. 왜 바꿨는지와 설계 문서와 다른 점은 [CONFLICTS.md](CONFLICTS.md)의 항목 번호를 따라가면 된다.

---

## 2026-11-10 — 면접 질문 품질, 질문 적용 범위, AI 공고 초안 그래프

> 한 줄 요약: AI 가 만든 면접 질문에서 **찌꺼기 글자·답변 방식 지시·두 가지 묻기·지어낸 경험**을 걸러 내고, 질문마다 **쓸 수 있는 공고 범위**를 붙였으며, 공고를 게시하면 **그 공고로 질문 후보**를 미리 만들어 관리자가 검토하게 했다. AI 공고 초안은 **LangGraph 그래프**(참고 → 작성 → 검사 → 고쳐 쓰기)로 바꿨다.

### ⚠ 올리기 전에 꼭 볼 것

| 항목 | 내용 |
|---|---|
| **DB 스키마 변경** | `questions` 테이블에 `posting_id`(uuid, `job_postings` FK, ON DELETE CASCADE, 인덱스)와 `job_code`(varchar 32) 두 열이 생겼다. 둘 다 비워 둘 수 있다(NULL = 모든 공고 공통). 앱이 뜰 때 `migrate.py` 가 `ADD COLUMN IF NOT EXISTS` 로 넣으므로 따로 할 일은 없다. |
| 다시 띄우기 | 면접이 진행 중이 아닌지 확인한 뒤 `sh scripts/up.sh app` (api 이미지 다시 빌드) |
| 새 파일 마운트 | `compose.app.yml` 에서 `./data/web_questions_candidates.json` 을 api 의 `/data/web_questions.json` 으로 읽기 전용 마운트 |
| 인터넷 참고 후보 넣기 (선택) | `docker compose -f compose.app.yml exec api python -m app.manage load_web_questions <공고 id>` — 같은 글은 다시 넣지 않으므로 여러 번 돌려도 된다 |

---

### 1. 면접 질문 글 검사 (CONFLICTS C-16)

**무엇이 문제였나.** 실제 LLM(llm-rt, Qwen3 4B)으로 질문을 만들어 보니 이런 질문이 나왔다.

- 끝에 JSON 조각이나 이모지가 붙은 질문(`…설명해 주세요."}`), 한글에 영어가 붙은 글(`본ly`)
- "1문장으로 답해 주세요", "간단히" 같은 **답변 방식 지시**
- "~했고, 그 이유는?"처럼 **한 번에 두 가지를 묻는** 질문
- 이력서에 없는 프로젝트를 **지어낸** 이력서 질문
- 직무 질문인데 "~해 본 경험이 있나요?"처럼 **경험을 묻는** 질문

**무엇을 바꿨나.**

| 파일 | 바뀐 것 |
|---|---|
| `backend/app/domain/question_text.py` (새 파일) | 질문 글 검사 한곳에 모음. `cleanQuestion()` 은 앞뒤 따옴표·끝 찌꺼기를 지우고, `textProblem()` 은 문제 코드를 돌려준다: `foreign_script` · `junk_text` · `meta_phrase` · `compound_question` · `not_question` · `too_long`(100자). `isYesNo()` 는 예/아니오로 답할 수 있는 질문인지 본다(의문사가 없고 '설명해 주세요' 같은 부탁 꼴도 아님). |
| `backend/app/services/question_compose.py` | ① 종류별 예시 꼴(`KIND_FORMS`)을 프롬프트에 넣음 ② 인성·회사 질문은 "기술 지식을 묻지 않는다" ③ 직무 질문의 과거형(`셨나요`·`었나요`)도 경험 질문으로 보고 버림 ④ 다시 만들 때 **이전 질문과 문제를 함께** 보여 주고 고치게 함 ⑤ 요구하는 일의 수 상한 2 → **1** ⑥ 이력서 요약의 `[PyTorch]` 꼴을 `— 사용 기술: PyTorch` 로 바꿈(대괄호 뒤에 JSON 찌꺼기가 붙던 원인) ⑦ 이력서 근거 문장은 앞부분 일치로 확인 |
| `backend/app/interview/graph.py` | 꼬리질문도 본질문과 같은 글 검사를 거치고 걸리면 내지 않음 |

**결과 (시뮬레이션: 지원자 3명 × 질문 DB 있음/없음 × 2반복 = 120자리).**

| | 수정 전 | 1차 | 2차 | 3차(최종) |
|---|---|---|---|---|
| AI 가 만든 질문 수 (나머지는 질문은행·예비 질문) | 112 | 74 | 109 | **110** |
| 찌꺼기·답변 방식 지시·지어낸 경험 | 있음 | — | — | **0건** |

- 남은 한계: 4B 모델의 어색한 말투("느꼈는가요"), 예/아니오 질문 몇 개(→ 2번의 꼬리질문으로 보완), 이력서 항목 두 개를 섞은 질문 1건.
- 시뮬레이터는 그래프 순서를 따라 다시 짠 것이고 실제 LangGraph 를 돌린 것은 아니다. "질문 DB 없음"은 가정이다(실제 코드는 예시가 없으면 바로 질문은행·예비 질문으로 간다).

**바꾸지 않은 것 (사용자 결정).** 엑셀 질문은행·예비 질문 1,914개 가운데 244개는 두 가지를 묻지만 **그대로 둔다**("여러 개 묻는 거는 그냥 냅두자"). 그래서 `question_bank.py` 는 바뀌지 않았다.

### 2. 예/아니오 질문 뒤 이유 묻기 (C-16)

사용자 요청: "예 아니요 질문의 경우, 그 이유를 추가로 물어보면 될 거 같아."

- `backend/app/interview/engine.py`: 본질문이 예/아니오 질문이고 답이 **30자보다 짧으면** LLM 을 부르지 않고 "그렇게 답하신 이유를 구체적으로 말씀해 주세요."를 꼬리질문으로 낸다(`YES_NO_SHORT_ANSWER`, `yesNoFollowup()`). 답이 길면 꼬리질문 프롬프트에 "이유·상황이 없으면 이유를 물어라"를 덧붙인다(`followupPrompt()`).
- 꼬리질문 개수 제한(질문당 1개, 전체 4개)과 시간이 모자라면 건너뛰는 규칙은 그대로다.
- 질문은행에서 사용 중인 1,914개 가운데 192개가 예/아니오 질문이다.

### 3. 질문 적용 범위 (C-17, DB 변경)

질문마다 **어느 공고에서 쓸 수 있는지**를 붙였다.

| 질문 종류 | 범위 | DB |
|---|---|---|
| 회사 질문 | 그 공고에서만 | `posting_id` |
| 직무 질문 | 같은 직무 공고에서만 | `job_code` |
| 인성 질문, 엑셀·예비 질문 | 모든 공고 | 둘 다 NULL |

- `models.py`·`migrate.py`: 열 2개와 인덱스.
- `question_compose.py`: `scopeFor(kind, posting)`, 질문은행 대체 후보(`candidates()`)에서 범위 밖 질문을 뺌, 면접 때 만든 질문을 검토 대기로 넣을 때(`savePending`) 범위를 붙임.

### 4. 공고를 게시하면 질문 후보 만들기 (C-17)

- `backend/app/services/posting_questions.py` (새 파일): 게시 뒤 백그라운드에서 그 공고의 업무·자격 줄마다 **직무 질문 1개(최대 6)**, **회사 질문 3개**를 1번과 같은 프롬프트·검사로 만든다. 지원자 정보는 넣지 않는다. 질문 DB 와 0.8 이상 비슷하거나 같은 글이면 버린다. 남은 것은 **검토 대기**(`pending`, 출처 `공고 기반`)로 넣고, 관리자가 [추가]해야 쓴다.
- 실패해도 게시는 그대로 된다(오류는 기록만). 감사 기록 `question.posting_candidates`.
- `routers/admin.py`: 게시(`publish`)가 `async` 가 되고 커밋 뒤 `posting_questions.schedule()` 을 부른다.
- 실측(예시 공고 "AI/AX 엔지니어 (신입)"): 9개 저장(직무 6, 회사 3), 버림 0. 회사 질문 말투가 약하다.

### 5. 인터넷 참고 후보 질문 (C-17)

- `data/web_questions_candidates.json` (새 파일, 65개): 인터넷 면접 질문 자료(RAG·PyTorch·주니어 ML·인성)의 **주제만 참고해 한국어로 새로 쓴** 질문. 원문 문장은 옮기지 않았다. 항목마다 출처 주소, 글 검사 결과, 질문은행에서 가장 비슷한 질문과 유사도, 판정(`new` 53 / `bank_duplicate` 12)을 적었다.
- `manage.py load_web_questions <공고 id>`: `new` 이고 아직 없는 글만 검토 대기(출처 `인터넷 참고`)로 넣고 임베딩을 붙인다. 감사 기록 `question.web_candidates`.
- 실제 DB 에 넣은 결과: 53개(직무 47, 회사 5, 인성 1), 임베딩 53개.

### 6. 질문 관리 화면 정리 (C-17)

- `frontend/app/admin/questions/page.tsx`: **적용 범위** 열(이 공고만 · 제목 / 이 직무만 · 직무 / 공통)과 출처(AI 생성 · 공고 기반 · 인터넷 참고)를 보여 주고 안내 문구를 고침.
- `routers/admin_questions.py`: 목록 응답에 `category`, `scope{type, label, posting_id|job_code}` 추가.
- 이 화면은 그전부터 있었는데 화면정의서에 없었다 → 화면정의서에 **S-R11 질문 관리**(§10.11)를 새로 적음(사용자 결정).

### 7. AI 공고 초안을 LangGraph 그래프로 (CONFLICTS C-15)

- `backend/app/services/posting_draft.py`: 참고 공고 찾기(같은 직무 게시·마감 공고 최근 2건, 용어·문체만) → 초안 작성 → 칸별 검사(차별 표현, 예전 공고 문장 40자 연속 일치) → 문제 있는 칸만 1번 다시 쓰기. 백엔드 차별 표현 사전에 **종교** 추가.
- 관리자 **한 칸 다시 쓰기**: `POST /admin/postings/{id}/draft-ai/revise` `{section, note, current}` (`schemas.DraftReviseRequest`). 결과는 화면 칸에만 넣고 DB 에는 쓰지 않는다([임시저장]해야 저장). 게시 뒤에는 409. 감사 기록 `posting.draft_revise`.
- 화면: AI 초안 진행 단계를 서버 단계로 표시(`admin/postings/ai/page.tsx`), 공고 작성 1단계에 'AI에게 한 칸 다시 쓰게 하기' 상자와 AI 처리 기록(`components/PostingEditor.tsx`, `lib/admin.ts`).
- 체크포인트는 게시·삭제·새 초안 때 지운다. 상태에는 공고 문장과 관리자 입력만 있고 지원자 개인정보는 없다.

### 8. 지원자 상세 '다시 돌리기' 확인 모달

- `frontend/app/admin/applicants/[applicationId]/page.tsx`: 평가 지연 건의 [다시 돌리기]는 "다시 채점할까요?", 채점 지시가 의심되는 건의 [확인했습니다, 채점하기]는 "확인한 내용으로 채점할까요?" 모달을 한 번 거친다.

### 9. 문서 (모두 `개인용/`, 팀 원본은 그대로)

| 문서 | 바뀐 곳 |
|---|---|
| 화면정의서 v0.7 | S-R11 질문 관리 추가(§2 목록, §10.11, T-53 사이드바), §10.9 문항 현황 문구, S-R02·S-R03(C-15), S-R06 확인 모달, 끝에 '2026-11-10 보정' |
| 기능정의서 0.3v.xlsx | QST-01-2·02·04, INT-06, EVL-08, ADM-07-2, JOB-02-1·02-2 수정, **QST-07 공고 기반 질문 후보 · QST-08 질문 관리** 추가, 변경 이력 7줄 |
| 테스트케이스 v0.3.xlsx | **TC-173~182** 추가(질문 글 검사·이력서 근거·직무 지식 질문·예/아니오 꼬리질문·적용 범위·게시 때 후보·질문 관리 화면·인터넷 후보·한 칸 다시 쓰기·다시 돌리기 모달), 변경 이력 |
| 테이블정의서 v1.1 | `questions.posting_id`·`job_code`, 출처 설명 |
| TRD v1.6 | 7-4 ② 질문은행 대체 후보 범위, questions 설명 |
| API 명세서 v1.2 | 게시 뒤 후보 만들기, `GET /admin/questions` · approve · reject, draft-ai revise·status |
| PRD v1.7 | QST-01(범위), QST-02(글 검사), 끝에 '2026-11-10 보정' |
| AI 아키텍처 v1.6 | T2·T3·T4 표, 6.0 ⑥ 게시 뒤 질문 후보, '2026-11-10 보정' |
| 논의사항 | 9장(처리함 · 그대로 두기로 함 · 남은 확인) |
| CONFLICTS.md | C-15, C-16, C-17 |

### 10. 테스트

| 검사 | 결과 |
|---|---|
| 백엔드 `python -m pytest` | **437 passed, 4 skipped** (2026-11-10). `python -m ruff check .` 통과 |
| 새 테스트 파일 | `tests/test_question_text.py`, `tests/test_posting_questions.py`(8개), `tests/test_posting_graph.py`(15개) |
| 고친 테스트 파일 | `tests/test_question_rag.py`, `tests/test_evaluation.py`, `tests/test_posting_draft.py`, `tests/conftest.py`(게시 때 후보 만들기를 테스트에서는 끔) |
| 프론트엔드 | `npx tsc --noEmit`, `npm run lint` 통과 (경고 0) |

**아직 확인하지 않은 것.** 질문 관리·한 칸 다시 쓰기·확인 모달의 브라우저 확인, 실제 [게시] 버튼으로 후보가 생기는지(가짜 LLM 테스트와 함수 직접 실행만 함), 실제 면접(음성)에서 예/아니오 꼬리질문, E2E(Playwright).

**남은 문제.**

- 회사 질문 후보의 말투가 약하다 — 프롬프트를 손볼지 정해야 한다.
- 엑셀 질문에는 범위가 없다(모두 공통). 다른 직무 공고가 생기면 다시 본다.
- 질문 #6343 은 범위 없이 사용 중이다(확인함).
