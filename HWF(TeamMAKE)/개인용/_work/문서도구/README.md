# 문서 도구 — 가이드 PDF · 활동 다이어그램 · 프로그램명세서 표

임시 폴더에 있던 스크립트를 2026-11-16 에 여기로 옮겼다. 경로는 `C:\big21\hw-repo\HWF(TeamMAKE)` 기준으로 박혀 있다.
PDF·PNG 를 인쇄할 때 `huge/e2e/node_modules` 의 Playwright 크롬을 쓴다(`cd huge/e2e && npm ci` 가 되어 있어야 함).
만든 html·png·json 은 각 폴더 안에 생기고 `.gitignore` 로 뺀다.

| 폴더 | 만드는 것 | 돌리기 (그 폴더에서) |
|---|---|---|
| `pdfguide/` | `개인용/가이드/*.pdf` 6개 | `python build.py && python build_course.py && node render.js` |
| `activity/` | `개인용/활동다이어그램/` PNG 9장 · md · 다크 PDF | `python diagrams.py && node shot2.js png && python make_md.py && python build_dark.py && node pdf_dark.js "../../활동다이어그램/활동다이어그램_다크모드.pdf"` |
| `guidegen/` | `개인용/가이드/프로그램명세서.md` 의 함수 표 | `python extract_py.py && python extract_ts.py && python refresh.py --dry` → 설명 없는 항목을 `new_desc.py` 에 채운 뒤 `python refresh.py` |

## 알아 둘 것

- **가이드 그림**은 md 안에 없고 `pdfguide/figs.py`·`figs2.py` 가 SVG 로 그려 넣는다. 메뉴·흐름이 바뀌면 md 와 그림을 둘 다 고친다(예: `adminMenu`, `questionFunnel`).
- **표지 날짜**는 `build.py`·`build_course.py`, 다크 PDF 표지 날짜는 `build_dark.py` 에 박혀 있다.
- **코드읽기코스 화면 사진**은 `pdfguide/shots/*.png`. E2E 로 찍는다: 임시 spec `huge/e2e/tests/_guide-shots.spec.ts` 를 만들어 `SHOT_DIR=<shots 폴더> npx playwright test _guide-shots` 로 돌리고 지운다(면접 한 번을 끝까지 하므로 몇 분 걸림).
- **활동 다이어그램 md** 는 `make_md.py` 가 통째로 다시 쓴다. md 를 손으로 고쳤다면 `make_md.py` 의 글(ITEMS)과 `diagrams.py` 도 같이 고친다.
- **프로그램명세서**: `refresh.py` 는 '하는 일'을 이미 적힌 글 그대로 두고 줄·인자·부르는 곳만 새로 뽑는다. 그래서 동작이 바뀐 함수는 설명을 따로 고쳐야 한다 — 2026-11-16 에는 `post_1116.py`(개요 표·가져오기 줄·낡은 설명·새 화면 절·머리말)와 `tests_1116.py`(5장 테스트 표)로 고쳤다. 코드읽기코스의 줄 번호는 `guidegen/course_lines.py`(코드 발췌 블록, `--fix` 면 통째로 옮김)·`course_refs.py`(`파일:줄` `이름` 짝, `--fix`)로 대조한다 — 줄 끝 주석은 무시하고, 옮겨도 안 맞는 블록은 코드가 바뀐 것이라 손으로 다시 쓴다. 2026-11-18 에는 `post_1118.py`(개요 표·새 파일 줄·역할·낡은 설명·테스트 표·머리말을 한 번에) 하나로 고쳤다. 다음에 쓸 때는 날짜와 DESC·ROWS 목록을 바꿔 쓴다.
