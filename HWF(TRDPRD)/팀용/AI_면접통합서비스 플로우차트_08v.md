# AI 면접 통합 서비스 플로우차트

통합 설계 검토 보고서 | 08v | 기준 문서: 통합 PRD v1.3 · TRD v1.5 (2026-10-29)

## 문서 개요

통합 PRD v1.3의 요구사항과 TRD v1.5의 처리 규칙을 기준으로 서비스 전체 흐름과 기능별 처리 절차를 정리한 플로우차트다. 도면의 각 단계에는 PRD 요구사항 ID를 함께 적어 추적할 수 있게 했다. 숫자(재시도 횟수·시간 제한·주기)는 TRD 14장 설정값을 따르며, 비동기 처리 등 구현 상세는 TRD에서 정한다.

## 08v 반영 사항

PRD v1.3과 TRD v1.5에 맞춰 07v를 고쳤다.

1. **단일 관리자(전체)** — ‘기업 담당자’와 ‘운영자’를 ‘관리자’ 하나로 합쳤다. 관리자 계정 1개는 설치 때 만들고, 회사별 계정·데이터 구분(멀티테넌시)은 두지 않는다(N8). ‘사전 발급 계정’, ‘소속 기업 데이터만’ 문구를 뺐다.
2. **02 공고** — Open API·더미 데이터로 공고를 불러오는 경로를 넣었다(JOB-08, 임시저장으로 들어옴). 게시 뒤에도 공고 내용은 고칠 수 있고, 평가 기준만 첫 응시 시작 후 잠긴다. 마감하면 진행 중 면접도 바로 끝난다(INT-10).
3. **03 지원** — 이력서는 PDF·JPG·PNG를 받고 10MB 상한을 없앴다(APP-04). 예상 처리 시간을 보여 주고, OCR 실패 기준(예상의 2배·최소 60초 초과, 글자 없음, 평균 신뢰도 0.5 미만)을 넣었다. 동시 면접 상한에 걸리면 ‘대기’ 상태 대신 ‘다시 시도’ 버튼을 보여 준다(상태는 ‘준비 중’ 그대로).
4. **04 질문 구성** — 구성 시점을 응시 시작에서 이력서 확정 직후(백그라운드)로 옮겼다(QST-03). 시도당 8초, 지원자 1명 전체 60초 제한을 넣고, 이력서 기반 문항은 실패하면 바로 예비 질문으로 바꾼다(QST-05).
5. **05 AI 면접** — ‘꼬리질문 5초 안에 생성’을 남은 시간 기반 판단으로 바꿨다. 꼬리질문 음성(TTS)이 늦으면 자막만으로 낸다(TRD 7-5).
6. **07 평가** — AI가 정한 합불을 시스템이 ‘총점 ≥ 합격 기준’ 규칙으로 다시 판정하지 않는다. 시스템은 형식·값 범위·근거 문장만 검증한다(TRD 1-2, 8-2 ⑤). 분석 재시도 간격은 1·2·4분이다.
7. **08 결과 공개** — 마감 시각에 모든 응시가 끝나므로 ‘장애 재개 중이라 지연 공개’ 분기를 뺐다. 알림 목록과 메일 재시도(60·300·1800초)를 TRD 10장에 맞췄다.
8. **10 마이페이지** — 응시 상태에 ‘미응시(마감)’·‘응시 종료(마감)’을 넣었다. 보관 기간이 지나면 데이터 자체가 지워지므로 ‘보관 만료·열람 불가’ 분기를 뺐다.
9. **11 장애 이어가기** — 끊긴 지 15초가 되는 순간 바로 판단한다(TRD 7-2). 재개 기한은 마감 후 24시간이 아니라 공고 마감 시각까지다(RES-03). 장애로 끊긴 면접의 자리는 10분만 맡아 둔다(TRD 5-3).
10. **12 화면 이탈** — 1회차 이탈 뒤에는 같은 질문을 멈춘 시점의 남은 시간부터 이어 답하고, 이탈 전후 음성을 하나의 답변으로 합친다(TRD 7-3).

## 07v 반영 사항

PRD v1.1의 팀 피드백 5건 중 흐름에 영향을 주는 4건을 반영했다.

1. **피드백 ① AI가 1차 합불 판정(07, 00, 09)** — 1차 합격·불합격은 AI가 판정 사유와 함께 낸다. (08v에서 검증 방식 변경)
2. **피드백 ② 이메일 인증 후순위(01, 03)** — 인증 없이 가입·지원하는 흐름을 기본으로 바꿨다. 이메일 인증은 추가 후 경로로 점선 표시했다.
3. **피드백 ④ 질문 재생성 상한(04, 11)** — 해당 문항을 같은 조건으로 최대 3회 재생성하고, 실패하면 DB 질문 → 예비 질문으로 대체한다.
4. **피드백 ⑤ 동시 면접 상한 N(03, 10)** — 상한을 운영 설정값 N으로 바꿨다. (08v에서 ‘대기’ 상태를 ‘다시 시도’ 안내로 변경)
5. **이력서 OCR 추가(03, 08-A)** — 스캔 PDF를 온프레미스 OCR로 추출하는 경로를 넣었다. (08v에서 JPG·PNG 추가)
6. **용어 통일** — 도면 용어를 PRD v1.1 용어로 바꿨다.

## 06v 반영 사항

05v를 PRD v1에 맞춰 전면 재작성했다. 도면을 00~12로 다시 나누고, 질문 구성의 관리자 검토 단계 제거, 꼬리질문 상한(질문당 1개·전체 4개), 코딩테스트 AI 도우미 제거, 마감 다음 날 10:00 일괄 공개를 넣었다.

검토 상태: 내부 검토본 / PRD v1.3 · TRD v1.5 정합 확인용

## 도면 목록

| 번호 | 도면 | 관련 PRD v1.3 · TRD v1.5 | 07v 대응 |
|---|---|---|---|
| 00 | 전체 서비스 흐름 | PRD 2-3, 6-1 | 00 |
| 01 | 회원가입·로그인 | PRD 5-1 · TRD 11장 | 01 |
| 02 | 공고 작성·평가 기준 설정 | PRD 5-2 · TRD 5-1 | 02 |
| 03 | 지원·사전 준비 | PRD 5-3, INT-08 · TRD 5-3, 7-6 | 03 |
| 04 | 질문 구성 | PRD 5-5, 7-4 · TRD 7-4 | 04 |
| 05 | AI 면접·꼬리질문 | PRD 5-4 · TRD 7-5 | 05 |
| 06 | 코딩테스트 응시·채점 | PRD 5-6 · TRD 9장 | 06 |
| 07 | 평가·채점·AI 1차 합불 판정 | PRD 5-7, 7-1 · TRD 8장 | 07 |
| 08 | 결과 공개·알림·보관 삭제 | PRD 5-8, 10-2, ADM-08 · TRD 10장 | 08 |
| 09 | 관리자 결과 관리 | PRD 5-9 | 09 |
| 10 | 지원자 마이페이지 | PRD 6-2, RES-03, INT-10 | 10 |
| 11 | 장애 이어가기 | PRD 5-10, 7-2 · TRD 7-1, 7-2 | 11 |
| 12 | 부정행위: 화면 이탈 | PRD 5-11, 7-3 · TRD 7-3 | 12 |

범례: 타원(시작/종료·다른 도면 연결) · 마름모(분기) · 파란 박스(허브 화면, 재진입 지점) · 흰 박스(처리/화면 단계) · 점선(상시 감시·백그라운드)

---

## 00 전체 서비스 흐름

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef hub fill:#DBEAFE,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    visit(["서비스 접속"]):::startEnd --> who{"로그인 상태 · 역할?"}:::decision

    who -- 비로그인 --> guest["공고 목록 · 상세 열람<br/>준비 중 직무는 필터에만 표시"]:::process
    guest -- 지원하기 --> login["로그인 · 회원가입 (01)"]:::process
    login -- "인증 후 해당 공고로 복귀" --> apply

    who -- 지원자 --> jobList["공고 목록<br/>(지원자 홈)"]:::hub
    jobList -- 공고 선택 --> jobDetail["공고 상세"]:::process
    jobDetail -- 목록으로 --> jobList
    jobDetail -- 지원하기 --> apply["지원 · 사전 준비 (03)"]:::process
    apply -. "이력서 확정 직후 백그라운드" .-> questions["질문 구성 (04)<br/>DB 검색 · AI 생성 · 문항별 재생성 최대 3회 · 전체 60초"]:::process
    apply -- "환경 점검 · 면접 시작" --> interview["AI 면접 (05)"]:::process
    questions -.-> interview
    interview --> useCode{"코딩테스트 사용 공고?"}:::decision
    useCode -- 예 --> coding["코딩테스트 (06)"]:::process
    useCode -- 아니요 --> done["응시 완료<br/>결과 공개일 안내"]:::process
    coding --> done
    done --> evaluate["평가 · AI 1차 합불 판정 (07)<br/>시스템은 형식 · 값 범위 · 근거 검증 · 관리자는 확인만"]:::process
    evaluate --> publish["마감 다음 날 10:00 일괄 공개 (08)"]:::process
    publish --> myPage
    jobList -- 마이페이지 --> myPage["마이페이지 (10)"]:::hub
    myPage -- 공고 목록으로 --> jobList

    interview -.-> watch["진행 중 상시 감시<br/>장애 이어가기 (11) · 화면 이탈 (12)"]:::process
    coding -.-> watch
    deadline(["공고 마감 시각"]):::startEnd -.-> closeAll["모든 응시 즉시 종료 (INT-10)<br/>시작 전 → 미응시(마감) · 진행 중 · 장애 중단 → 응시 종료(마감)"]:::process
    closeAll -.-> evaluate

    who -- 관리자 --> jobManage["공고 관리<br/>(관리자 홈)"]:::hub
    jobManage -- "공고 작성 · 불러오기" --> jobCreate["공고 작성 · 평가 기준 설정 (02)"]:::process
    jobCreate -- 저장 후 복귀 --> jobManage
    jobManage -- "지원자 · 통계 · 운영" --> resultMgmt["결과 관리 (09)"]:::process
    resultMgmt -- 복귀 --> jobManage
    evaluate -. 산출 즉시 열람 .-> resultMgmt
```

설계 기준: 지원자는 공고 목록, 관리자는 공고 관리 화면이 홈이다. 관리자 계정은 1개이며 설치 때 만들어 두고, 회원가입은 지원자만 한다(N8). 응시는 지원 건당 1회이고, 첫 질문이 제시되는 시점에 차감된다(INT-09). 1차 합불은 AI가 판정하고 시스템이 결과의 형식·값 범위·근거를 검증하며, 관리자를 포함해 누구도 수정할 수 없다(1-3 ①②). 공고 마감 시각이 되면 시작 전이든 진행 중이든 그 공고의 응시는 즉시 끝난다(INT-10).

---

## 01 회원가입·로그인

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    entry(["로그인 · 회원가입 진입"]):::startEnd --> account{"계정 유형?"}:::decision
    account -- "지원자 · 신규" --> signup["가입 정보 입력<br/>이름 · 이메일(아이디) · 비밀번호 · 휴대전화<br/>만 14세 이상 확인 · 이용약관·개인정보 동의"]:::process
    signup --> signupOk{"필수 항목 · 형식 · 비밀번호 규칙 통과?<br/>8~64자 · 영문·숫자·특수문자 각 1자 이상<br/>이메일 아이디 포함 금지 · 같은 문자 4번 연속 금지"}:::decision
    signupOk -- 아니요 --> signup
    signupOk -- 예 --> login
    signupOk -.->|"부가 기능 · 후순위"| sendVerify["이메일 인증 메일 발송<br/>추가 후에는 새 지원부터 인증 확인"]:::process
    sendVerify -.-> login

    account -- "지원자 · 기존 / 관리자" --> login["로그인"]:::process
    login --> loginOk{"인증 성공?"}:::decision
    loginOk -- 아니요 --> failCount{"연속 실패 5회?"}:::decision
    failCount -- 아니요 --> failMsg["실패 안내<br/>계정 존재 여부 비노출"]:::process
    failMsg --> login
    failCount -- 예 --> lock["10분 로그인 제한"]:::process
    lock --> login
    login -- 비밀번호 찾기 --> reset["이메일로 비밀번호 재설정 링크 발송<br/>(30분 유효)"]:::process
    reset --> login

    loginOk -- 예 --> firstLogin{"관리자 첫 로그인?"}:::decision
    firstLogin -- 예 --> pwChange["초기 비밀번호 변경 (건너뛸 수 없음)"]:::process
    pwChange --> route
    firstLogin -- 아니요 --> route{"역할 · 진입 경로?"}:::decision
    route -- "지원자 · 지원하기에서 진입" --> backApply(["해당 공고 지원 절차로 복귀 (03)"]):::startEnd
    route -- 지원자 --> toList(["공고 목록"]):::startEnd
    route -- 관리자 --> toManage(["공고 관리"]):::startEnd
```

설계 기준: 이메일 인증은 부가 기능(후순위)이다. 추가 전에는 인증 없이 가입·지원할 수 있고, 점선은 추가 후 경로다(ACC-02). 추가 후에도 이미 진행 중인 지원은 확인하지 않고 새 지원을 만들 때만 인증 여부를 본다(추천안). 생년월일·성별·주소·사진·주민등록번호는 수집하지 않는다(ACC-02). 세션은 마지막 요청 후 2시간 유지하며 면접 중에는 연장한다(ACC-01). 복귀 경로는 허용된 내부 경로만 쓴다(ACC-04). 지원자는 본인 데이터만, 관리자 API는 관리자만 쓸 수 있으며 서버가 모든 요청에서 역할과 데이터 주인을 확인한다(ACC-06).

---

## 02 공고 작성·평가 기준 설정

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef hub fill:#DBEAFE,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    jobManage["공고 관리"]:::hub --> mode{"작성 방식?"}:::decision
    mode -- AI 초안 --> aiDraft["선택형 · 단답형 질문 답변<br/>AI 공고 초안 생성 (채점용 LLM, 백그라운드)"]:::process
    aiDraft --> biasWarn["차별 소지 표현 표시 · 경고<br/>(게시는 막지 않음 · 감지 방식 미정 O-05)"]:::process
    biasWarn --> form
    mode -- 직접 작성 --> form["공고 필드 입력<br/>제목 · 직무(AI/AX 엔지니어) · 회사명 · 회사 소개 · 주요 업무<br/>자격 요건 · 우대 사항 · 고용 형태 · 근무지 · 모집 인원 · 접수 기간"]:::process
    mode -- "불러오기 (JOB-08)" --> importSrc{"출처?"}:::decision
    importSrc -- "공공 채용정보 Open API" --> importRun["공고 정보만 가져오기"]:::process
    importSrc -- "더미 데이터 (JSON · CSV)" --> importRun
    importRun --> dupCheck{"같은 공고(external_id)가 이미 있음?"}:::decision
    dupCheck -- 예 --> skipDup["건너뛰고 '이미 있음'으로 집계"]:::process
    dupCheck -- 아니요 --> importDraft["임시저장 공고로 저장<br/>직무가 AI/AX가 아니면 '직무 확인 필요' 표시"]:::process
    skipDup --> jobManage
    importDraft --> jobManage

    form --> criteria["평가 기준 설정 (기본값 제공)<br/>평가 항목 5개 가중치: 5% 단위 · 각 5% 이상 · 합 100%<br/>코딩테스트 사용 여부 · 반영 비중(기본 70:30, 10% 단위)<br/>1차 합격 기준 점수(기본 70점)"]:::process
    criteria --> valid{"필수 항목 · 가중치 합 · 접수 기간 검증"}:::decision
    valid -- 실패 --> form
    valid -- 통과 --> saveType{"저장 방식?"}:::decision
    saveType -- 임시저장 --> jobManage
    saveType -- "미리보기 후 게시" --> posted["게시 중<br/>마감 시각 예약 작업 등록"]:::process

    posted -- 수정 --> started{"첫 응시가 시작됐나?"}:::decision
    started -- 아니요 --> form
    started -- 예 --> locked["평가 기준 잠금<br/>가중치 · 반영 비중 · 합격 기준 · 코딩테스트 사용 여부<br/>적용 기준 버전 기록"]:::process
    locked --> contentOnly["공고 내용만 수정 · 저장<br/>평가 기준 칸은 비활성"]:::process
    contentOnly --> posted

    posted -- 삭제 요청 --> hasApplicant{"지원자 있음?"}:::decision
    hasApplicant -- 아니요 --> deleted["공고 삭제"]:::process
    hasApplicant -- 예 --> noDelete["삭제 불가 안내<br/>마감만 가능"]:::process
    noDelete --> posted

    posted -- "마감 시각 도달 · 관리자 수동 마감" --> closed["마감 (INT-10)<br/>준비 중 응시 → 미응시(마감)<br/>진행 중 · 장애 중단 → 즉시 종료 · 응시 종료(마감) · 채점 시작"]:::process
    closed --> publishSched(["결과 공개 예약 · 마감 다음 날 10:00 (08)"]):::startEnd
```

설계 기준: 질문은 관리자가 입력·선택·편집하지 않는다(JOB-06). 평가 항목과 루브릭은 수정할 수 없고 가중치만 조정한다(JOB-04). 코딩테스트 문제는 관리자가 화면에서 입력하지 않고 문제 은행에서 시스템이 출제한다(JOB-03). ‘준비 중’ 직무 6개는 직무 선택 목록에 보이지만 선택할 수 없다(2-4). 불러온 공고도 직무가 AI/AX 엔지니어여야 게시할 수 있다. 수동 마감 전 확인 창에서 진행 중 면접 건수를 알려 준다. 잠금 이후에는 기존 결과를 재산출하지 않는다(JOB-07).

---

## 03 지원·사전 준비

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef hub fill:#DBEAFE,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    jobDetail["공고 상세<br/>코딩테스트 포함 여부 · 예상 소요 시간 · 결과 공개일"]:::hub -- 지원하기 --> loggedIn{"로그인 상태?"}:::decision
    loggedIn -- 아니요 --> login["로그인 · 가입 (01)"]:::process
    login -- "인증 후 복귀" --> applyCheck
    loggedIn -- 예 --> applyCheck{"서버 검증<br/>접수 기간 · 중복 지원 · 응시 이력<br/>(이메일 인증 추가 후: 인증 여부)"}:::decision
    applyCheck -- "실패 (마감 · 이미 지원 · 응시 종료/취소 이력)" --> denied["지원 불가 사유 안내"]:::process
    denied --> jobDetail

    applyCheck -- 통과 --> consent["필수 동의 (APP-03)<br/>① 응시 데이터 수집·이용 ② AI 자동 평가와 AI의 1차 합격·불합격 판정<br/>③ 공고를 운영하는 관리자에게 결과 제공 ④ 보관 기간(응시 데이터 공개일 + 7일 · 녹화 3일)<br/>⑤ 응시 규칙(1회 응시 · 중단 버튼 없음 · 화면 이탈 경고/강제 퇴장)"]:::process
    consent --> agreed{"모두 동의?"}:::decision
    agreed -- 아니요 --> noConsent["다음 단계 진행 불가"]:::process
    noConsent --> jobDetail
    agreed -- 예 --> consentLog["동의 문구 버전 · 항목 · 일시 기록"]:::process

    consentLog --> resumeWay{"이력서 제출 방식?"}:::decision
    resumeWay -- "파일 업로드 (PDF · JPG · PNG)" --> fileCheck{"확장자 · 실제 파일 형식 일치?<br/>서버 보호 한도 이내? (사용자에게 비노출)"}:::decision
    fileCheck -- 아니요 --> failModal
    fileCheck -- 예 --> estimate["예상 처리 시간 표시<br/>글자 있는 쪽 × 0.5초 + 스캔 쪽 × 쪽당 OCR 시간 + AI 정리 시간<br/>경과 시간 함께 표시"]:::process
    estimate --> pageType{"쪽마다 글자 50자 이상?"}:::decision
    pageType -- "예 (텍스트 PDF 쪽)" --> textExtract["PDF 글자 바로 추출"]:::process
    pageType -- "아니요 (스캔 쪽 · 사진 파일)" --> ocr["온프레미스 OCR<br/>300dpi 이미지 변환 · 기울기 보정 · 줄별 신뢰도"]:::process
    ocr --> ocrOk{"OCR 실패 기준에 걸림?<br/>예상 시간의 2배(최소 60초) 초과<br/>읽은 글자 없음 · 평균 신뢰도 0.5 미만"}:::decision
    ocrOk -- 예 --> failModal["'이력서를 불러오는 데 실패했습니다'<br/>직접 입력하시겠어요?"]:::process
    failModal -- 다른 파일 올리기 --> resumeWay
    failModal -- 직접 입력하기 --> manual
    ocrOk -- 아니요 --> extract
    textExtract --> extract["AI 정보 정리<br/>학력 · 경력 · 프로젝트 · 기술 · 자격"]:::process
    resumeWay -- 직접 작성 --> manual["이력서 직접 작성"]:::process
    resumeWay -- 마이페이지 등록본 --> loadSaved["등록본 불러오기"]:::process
    extract --> confirm["지원자 확인 · 수정 (필수)<br/>OCR 신뢰도 0.80 미만 줄에서 나온 항목은 강조 표시"]:::process
    manual --> confirm
    loadSaved --> confirm
    confirm --> basicInfo{"기본 정보 충족?<br/>성명 + 학력 또는 경력 1건 이상"}:::decision
    basicInfo -- 아니요 --> confirm
    basicInfo -- 예 --> applied["지원 완료 · 응시 상태 '준비 중'<br/>이력서 스냅샷 저장(변경 불가)"]:::process
    applied -.-> composeStart(["질문 구성 백그라운드 시작 (04)"]):::startEnd

    applied --> envCheck["환경 점검 (APP-06)<br/>① 마이크 입력 레벨 ② 카메라 영상 ③ 스피커 테스트음 후 '들립니다' 확인<br/>④ 네트워크 상태 ⑤ AI 서버 상태"]:::process
    envCheck --> envOk{"모두 통과?"}:::decision
    envOk -- 아니요 --> envFix["실패 항목 안내 · 시작 버튼 비활성"]:::process
    envFix -- 재점검 --> envCheck
    envOk -- 예 --> rules["시작 전 안내 (APP-07)<br/>진행 방식 · 질문 수 · 답변 시간 · 코딩테스트 여부 · 예상 소요 시간<br/>중단 버튼 없음 · 장애 시 이어가기 · 화면 이탈 1회 경고 · 2회 취소<br/>공고 마감 시각에 면접이 끝남"]:::process
    rules --> ruleCheck{"규칙 확인 체크?"}:::decision
    ruleCheck -- 아니요 --> rules
    ruleCheck -- "예 · '면접 시작' 선택" --> capacity{"입장 가능?<br/>진행 중 면접이 상한 N건 미만 (INT-08)<br/>자동 보호(GPU 메모리 92% · 다음 질문 시간 초과) 꺼짐"}:::decision
    capacity -- 아니요 --> retryWait["'동시 면접 인원이 찼습니다' 안내 + '다시 시도' 버튼<br/>상태 '준비 중' 그대로 · 응시 횟수 미차감 · 대기 줄 없음<br/>버튼은 10초 동안 막음"]:::process
    retryWait -- 다시 시도 --> capacity
    retryWait -- 나중에 --> toMyPage(["마이페이지 (10)"]):::startEnd
    capacity -- 예 --> begin(["전체 화면 전환 → AI 면접 (05)<br/>질문이 덜 만들어졌으면 '질문 준비 중'(최대 60초)"]):::startEnd
```

설계 기준: 중복 지원·응시 이력 검증을 동의·이력서 입력보다 먼저 해서, 통과할 수 없는 지원자가 입력을 반복하지 않게 한다. 이력서 파일은 용량·쪽수 상한을 화면에 두지 않는다(APP-04). 자기소개서는 필수가 아니다(APP-05). OCR 중간 이미지는 처리 직후 지우고, 원본과 뽑은 글자는 면접 데이터로 보고 공개일 + 7일에 지운다(TRD 7-6). 지원 환경은 데스크톱 Chrome·Edge 최신 2개 버전이다. 상한 N은 운영 장비에서 측정해 정한 초기값으로 시작하며, 서비스 재시작 없이 바꿀 수 있다(AC-21). ‘다시 시도’ 안내는 추천안으로 팀 확인 대기 중이다.

---

## 04 질문 구성

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    begin(["이력서 확정 직후 (03)<br/>백그라운드 질문 만들기 줄에 등록"]):::startEnd --> budget["지원자 1명 질문 전체 제한 60초 시작"]:::process
    budget --> slots["문항 구성 고정 (모든 공고 공통)<br/>인성 2 · 이력서 기반 2 · 기업 관련 2 · 직무(AI/AX) 4 = 10문항"]:::process
    slots --> dbSearch["인성 · 기업 관련 · 직무 문항<br/>질문 DB 검색 · 선정<br/>공고에서 덜 쓰인 질문 우선 · 같은 중복 묶음 · 유사도 0.9 이상은 하나만<br/>직무는 코딩문제 '예' 질문 제외"]:::process
    slots --> resumeGen["이력서 기반 문항<br/>이력서 스냅샷 근거로 AI 생성 (비슷한 질문 예시 참고)"]:::process

    dbSearch --> enough{"카테고리별 후보 충분?"}:::decision
    enough -- 예 --> picked["DB 질문 선정<br/>기업 관련은 공고 본문에 맞게 AI 맥락화"]:::process
    enough -- 아니요 --> aiGen["같은 카테고리 질문 AI 생성 (QST-02)<br/>'생성' 표시"]:::process
    picked --> check
    aiGen --> check
    resumeGen --> check

    check{"검증<br/>형식 · 1번 시도 8초 이내<br/>QST-04 범위 적합성: 답변 시간(90초) 안에 요구하는 일 2개 이하<br/>이력서 기반은 서류에 근거 · 예시를 베끼지 않음"}:::decision
    check -- 통과 --> accept
    check -- "실패 (형식 오류 · 검증 미통과 · 8초 초과)" --> overBudget{"전체 60초 제한에 걸림?"}:::decision
    overBudget -- 아니요 --> regenCount{"이 문항 재생성 3회 미만?"}:::decision
    regenCount -- 예 --> regen["같은 조건으로 재생성<br/>평가 목적을 유지하며 범위 조정"]:::process
    regen --> check
    regenCount -- "아니요 · 3회 모두 실패" --> slotType{"이력서 기반 문항?"}:::decision
    overBudget -- "예 · 진행 중 시도 중단<br/>남은 문항은 AI 없이 채움" --> slotType
    slotType -- 아니요 --> dbAlt{"같은 카테고리의 검증된 DB 질문 있음?"}:::decision
    slotType -- 예 --> useSpare
    dbAlt -- 예 --> useDb["검증된 DB 질문으로 대체"]:::process
    dbAlt -- 아니요 --> useSpare["예비 질문에서 제시<br/>이력서 기반은 '경험·프로젝트' 종류"]:::process
    useDb --> accept
    useSpare --> accept
    accept["문항 확정<br/>재생성 횟수 · 실패 사유 · 대체 여부 기록"]:::process

    accept --> allFilled{"10문항 모두 확정?"}:::decision
    allFilled -- 아니요 --> slots
    allFilled -- 예 --> snapshot["질문 스냅샷 저장(변경 불가)<br/>카테고리별 평가 항목 · 답변 시간 부여<br/>기본 질문 음성(TTS) 미리 생성"]:::process
    snapshot --> toInterview(["면접 시작 시 바로 제시 (05)"]):::startEnd

    startPress(["지원자가 '면접 시작'을 눌렀는데 아직 미완료"]):::startEnd -.-> preparing["'질문 준비 중' 화면<br/>버튼을 누른 뒤 60초가 지나면 진행 중 시도 중단<br/>못 만든 문항은 DB 질문 → 예비 질문으로 채워 시작"]:::process
    preparing -.-> toInterview
```

설계 기준: 질문은 관리자의 검토·승인 없이 시스템이 자동 구성한다(JOB-06, QST-01~03). 이력서 확정 직후 미리 만들어 두므로 보통 지원자는 기다리지 않는다(QST-03). AI가 질문을 만들지 못하면 그 문항을 같은 조건으로 최대 3회 재생성하고, 3회 모두 실패하면 검증된 DB 질문으로, DB 후보도 없으면 예비 질문으로 대체한다. 이력서 기반 문항은 맞는 DB 종류가 없어 바로 예비 질문으로 간다(QST-05, TRD 7-4 ⑤). 대체는 감점·장애 판정 대상이 아니다. 예비 질문은 관리자가 미리 확인해 명령어·파일로 넣는다(종류별 5개 이상). 응시하지 않으면 응시 횟수를 쓰지 않으며, 쓰지 않은 질문 구성은 응시 데이터 보관 규칙대로 지운다. 평가와 리포트는 질문 스냅샷을 기준으로 한다.

---

## 05 AI 면접·꼬리질문

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    snap(["질문 스냅샷 · 전체 화면 (04)"]):::startEnd --> present["질문 제시<br/>미리 만든 TTS 음성 + 자막 · 진행 표시 '3 / 10'<br/>음성이 없으면 자막만으로 진행"]:::process
    present --> countdown["음성 종료 후 3-2-1 카운트다운"]:::process
    countdown --> record["답변 실시간 전송 (WebRTC) · 카메라 녹화 · 임시 자막<br/>기본 질문 90초 · 꼬리질문 60초<br/>'답변 완료'로 먼저 넘길 수 있음"]:::process
    record -- "답변 완료 · 시간 만료" --> stt["STT 최종 글자 변환<br/>질문별 음성 · 텍스트 · 시각 저장"]:::process
    stt --> sttOk{"변환 성공?<br/>(최대 2회 재시도)"}:::decision
    sttOk -- 아니요 --> sttFail["시스템 장애로 처리<br/>같은 질문 다시 답변 · 감점 없음"]:::process
    sttFail --> present
    sttOk -- 예 --> empty{"내용 없는 답변?<br/>'잘 모르겠습니다' 등"}:::decision

    empty -- "예 · 꼬리질문 없음" --> nextQ
    empty -- 아니요 --> limit{"이 질문에 꼬리질문 없음<br/>그리고 전체 4개 미만?"}:::decision
    limit -- 아니요 --> nextQ
    limit -- 예 --> timeLeft{"판단에 쓸 남은 시간 ≥ 최소 판단 시간?<br/>남은 시간 = 다음 질문 목표 시간 − STT에 걸린 시간 − 꼬리질문 음성 평균 시간"}:::decision
    timeLeft -- "아니요 · 생략" --> nextQ
    timeLeft -- 예 --> needFollow{"면접 중 LLM 꼬리질문 판단 (남은 시간 제한)<br/>① 논리성 · 내용 관련성 2점 이하<br/>② 이력서 기재 내용과 다름<br/>③ 구체 사례 없는 일반론"}:::decision
    needFollow -- "아니요 · 시간 초과 · 형식 오류" --> nextQ
    needFollow -- 예 --> followTts{"목표 시간 안에 꼬리질문 음성(TTS) 생성?"}:::decision
    followTts -- 예 --> follow["꼬리질문 제시 (음성 + 자막)<br/>같은 번호에 '꼬리질문' 표시 · 답변 1개 근거"]:::process
    followTts -- 아니요 --> followText["꼬리질문 자막만으로 제시"]:::process
    follow --> countdown
    followText --> countdown

    nextQ{"남은 기본 질문?"}:::decision
    nextQ -- 예 --> present
    nextQ -- 아니요 --> finish(["AI 면접 종료<br/>코딩테스트 사용 → 06 · 미사용 → 응시 완료 (07)"]):::startEnd

    nextQ -.-> preEval["질문 번호가 끝날 때마다 미리 채점 (07, 백그라운드)<br/>꼬리질문이 있으면 그 답변까지 합쳐 채점"]:::process
    record -.-> watch["상시 감시<br/>연결 장애 → 11 · 화면 이탈 → 12 · 공고 마감 → 즉시 종료"]:::process
```

설계 기준: 중단·일시정지 버튼은 없다(INT-03). 면접관 아바타는 쓰지 않는다(INT-01). 답변이 끝나고 다음 질문이 뜨기까지의 목표 시간은 운영 서버에서 재서 정하며(TRD 12장), 꼬리질문 판단에는 고정 시간 대신 그 답변의 남은 시간만 준다. 녹화는 평가에 쓰지 않고 장애·부정행위 판정 확인용으로 3일만 보관한다(INT-05). 꼬리질문은 거짓 여부를 판정하지 않는다. 내용 없는 답변은 같은 질문을 반복하지 않고 해당 문항을 1점으로 평가한다(INT-07). 예상 소요 시간은 약 25분이다.

---

## 06 코딩테스트 응시·채점

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    fromInterview(["AI 면접 종료 직후 시작<br/>코딩테스트 사용 공고 · 건너뛰기 불가<br/>동시 면접 자리는 이때 돌려줌"]):::startEnd --> assign["시스템 출제<br/>문제 은행 AI/AX 2문항(기초 1 · 응용 1)<br/>Python 3 · 2문항 합계 60분"]:::process
    assign --> editor["문제 · 입출력 예시 · 남은 시간 · 코드 편집기<br/>30초마다 자동 저장"]:::process
    editor --> act{"지원자 동작"}:::decision
    act -- 실행 --> runSample["공개 예제 실행<br/>실행 결과 · 오류 표시"]:::process
    runSample --> editor
    act -- "외부 붙여넣기" --> pasteBlock["붙여넣기 차단 · 시도 횟수 기록"]:::process
    pasteBlock --> editor
    act -- 최종 제출 --> sure{"제출 확인?"}:::decision
    sure -- 아니요 --> editor
    sure -- 예 --> submitted
    act -- "제한시간 종료 · 공고 마감" --> autoSubmit["마지막 저장 코드 자동 제출"]:::process
    autoSubmit --> submitted["제출 코드 확정 · 응시 완료"]:::process

    submitted --> sandbox["격리 실행 · 채점<br/>네트워크 차단 · 문항당 실행 10초 · 메모리 256MB · CPU 1개<br/>공개 + 비공개 테스트케이스"]:::process
    sandbox --> envOk{"실행 환경 정상?"}:::decision
    envOk -- "예 (코드 오류 · 시간 초과 포함)" --> score["코딩테스트 점수 = 테스트케이스 통과율 × 100<br/>2문항 동일 배점"]:::process
    envOk -- "아니요 · 인프라 오류" --> retry{"자동 재시도 3회 이내?<br/>(1 · 2 · 4분 간격)"}:::decision
    retry -- 예 --> sandbox
    retry -- "아니요 · 30분 초과" --> ops["'확인 필요' 전환 · 관리자 재처리"]:::process
    ops --> sandbox
    score --> codeReview["AI 코드 서술 피드백<br/>관리자 리포트 전용 · 점수 미반영"]:::process
    codeReview --> toEval(["평가 · 합불 판정 (07)"]):::startEnd

    editor -.-> watch["상시 감시<br/>연결 장애 → 11 · 화면 이탈 → 12(면접과 횟수 합산)"]:::process
```

설계 기준: **AI 도우미 없이 일반 코딩테스트로 진행하며, AI 사용 이력은 수집하지 않는다.** 코드 관련 꼬리질문도 제공하지 않는다(COD-06). 점수는 작성 코드의 테스트케이스 통과율로만 계산한다. 실행만으로는 응시가 완료되지 않고 최종 제출(또는 시간 종료·마감 자동 제출)이 필요하다(COD-01). 정답과 비공개 테스트는 지원자 화면과 AI 입력에 노출하지 않는다(COD-05). 실행 환경 오류는 지원자 오답으로 처리하지 않으며, 재시도는 뒤에서 도는 작업 공통 규칙을 따른다(TRD 8-3). 시스템 장애로 끊긴 시간은 남은 시간에서 빼지 않는다(COD-04). 코딩테스트는 동시 면접 상한 N에 세지 않는다(추천안).

---

## 07 평가·채점·AI 1차 합불 판정

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    complete(["응시 완료 · 응시 종료 · 응시 종료(마감) · 응시 취소"]):::startEnd --> cancelled{"부정행위로 응시 취소?"}:::decision
    cancelled -- 예 --> autoFail["평가 없이 1차 불합격<br/>사유: 응시 취소"]:::process
    autoFail --> save

    cancelled -- 아니요 --> zero["미응답 · 미제시 문항 0점 (시스템)"]:::process
    zero --> rubric["문항별 루브릭 평가 (채점용 AI)<br/>해당 평가 항목 0~5점 + 답변 원문 인용<br/>꼬리질문 답변은 원 문항에 합쳐 평가<br/>질문 번호마다 미리 채점한 결과 사용"]:::process
    rubric --> evalErr{"분석 오류?"}:::decision
    evalErr -- 예 --> errRetry{"자동 재시도 3회 이내 · 30분 이내?<br/>(1 · 2 · 4분 간격)"}:::decision
    errRetry -- 예 --> rubric
    errRetry -- 아니요 --> delayed["'확인 필요' · 관리자 알림 · 관리자 재처리<br/>관리자 화면 '평가 지연'"]:::process
    delayed --> rubric
    evalErr -- 아니요 --> verify{"형식 · 점수 범위(0~5 정수) · 인용 원문 일치?"}:::decision
    verify -- 예 --> itemScore
    verify -- 아니요 --> regenDone{"이미 1회 다시 받음?"}:::decision
    regenDone -- 아니요 --> regen["1회 다시 받기"]:::process
    regen --> verify
    regenDone -- 예 --> floor["답했으면 1점 · 답이 없으면 0점 확정"]:::process
    floor --> itemScore

    itemScore["항목 점수 = 해당 항목 문항 점수 평균 ÷ 5 × 100 (시스템)"]:::process
    itemScore --> interviewScore["AI 면접 점수 = Σ(항목 점수 × 가중치)<br/>소수 둘째 자리까지"]:::process
    interviewScore --> useCode{"코딩테스트 사용 공고?"}:::decision
    useCode -- 예 --> totalMix["종합 총점 = AI 면접 점수 × 면접 비중 + 코딩테스트 점수 × 코딩 비중<br/>기본 70 : 30 (06 점수 사용)"]:::process
    useCode -- 아니요 --> totalOnly["종합 총점 = AI 면접 점수"]:::process
    totalMix --> aiJudge
    totalOnly --> aiJudge["AI 1차 합불 판정 (EVL-05)<br/>항목 점수 · 종합 총점 · 합격 기준(기본 70점) · 항목별 근거 문장을 보고<br/>1차 합격/불합격 + 판정 사유(근거 문장으로 설명)"]:::process
    aiJudge --> judgeCheck{"시스템 결과 검증 (TRD 8-2 ⑤)<br/>(a) 형식 (b) 값 범위: 합격/불합격 중 하나 · 사유 있음<br/>(c) 근거 문장이 답변 원문에 있음"}:::decision
    judgeCheck -- "통과 · 합격" --> pass["1차 합격 확정"]:::process
    judgeCheck -- "통과 · 불합격" --> fail["1차 불합격 확정"]:::process
    judgeCheck -- 실패 --> rejudged{"이미 1회 다시 판정?"}:::decision
    rejudged -- 아니요 --> rejudge["AI에 1회 다시 판정 요청"]:::process
    rejudge --> judgeCheck
    rejudged -- 예 --> judgeHold["'판정 전' 유지 · '확인 필요' 전환 (EVL-08)<br/>관리자 알림 · 관리자 재처리 · 관리자 화면 '평가 지연'"]:::process
    judgeHold --> aiJudge
    pass --> save
    fail --> save["결과 저장 · 누구도 수정 불가<br/>적용 기준(가중치 · 반영 비중 · 합격 기준 · 버전) · 점수 구성 · 항목별 근거<br/>AI 판정과 판정 사유 · 모델 · 지시문 · 루브릭 버전 · 장애/이탈 기록 요약"]:::process
    save --> toPublish(["결과 공개 대기 (08)<br/>관리자는 판정 즉시 확인 (09)"]):::startEnd
```

평가 항목과 기본 가중치: 직무 전문성 30% · 논리성 25% · 내용 관련성·구체성 20% · 전달력 10% · 조직 적합성 15%.

루브릭 척도: 0 미응답 · 1 답변했으나 최저 수준(관련성 거의 없음, ‘모르겠습니다’, 근거 인용 불가) · 2 부분적 · 3 기본 충족 · 4 우수 · 5 탁월.

설계 기준: AI는 루브릭 채점·근거 인용과 함께 1차 합격·불합격과 판정 사유를 낸다. 시스템은 점수를 집계하고 AI 결과의 형식·값 범위·근거 문장을 검증하며, 합격 여부를 ‘총점 ≥ 합격 기준’ 같은 별도 규칙으로 다시 판정하지 않는다(1-3 ②, EVL-03~06, TRD 1-2). 검증을 통과한 결정만 확정한다(AC-13). 같은 작업이 두 번 돌아도 결과는 한 번만 생기게 한다(TRD 8-3). 부정행위로 취소된 응시는 평가 없이 1차 불합격이다. 이름·연락처 등 인적 정보와 음성 특성은 평가 입력에서 뺀다. 관리자의 승인 단계와 수정 기능은 없다. 응시 완료 후 p90 10분 안에 결과를 산출하며, ‘분석 실패’라는 최종 상태는 두지 않는다(EVL-08).

---

## 08 결과 공개·알림·보관 삭제

### 08-A 결과 공개와 보관

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    examDone(["응시 완료"]):::startEnd --> doneNotice["완료 안내<br/>'응시가 완료되었습니다. 결과는 OO월 OO일 10:00에 공개됩니다'"]:::process

    closed(["공고 마감 시각 (02)<br/>이 시각에 모든 응시가 끝남"]):::startEnd --> schedule["결과 공개 예약<br/>지원 건마다 공개 시각 = 마감 다음 날 10:00<br/>삭제 예정 = 공개 시각 + 7일"]:::process
    schedule --> ready{"매일 10:00 · 공개 시각이 지난 건의 결과 확정?"}:::decision
    ready -- 예 --> publish["공개<br/>1차 합격 · 불합격 · 강점·개선점(각 최대 3개) · 응시 상태(취소 · 마감 시 사유)<br/>'AI가 생성한 결과입니다' 안내"]:::process
    ready -- "아니요 · 평가 지연('확인 필요')" --> lateNotice["해당 지원자에게 지연 안내"]:::process
    lateNotice --> lateCalc["결과가 확정되면 공개 시각을 다음 날 10:00으로 다시 정함<br/>삭제 예정도 그 공개 시각 + 7일로"]:::process
    lateCalc --> ready
    publish --> sendPub["사이트 내 알림 + 이메일 (08-B)"]:::process
    sendPub --> viewing["지원자 열람 기간<br/>공개일로부터 7일"]:::process
    viewing --> expireWarn["보관 만료 2일 전 알림<br/>지원자(건별) · 관리자(매일 09:00 공고별 묶음)"]:::process
    expireWarn --> purge["매일 03:00 · 삭제 예정이 지난 건 자동 삭제<br/>이력서 스냅샷 · 원본 · 답변 음성/텍스트 · 코드 · 결과 · 리포트 · 메모<br/>파생 데이터(임베딩 · 캐시 · OCR 추출 텍스트 · 진행 상태 기록) · 지원 이력 포함"]:::process

    notTaken(["미응시(마감)"]):::startEnd --> notTakenPurge["평가 없음 · 같은 삭제 규칙 적용"]:::process
    notTakenPurge --> purge

    examEnd(["응시 끝난 시점<br/>(완료 · 종료 · 마감 종료 · 취소)"]):::startEnd --> recPurge["+3일: 카메라 녹화 자동 삭제"]:::process

    purge --> purgeLog["삭제 기록 저장 (3년)<br/>원문 없이 식별자 · 시각 · 행위만"]:::process
    recPurge --> purgeLog
```

설계 기준: 공개 전에는 결과가 지원자 화면·API에 나타나지 않는다. 지원자 공개용 결과는 관리자용과 별도로 만들며, 점수·총점·코딩테스트 세부·근거 인용·내부 기록은 공개하지 않는다(RPT-03, RPT-04). 이의제기·근거 설명 요청 창구는 두지 않는다(N7). 모든 예약 작업과 날짜 계산은 한국 시간 기준이다. 삭제 작업은 매일 실행하고 결과를 기록한다(10-3).

### 08-B 알림 발송

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    trigger(["알림 이벤트"]):::startEnd --> kind{"이벤트 종류 (ADM-08 · TRD 10장)"}:::decision
    kind -- "신규 지원 · 공고 마감 1일 전 · '확인 필요' 발생" --> toManager["관리자"]:::process
    kind -- "삭제 2일 전 (매일 09:00, 공고별 한 통)" --> toManager
    kind -- "미완료 지원자 마감 3일 전 · 1일 전 (매시 점검)" --> toApplicant["지원자 리마인더"]:::process
    kind -- "결과 공개" --> toApplicant2["지원자"]:::process
    kind -- "결과 보기 종료 2일 전 (건별)" --> toApplicant2
    toManager --> dedup
    toApplicant --> dedup
    toApplicant2 --> dedup{"수신자 유효 · 중복 키 검증"}:::decision
    dedup -- 아니요 --> skipLog["중복 · 수신 불가 기록"]:::process
    dedup -- 예 --> siteNoti["사이트 내 알림 생성 (메일 결과와 관계없이 항상)"]:::process
    siteNoti --> dailyCap{"오늘 메일 발송 한도 이내?<br/>(Gmail 약 500통)"}:::decision
    dailyCap -- 아니요 --> defer["다음 날로 미룸 · 관리자 대시보드에 표시"]:::process
    defer --> send
    dailyCap -- 예 --> send["이메일 발송 (팀 Gmail SMTP)<br/>알림 문구 · 링크만 · 답변 · 점수 · 이력서 내용 없음"]:::process
    send --> sent{"발송 결과?"}:::decision
    sent -- 성공 --> log["발송 이력 저장"]:::process
    sent -- "일시 오류(4xx) · 연결 실패" --> sendRetry{"재시도 3회 이내?<br/>(60초 · 300초 · 1800초 뒤)"}:::decision
    sendRetry -- 예 --> send
    sendRetry -- 아니요 --> failLog
    sent -- "영구 오류(5xx · 주소 없음)" --> failLog["발송 실패 기록 · 사유 저장<br/>관리자 대시보드에 실패 건수 표시"]:::process
    skipLog --> log
    failLog --> log
```

설계 기준: 면접 일정 관리·통보 기능과 외부 캘린더 연동은 범위 밖이다(N1, N5, C-23). 같은 이벤트는 한 번만 발송한다.

---

## 09 관리자 결과 관리

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef hub fill:#DBEAFE,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    home["공고 관리 (관리자 홈)"]:::hub --> menu{"메뉴"}:::decision
    menu -- 공고 --> toJob(["공고 작성 · 평가 기준 · 불러오기 (02)"]):::startEnd
    menu -- 대시보드 --> stats["통계 (집계값 · 개인 식별 정보 없음)<br/>월별 응시자 수 · 공고별 1차 합격률 · 평균 점수<br/>장애 이어가기 · 부정행위 취소 건수 (미응시(마감) 제외)"]:::process
    stats --> opsStatus["운영 현황<br/>'확인 필요' 목록 · 재처리 · 메일 발송 실패 건 · 예비 질문 수"]:::process
    opsStatus -- 복귀 --> home
    menu -- 운영 설정 --> settings["동시 면접 상한 N 변경<br/>다음 시작 요청부터 바로 적용 · 진행 중 면접은 유지 · 감사 로그"]:::process
    settings -- 복귀 --> home
    menu -- 지원자 --> list["지원자 목록<br/>공고 · 1차 결과 · 상태 필터<br/>AI 면접 · 코딩테스트 · 종합 점수 · AI 1차 판정 · 분석/장애/이탈 상태"]:::hub
    list -- 복귀 --> home

    list --> analyzed{"분석 완료?"}:::decision
    analyzed -- 아니요 --> statusOnly["상태만 표시<br/>분석 대기 · 분석 중 · 평가 지연 · 미응시(마감)<br/>'확인 필요'면 재처리 버튼"]:::process
    statusOnly --> list
    analyzed -- 예 --> action{"작업 선택"}:::decision

    action -- 상세 --> detail["지원자 상세<br/>표준 양식 이력서 · 원본 파일(OCR 여부 · 신뢰도) · 리포트(AI 1차 판정 · 판정 사유)<br/>질문별 질문 · 답변 원문 · 근거 · 적용 기준"]:::process
    detail --> media["녹화 재생: 장애·이탈 판정 확인용, 응시 끝 + 3일 이내<br/>하이라이트 플레이어: 우수·감점 구간 음성, 공개 + 7일 이내<br/>재생할 때마다 감사 로그"]:::process
    media --> list
    action -- "비교 (2~3명)" --> compare["점수 · 항목 점수 · 강점 · 개선점 대조<br/>참고용 · 결과 불변"]:::process
    compare --> list
    action -- 메모 --> memo["내부 메모 작성 · 수정 · 삭제<br/>관리자만 열람 · 지원자 비공개"]:::process
    memo --> list
    action -- 다음 전형 --> nextStage["1차 합격자 목록 · 필터 · 연락처 확인<br/>2차 일정 관리 · 통보 기능 없음"]:::process
    nextStage --> list
```

설계 기준: 관리자는 AI 판정 결과와 판정 사유·적용 기준·근거를 확인만 하며, 판정을 바꾸는 버튼·입력은 없다(ADM-01, AC-14). 재처리는 같은 응시 자료로 분석을 다시 돌릴 뿐 판정을 사람이 고치지 않는다(EVL-08). 관리자는 판정 즉시 결과를 볼 수 있지만, 지원자에게는 마감 다음 날 10:00에 공개된다. 응시 데이터는 결과 공개일로부터 7일 뒤 삭제되므로 다음 전형 대상자 관리는 그 안에 끝내야 하며, 삭제 2일 전 알림을 보낸다(ADM-06). 문제 은행·예비 질문은 관리 화면 없이 명령어·파일로 넣는다. 관리자용 리포트 구성은 RPT-01을 따른다.

---

## 10 지원자 마이페이지

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef hub fill:#DBEAFE,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    jobList["공고 목록"]:::hub -- 마이페이지 --> myPage["마이페이지"]:::hub
    myPage -- 공고 목록으로 --> jobList
    myPage --> menu{"메뉴"}:::decision

    menu -- 지원 내역 --> apps["지원 내역 · 응시 상태<br/>준비 중 · 면접 진행 중 · 코딩테스트 진행 중 · 장애 중단<br/>응시 완료 · 응시 종료 · 응시 종료(마감) · 응시 취소 · 미응시(마감)"]:::process
    apps --> state{"응시 상태?"}:::decision
    state -- "준비 중 · 마감 전 (동시 면접 상한으로 못 시작한 경우 포함)" --> startLater(["응시 준비 계속하기 → 환경 점검 (03)"]):::startEnd
    state -- "장애 중단 · 공고 마감 시각 전" --> resumeExam(["면접 이어가기 (11)"]):::startEnd
    state -- "미응시(마감) · 응시 종료(마감)" --> closedMsg["'마감이 되어 면접을 진행할 수 없습니다' · 버튼 없음<br/>응시 종료(마감)은 답한 문항까지 평가"]:::process
    closedMsg --> myPage
    state -- 그 외 --> myPage

    menu -- 결과 --> published{"결과 공개됨?"}:::decision
    published -- 아니요 --> pending["공개 예정일 안내<br/>평가 지연이면 '산출이 끝나면 다음 날 공개'<br/>미응시(마감)은 '평가되지 않았습니다'"]:::process
    pending --> myPage
    published -- 예 --> result["1차 합격 · 불합격 · 강점·개선점 · 응시 상태<br/>'AI가 생성한 결과입니다' · 열람 가능 기한(공개 + 7일) 표시"]:::process
    result --> myPage

    menu -- 이력서 --> resumeMgr["등록 이력서 관리 (파일 업로드 · OCR · 직접 작성)<br/>지원에 쓴 스냅샷은 변경되지 않음"]:::process
    resumeMgr --> myPage

    menu -- 계정 --> account["회원 정보"]:::process
    account -- "동의 철회 · 탈퇴" --> withdraw["진행 중 응시 취소 · 응시 데이터 즉시 삭제<br/>탈퇴 시 계정 즉시 삭제"]:::process
    account -- 복귀 --> myPage
```

설계 기준: 응시는 공고 상세의 지원 절차(03)에서 시작한다. 마이페이지에서 응시로 들어가는 경로는 지원을 마쳤지만 아직 시작하지 않은 경우(동시 면접 상한으로 못 시작한 경우 포함, INT-08)와 장애 이어가기(RES-03) 두 가지다. 공고 마감 시각이 지나면 두 경로 모두 막힌다(INT-10). 보관 기간이 지나면 지원 이력과 결과가 함께 지워져 목록에서 사라진다(10-2). 지원에 쓴 이력서와 서류는 수정할 수 없다(APP-05).

---

## 11 장애 이어가기

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    running["면접 · 코딩테스트 진행 중<br/>heartbeat 5초 주기"]:::process --> detect{"연결 이상 감지?<br/>heartbeat 3회(15초) 누락 · WebSocket 비정상 해제<br/>브라우저 offline · 장치 스트림 중단 · 업로드 3회 실패 · 서버/AI 오류"}:::decision
    detect -- 아니요 --> running
    detect -- "예 · 그 순간 바로 판단" --> judge{"끊기기 직전 30초 안에<br/>창 닫기(beforeunload · pagehide) 또는 권한 끄기 기록?"}:::decision

    judge -- "예 · 장애 아님<br/>탭·브라우저 닫기 · 새로고침 · 뒤로가기 · 주소 이동<br/>마이크·카메라 권한 직접 해제" --> examEnd["응시 종료 · 자리 바로 돌려줌<br/>완료 답변까지 평가 · 남은 기본 문항 0점<br/>코딩테스트는 마지막 저장 코드로 채점 · 재응시 없음"]:::process

    judge -- "아니요 · 장애<br/>네트워크 단절 · 브라우저/기기 비정상 종료 · 장치 오류<br/>업로드 실패 · 서버/AI 장애 · 원인 불명<br/>(질문 생성 실패는 장애가 아니라 QST-05로 처리)" --> pause["'장애 중단' 상태 · 타이머 정지<br/>마지막 질문 · 저장된 답변 · 남은 시간 · 발생 시각 · 진행 상태 저장"]:::process
    pause --> seat["동시 면접 자리는 10분만 맡아 둠<br/>10분이 지나면 자리만 돌려줌 (이어가기 기한과 별개)"]:::process
    seat --> notice["지원자 안내<br/>'연결이 끊겼습니다. 답변은 안전하게 저장되었습니다.<br/>공고 마감 시각까지 다시 접속하면 이어서 진행합니다'"]:::process
    notice --> rejoin{"공고 마감 시각 전에 재접속?<br/>마이페이지 '면접 이어가기'"}:::decision
    rejoin -- "아니요 · 마감 시각 도달" --> timeout["응시 종료(마감) (INT-10)<br/>저장된 답변까지 평가 · 제시되지 않은 문항 0점<br/>코딩테스트는 마지막 저장 코드로 채점"]:::process
    rejoin -- 예 --> recheck["환경 재점검 (03 환경 점검 재사용)<br/>동시 면접 상한 N은 다시 확인하지 않음"]:::process
    recheck --> resume["이어가기 (횟수 무제한)<br/>면접: 끊긴 질문을 처음부터 다시 제시 · 답변 시간 새로 부여 · 완료 답변 유지<br/>코딩테스트: 마지막 자동 저장 코드에서 남은 시간으로 재개"]:::process
    resume --> running

    timeout --> toEval(["평가 (07)"]):::startEnd
    examEnd --> toEval
    pause -.-> logs["판정 결과 · 사유를 지원자 · 관리자 화면에 기록<br/>장애 이벤트는 리포트 · 감사 로그에 저장, 점수에는 영향 없음"]:::process
    examEnd -.-> logs
```

설계 기준: 장애로 끊긴 시간은 면접 답변 시간과 코딩테스트 제한시간에서 빼지 않는다(RES-01). 판정은 끊긴 지 15초가 되는 순간 시스템이 직전 기록을 근거로 자동 수행하며, 재접속 때까지 미루지 않고 수동 검토 단계도 없다(TRD 7-2). 원인을 특정할 수 없거나 창 닫기 기록이 서버에 오지 못했으면 지원자에게 유리하게 장애로 판정한다. 자리를 이미 돌려준 뒤 다시 들어와도 N을 다시 확인하지 않는다(TRD 5-3). 장애로 판정된 연결 소실은 화면 이탈 횟수에 넣지 않는다(CHT-04).

---

## 12 부정행위: 화면 이탈

```mermaid
flowchart TD
    classDef startEnd fill:#F8FAFC,stroke:#334155,color:#334155
    classDef decision fill:#FEF3C7,stroke:#334155,color:#334155
    classDef process fill:#F8FAFC,stroke:#334155,color:#334155

    running["면접 · 코딩테스트 진행 중"]:::process --> leave{"화면 이탈 감지?<br/>탭 숨김 · 창 포커스 이탈 · 전체 화면 해제<br/>다른 사이트 이동 시도"}:::decision
    leave -- 아니요 --> running
    leave -- 예 --> excluded{"제외 대상?<br/>장애로 판정된 구간(11) · 2초 미만 포커스 이탈"}:::decision
    excluded -- 예 --> notCounted["이탈 횟수 미포함"]:::process
    notCounted --> running
    excluded -- 아니요 --> count{"누적 이탈 횟수<br/>(면접 + 코딩테스트 합산)"}:::decision

    count -- 1회 --> warn["그 순간 남은 시간 저장 · 시간 정지 · 경고 모달<br/>'한 번 더 이탈하면 면접이 취소됩니다'<br/>화면을 벗어난 동안 · 모달이 떠 있는 동안 시간이 흐르지 않음"]:::process
    warn --> ack["확인 → 전체 화면 복귀"]:::process
    ack --> stage{"현재 단계?"}:::decision
    stage -- AI 면접 --> continueQ["같은 질문을 멈춘 시점의 남은 시간부터 이어 답변<br/>(답변 시간 새로 주지 않음)<br/>이탈 전후 음성을 합쳐 하나의 답변으로 글자 변환 · 채점"]:::process
    continueQ --> running
    stage -- 코딩테스트 --> keepTime["남은 시간 그대로 계속"]:::process
    keepTime --> running

    count -- 2회 --> kick["즉시 강제 퇴장 · 인터뷰 자동 취소 · 자리 돌려줌<br/>상태 '응시 취소' · 재응시 불가"]:::process
    kick --> autoFail(["1차 불합격<br/>사유: 부정행위로 인한 응시 취소 (07)"]):::startEnd

    warn -.-> evidence["이탈 이벤트 기록<br/>유형 · 시각 · 지속 시간 · 회차 + 카메라 녹화(3일)<br/>점수에는 반영하지 않음"]:::process
    kick -.-> evidence
```

설계 기준: 이탈은 경고와 취소로만 처리하고 점수에 반영하지 않는다(CHT-05). 시선 추적·얼굴 표정 분석으로 부정행위를 판정하지 않는다(CHT-06). 관리자는 이탈 기록과 녹화로 판정 근거를 확인할 수 있다. 1회차 이탈 뒤 남은 시간부터 이어 가는 방식은 TRD v1.5 7-3을 따랐다. PRD v1.3 CHT-02는 아직 ‘답변 시간 새로 부여’로 적혀 있어 PRD 개정 때 맞춰야 한다.

---

## 문서 간 확인이 필요한 부분

08v에서는 07v ‘PRD에 정의되지 않아 가정한 부분’ 표의 항목이 모두 정리되었다. OCR은 PRD v1.3 APP-04로, 예비 질문 관리 주체는 단일 관리자(TRD 15장 T-05)로, 08-A 지연 공개는 마감 즉시 종료(INT-10)로, 06 재시도는 TRD 8-3으로, 운영자는 단일 관리자(N8)로 확정됐다. 질문 구성 시점(QST-03), 근거 설명 요청 창구(N7 없음), 알림 수신자·메일 재시도(TRD 10장)도 정해졌다.

남은 것은 문서끼리 말이 다른 아래 항목이다.

| 위치 | 내용 | 도면의 선택 | 근거 |
|---|---|---|---|
| 12 화면 이탈 | 1회차 이탈 뒤 답변 시간: PRD v1.3 CHT-02는 새로 부여, TRD v1.5 7-3은 남은 시간부터 이어 감 | TRD를 따름 | CHT-02, TRD 7-3 |
| 05 AI 면접 | STT 최종 실패: PRD INT-04·화면정의서 D-02는 같은 질문 다시 답변, TRD v1.5 7-2는 장애(장애 중단 화면)로 분류 | PRD를 따름 | INT-04, TRD 7-2 |
| 03·10 동시 면접 상한 | PRD 6-2는 ‘대기’ 상태를 두지만, TRD 7-1은 저장 상태 없이 ‘다시 시도’ 안내만 둠(추천안, 팀 확인 대기) | TRD를 따름 | INT-08, TRD 5-3·7-1 |
| 전체 | TRD v1.5는 PRD v1.6을 기준으로 적혀 있으나 팀에 공유된 PRD는 v1.3 | v1.3 + TRD v1.5 | TRD 표지 |
