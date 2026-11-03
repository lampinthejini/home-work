# Huge — AI 1차 면접 플랫폼 (Team AIIT)

AI 면접(질문 음성 → 답변 음성 인식 → 꼬리질문)과 선택형 코딩테스트를 한 번에 진행하는 채용 1차 면접 서비스입니다.
설계 기준은 상위 폴더의 PRD v1.6 · TRD v1.5 · 화면정의서 v0.6 · API 명세서 · AI 기술 아키텍처 v1.4 입니다.

## 구성 (컨테이너 3묶음)

| 묶음 | 파일 | 서비스 |
|---|---|---|
| infra | `compose.infra.yml` | PostgreSQL(pgvector) · Redis · RustFS(오브젝트 저장소) · Mailpit |
| ai | `compose.ai.yml` | llm-rt(llama.cpp GPU, Qwen3 4B) · **llm-eval(llama.cpp CPU, Qwen3 8B — 결과 이유 쓰기)** · stt(faster-whisper) · tts(Supertonic) · ocr(PaddleOCR 한국어, CPU) · **embed(BGE-M3, CPU — 질문 RAG)** |
| app | `compose.app.yml` | api(FastAPI) · frontend(Next.js) · **worker-eval(채점, 동시 1개) · worker(메일·알림) · scheduler(5분 점검·결과 공개, 매시 안내)** |

브라우저 주소: <http://127.0.0.1:8080> (화면) · api/WebSocket `127.0.0.1:8000`

## 처음 실행

```sh
cp .env.example .env              # 비밀값 채우기 (POSTGRES_PASSWORD, APP_SECRET, ADMIN_INITIAL_PASSWORD 등)
sh scripts/up.sh                  # 네트워크 생성 → infra → ai → app 순서로 띄움
docker exec huge-app-api-1 python -m app.manage init            # 관리자 계정 (첫 로그인 때 비밀번호 변경)
docker exec huge-app-api-1 python -m app.manage load_questions  # 질문은행 (상위 폴더 xlsx 2개)
docker exec huge-app-api-1 python -m app.manage embed_questions # 질문 임베딩 (RAG, 처음 약 13분, 다시 돌리면 없는 것만)
docker exec huge-app-api-1 python -m app.manage sample_posting  # 예시 공고 (선택)
```

- 내리기: `sh scripts/down.sh` (볼륨은 남음). 한 묶음만: `sh scripts/up.sh app`
- 모델 파일은 `models/llm/` 에 둡니다 (Qwen3 4B · Qwen3 8B Q4_K_M GGUF, 각 `.sha256` 확인). GPU 6GB 기준으로 맞춰 두었습니다.
- **Docker 메모리 24GB 이상 필요** (llm-eval 8B 가 CPU 메모리 약 5GB 사용, 상한 9GB). Windows 는 `%USERPROFILE%\.wslconfig` 에 `[wsl2]` `memory=24GB` 를 넣고 `wsl --shutdown` 뒤 Docker 를 다시 켭니다.
- 메일은 개발용 Mailpit 으로 갑니다 (<http://127.0.0.1:8025>).

### DB 직접 보기 (개발자용)

Postgres 는 외부와 끊긴 내부 네트워크에만 있어 포트가 열려 있지 않습니다. DBeaver 등으로 볼 때만 내 PC 전용 통로를 엽니다.

```sh
docker run -d --name huge-db-tunnel --network huge-front -p 127.0.0.1:15432:5432 alpine/socat tcp-listen:5432,fork,reuseaddr tcp-connect:postgres:5432
docker network connect huge-internal huge-db-tunnel
# DBeaver: 127.0.0.1:15432 / DB huge / 사용자 huge / 비밀번호 .env 의 POSTGRES_PASSWORD. 읽기 전용 연결 권장
docker rm -f huge-db-tunnel        # 다 보면 닫기
```

답변·이력서·판정 근거 같은 민감한 칸은 앱에서 암호화(AES-256-GCM)해 저장하므로 DBeaver 에서는 읽을 수 없습니다. 서버 안에서 풉니다.
출력에 지원자 개인정보가 그대로 나오니 확인에만 쓰고 파일·메신저로 옮기지 않습니다.

```sh
docker exec huge-app-api-1 python -m app.devtools answers <application_id>   # 질문과 답변 글
docker exec huge-app-api-1 python -m app.devtools field answers transcript <answers.id>  # 표·칸·ID 로 바로 (복사 불필요)
docker exec huge-app-api-1 python -m app.devtools plain     # DBeaver 용 평문 사본 → dev_plain 스키마 (개발 환경 전용, 그 시점 사본)
docker exec huge-app-api-1 python -m app.devtools unplain   # 평문 사본 지우기 (다 보면 꼭)
docker exec huge-app-api-1 python -m app.devtools decrypt "<칸 값>"           # DBeaver 에서 복사한 암호화 값 하나
```
- Windows Git Bash 에서는 `MSYS_NO_PATHCONV=1` 이 필요합니다 (`up.sh` 에 들어 있음).

## 개발 검사

```sh
cd backend && python -m pytest && python -m ruff check .
cd frontend && npx tsc --noEmit && npm run lint
cd e2e && npm test               # 브라우저 E2E 빠른 묶음 (스택이 떠 있어야 함, 약 5분) — e2e/README.md
cd e2e && npm run test:full      # 끝까지 응시·코딩·채점·결과 공개 포함 (약 25분)
```

## 범위

포함: 회원가입·로그인, 공고 작성(AI 초안·직접 작성)·게시·마감(코딩테스트 토글), 공고 조회·지원, 동의·이력서(PDF 리더 → AI 항목 정리 → 필요 시 OCR · 직접 작성),
환경 점검, 질문 10개 RAG 구성(기존 질문 예시 + 이력서 + 회사 상황 → LLM, 실패 시 질문은행 → 예비 질문), AI 면접(TTS 질문 · WebSocket PCM 음성 · STT 자막 · LLM 꼬리질문), 화면 이탈 경고·취소, 장애 중단·이어가기,
코딩테스트(격리 실행 상자), 마이페이지, 관리자 지원자 목록·상세(답변 원문·음성·기록).

2단계-A: 응시가 끝나면 자동 채점(문항별 AI 점수 + 근거 문장 확인) → 코드가 총점·합격 여부 계산(총점 ≥ 합격 기준) → 8B 모델이 결과 이유 작성(방향·근거 검사, 1회 다시 쓰기, 안 되면 '확인 필요') → 공개 시각에 결과 공개·사이트 알림·메일, 지원자 결과 화면, 관리자 점수·리포트·하이라이트·[다시 돌리기], 🔔 알림.

2단계-B·C: 관리자 지원자 비교(2~3명)·다음 전형 대상자(1차 합격자 연락처)·대시보드(통계·운영 현황)·운영 설정(동시 면접 상한), 코딩 실행은 `worker-sandbox` 만 docker.sock 을 가짐(api 는 비루트·소켓 없음), 매일 03:00 보관 기간이 지난 면접 데이터 삭제(파일·Redis·DB, 동의는 증거로 남김, `deletion_logs`)·09:00 삭제 2일 전 관리자 안내.

3단계: 카메라 녹화(10초 조각 업로드, 관리자 재생·감사 로그, 응시 끝 + 3일 삭제 — 매시 30분), 동의 철회·회원 탈퇴(진행 중 응시 취소 → 즉시 삭제, `deletion_logs`), 비밀번호 찾기(재설정 메일 30분 링크, Mailpit), 관리자 메모.

E2E: Playwright 로 가입·비밀번호 찾기(Mailpit)·지원~면접·녹화 업로드·화면 이탈 경고/취소·장애 중단→이어가기·끝까지 응시→코딩테스트→채점→결과 공개·관리자 녹화 재생·메모·탈퇴를 확인합니다 ([`e2e/README.md`](e2e/README.md)).
남은 것: 코딩 시간 초과·붙여넣기 차단, 관리자 화면 공고 작성 E2E.
설계와 다르게 구현한 부분은 [`CONFLICTS.md`](CONFLICTS.md) 에 있습니다 (승인 필요).

---
Made by **Team AIIT** · AI Interview Training
