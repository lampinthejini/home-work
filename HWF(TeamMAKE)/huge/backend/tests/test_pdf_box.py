"""PDF 는 별도 프로세스에서 읽는다. 멈추거나 죽어도 api 는 영향이 없다 (논의사항 P5)."""

import asyncio
import io
import json
import sys
import time

import fitz
import pytest
from conftest import APPLICANT_PASSWORD, login, publishedPosting, signup
from PIL import Image

from app import main
from app.services import pdf_box
from app.services import resume_extract as rx

TEXT = "성명 홍길동 한국대학교 컴퓨터공학과 졸업 가나다전자 백엔드 개발자 2020년부터 2024년까지 근무 파이썬 자바 데이터베이스 설계 경험"


def pdfBytes(width=595, height=842, text=TEXT) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_text((40, 80), text, fontname="korea")
    return doc.tobytes()


def fakeBox(monkeypatch, tmp_path, source: str) -> None:
    script = tmp_path / "fake_box.py"
    script.write_text(source, encoding="utf-8")
    monkeypatch.setattr(rx, "BOX_COMMAND", [sys.executable, str(script)])


def test_apiProcessDoesNotLoadPdfLibraries():
    code = "import sys; import app.services.pdf_box; print('fitz' in sys.modules or 'pdfplumber' in sys.modules)"
    import subprocess
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_readsRealPdfInBox():
    pages = asyncio.run(rx.readPages(pdfBytes()))
    assert [p.source for p in pages] in (["pymupdf"], ["pdfplumber"]) and "홍길동" in pages[0].text  # 글꼴에 따라 두 번째 리더가 읽는다


def causeOf(data: bytes) -> str:
    with pytest.raises(rx.BoxError) as caught:
        asyncio.run(rx.readPages(data))
    return caught.value.code


def test_brokenPdfIsReportedAsBroken():
    assert causeOf(b"%PDF-1.7 not really a pdf") == "PDF_BROKEN"


def test_passwordPdfIsReportedAsEncrypted():
    doc = fitz.open(stream=pdfBytes(), filetype="pdf")
    assert causeOf(doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")) == "PDF_ENCRYPTED"


def test_permissionOnlyPasswordStillReads():
    doc = fitz.open(stream=pdfBytes(), filetype="pdf")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="", owner_pw="o")
    assert "홍길동" in asyncio.run(rx.readPages(data))[0].text


def test_truncatedPdfIsRepairedAndRead():
    data = pdfBytes()
    assert "홍길동" in asyncio.run(rx.readPages(data[:data.rindex(b"startxref")]))[0].text


def uploadUrl(client) -> str:
    postingId = publishedPosting(client)
    client.post("/auth/logout")
    signup(client)
    login(client, "kim@example.com", APPLICANT_PASSWORD)
    applicationId = client.post("/applications", json={"posting_id": postingId}).json()["application_id"]
    return f"/applications/{applicationId}/resume/upload"


def test_uploadTellsBrokenCause(adminClient):
    res = adminClient.post(uploadUrl(adminClient), files={"file": ("r.pdf", b"%PDF-1.7 broken", "application/pdf")})
    assert res.status_code == 400 and res.json()["code"] == "PDF_BROKEN"


def test_uploadTellsPasswordCause(adminClient):
    data = fitz.open(stream=pdfBytes(), filetype="pdf").tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    res = adminClient.post(uploadUrl(adminClient), files={"file": ("r.pdf", data, "application/pdf")})
    assert res.status_code == 400 and res.json()["code"] == "PDF_ENCRYPTED"


def throughGuard(monkeypatch, path, headers) -> tuple[int | None, bool]:
    """UploadSizeGuard 만 돌려 (응답 코드, 안쪽 앱이 불렸는지) 를 돌려준다."""
    monkeypatch.setattr(main, "uploadLimitBytes", lambda: 100)
    reached, sent = [], []

    async def inner(_scope, _receive, _send):
        reached.append(True)

    async def receive():
        raise AssertionError("본문을 읽으면 안 된다")

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": path, "headers": headers}
    asyncio.run(main.UploadSizeGuard(inner)(scope, receive, send))
    return (sent[0]["status"] if sent else None), bool(reached)


UPLOAD = "/applications/abc/resume/upload"


def test_oversizeIsRefusedBeforeReadingBody(monkeypatch):
    assert throughGuard(monkeypatch, UPLOAD, [(b"content-length", b"101")]) == (413, False)


def test_missingLengthIsRefused(monkeypatch):
    assert throughGuard(monkeypatch, UPLOAD, []) == (411, False)


def test_guardPassesAllowedSizeAndOtherPaths(monkeypatch):
    assert throughGuard(monkeypatch, UPLOAD, [(b"content-length", b"100")]) == (None, True)
    assert throughGuard(monkeypatch, "/auth/login", [(b"content-length", b"999")]) == (None, True)


def test_bigPhotoIsRefusedBeforeOcr(adminClient):
    data = b"\x89PNG\r\n\x1a\n" + b"x" * rx.OCR_MAX_IMAGE_BYTES
    res = adminClient.post(uploadUrl(adminClient), files={"file": ("r.png", data, "image/png")})
    assert res.status_code == 413 and res.json()["code"] == "FILE_TOO_LARGE"


def test_hangingBoxIsKilledOnTime(monkeypatch, tmp_path):
    fakeBox(monkeypatch, tmp_path, "import time\ntime.sleep(60)\n")
    monkeypatch.setattr(rx, "BOX_TIMEOUT_SEC", 1)
    started = time.monotonic()
    with pytest.raises(rx.BoxError, match="timeout"):
        asyncio.run(rx.readPages(b"%PDF-"))
    assert time.monotonic() - started < 10


def test_crashingBoxIsContained(monkeypatch, tmp_path):
    fakeBox(monkeypatch, tmp_path, "import os\nos._exit(139)\n")
    with pytest.raises(rx.BoxError, match="exit"):
        asyncio.run(rx.readPages(b"%PDF-"))


def test_secretsAreNotPassedToBox(monkeypatch, tmp_path):
    fakeBox(monkeypatch, tmp_path, "import json, os\nprint(json.dumps([{'no': 1, 'text': json.dumps(dict(os.environ)), 'source': 'none'}]))\n")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "secret-value")
    monkeypatch.setenv("DATABASE_URL", "secret-value")
    seen = json.loads(asyncio.run(rx.readPages(b"%PDF-"))[0].text)
    assert "secret-value" not in seen.values()


def test_onlyTwoBoxesRunAtOnce(monkeypatch, tmp_path):
    fakeBox(monkeypatch, tmp_path, "import time\ntime.sleep(0.6)\nprint('[]')\n")

    async def many():
        monkeypatch.setattr(rx, "BOX_SLOTS", asyncio.Semaphore(2))
        await asyncio.gather(*(rx.readPages(b"%PDF-") for _ in range(4)))

    started = time.monotonic()
    asyncio.run(many())
    assert time.monotonic() - started >= 1.2


def test_renderKeepsNormalPageResolution():
    png = asyncio.run(rx.renderPage(pdfBytes(), 1))
    assert max(Image.open(io.BytesIO(png)).size) == pytest.approx(842 * 200 / 72, abs=2)


def test_renderCapsInflatedPageSize():
    png = asyncio.run(rx.renderPage(pdfBytes(width=14400, height=14400), 1))
    assert max(Image.open(io.BytesIO(png)).size) <= pdf_box.RENDER_MAX_SIDE_PX


def test_pageTextIsCapped():
    doc = fitz.open()
    page = doc.new_page()
    for row in range(60):
        page.insert_text((10, 12 + row * 12), "가나다라마바사아자차" * 9, fontname="korea", fontsize=6)
    assert len(pdf_box.readPages(doc.tobytes())[0]["text"]) <= pdf_box.MAX_PAGE_CHARS


def test_garbledTextIsNotReadableButHyphensAre():
    body = TEXT * 2
    assert pdf_box.isReadable(body)  # 아래 시험이 글자 수 때문에 걸리지 않게 확인
    assert pdf_box.isReadable(body + "2020-03-01 ~ 2024-02-29")
    assert not pdf_box.isReadable(body + "\ue000" * 20)


def test_renderFailureBecomesOcrError(monkeypatch, tmp_path):
    fakeBox(monkeypatch, tmp_path, "raise SystemExit(1)\n")
    with pytest.raises(rx.OcrError):
        asyncio.run(rx.ocrPages(b"%PDF-", "application/pdf", [1]))
