"""PDF 를 읽는 별도 프로세스. 믿을 수 없는 파일이라 api 프로세스 안에서 열지 않는다 (논의사항 P5).

사용: python pdf_box.py read      표준입력 PDF → 표준출력 JSON [{no, text, source, images}]
      python pdf_box.py render N  표준입력 PDF → 표준출력 N쪽 PNG

이 파일은 단독으로 실행되므로 앱 모듈을 가져오지 않는다. fitz·pdfplumber 는 함수 안에서 가져와 api 프로세스에 올리지 않는다.
"""

import io
import json
import re
import sys

SCANNED_PAGE_CHARS = 50
# 쪽 넓이의 이만큼 이상을 차지하는 그림만 센다 (작은 아이콘·로고는 OCR 하지 않음). images 는 그림 속 글자를 OCR 할 쪽을 고르는 데 쓴다
IMAGE_MIN_AREA_RATIO = 0.03
MAX_PAGES = 10
MAX_PAGE_CHARS = 6000  # 글자가 비정상으로 많은 PDF 가 api 메모리로 넘어오지 않게 한다
RENDER_DPI = 200
RENDER_MAX_SIDE_PX = 4000  # 쪽 크기를 부풀린 PDF 대비. 보통 문서(A4 200dpi 약 2339)에는 영향이 없다
MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
CPU_LIMIT_SEC = 60
EXIT_ENCRYPTED = 3
EXIT_BROKEN = 4
EXIT_TOO_COMPLEX = 5

MEANINGFUL = re.compile(r"[가-힣A-Za-z0-9]")
# 글꼴 정보가 깨진 PDF 에서 나오는 흔적: (cid:123), 대체 문자, 사용자 영역 문자
GARBAGE = re.compile(r"\(cid:\d+\)|�|[-]")
LATIN1_JUNK = re.compile(r"[À-ÿ]")


def isReadable(text: str) -> bool:
    """쪽 글자를 믿을 수 있는지: 의미 있는 글자가 충분하고, 깨진 글자 흔적이 적어야 한다."""
    meaningful = len(MEANINGFUL.findall(text))
    if meaningful < SCANNED_PAGE_CHARS:
        return False
    junk = len(GARBAGE.findall(text)) + len(LATIN1_JUNK.findall(text))
    return junk / meaningful < 0.05


class Encrypted(Exception):
    pass


def imageCount(page) -> int:
    """쪽 위에 그려진 그림 가운데 넓이가 쪽의 IMAGE_MIN_AREA_RATIO 이상인 것의 수."""
    pageArea = abs(page.rect.width * page.rect.height) or 1
    try:
        boxes = [info["bbox"] for info in page.get_image_info()]
    except Exception:  # 그림 정보를 못 읽어도 글자 읽기는 계속한다
        return 0
    return sum(1 for x0, y0, x1, y1 in boxes if abs((x1 - x0) * (y1 - y0)) / pageArea >= IMAGE_MIN_AREA_RATIO)


def readPages(data: bytes) -> list[dict]:
    import fitz  # PyMuPDF
    import pdfplumber

    pages: list[dict] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise Encrypted
        plumber = None
        try:
            for index, page in enumerate(doc):
                if index >= MAX_PAGES:
                    break
                text = page.get_text("text", sort=True).strip()[:MAX_PAGE_CHARS]
                images = imageCount(page)
                if isReadable(text):
                    pages.append({"no": index + 1, "text": text, "source": "pymupdf", "images": images})
                    continue
                # 두 번째 리더: 표·특수 글꼴은 pdfplumber 가 더 잘 읽을 때가 있다
                if plumber is None:
                    plumber = pdfplumber.open(io.BytesIO(data))
                second = (plumber.pages[index].extract_text() or "").strip()[:MAX_PAGE_CHARS]
                if isReadable(second):
                    pages.append({"no": index + 1, "text": second, "source": "pdfplumber", "images": images})
                else:
                    pages.append({"no": index + 1, "text": "", "source": "none", "images": images})
        finally:
            if plumber is not None:
                plumber.close()
    return pages


def renderPage(data: bytes, pageNo: int) -> bytes:
    import fitz  # PyMuPDF

    with fitz.open(stream=data, filetype="pdf") as doc:
        page = doc[pageNo - 1]
        zoom = min(RENDER_DPI / 72, RENDER_MAX_SIDE_PX / max(page.rect.width, page.rect.height))
        return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")


def limitResources() -> None:
    try:
        import resource
    except ImportError:  # Windows 개발 환경. 시간 제한은 부르는 쪽에서 건다
        return
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SEC, CPU_LIMIT_SEC))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main(args: list[str]) -> None:
    limitResources()
    data = sys.stdin.buffer.read()
    try:
        if args[0] == "read":
            out = json.dumps(readPages(data), ensure_ascii=False).encode()
        else:
            out = renderPage(data, int(args[1]))
    except Encrypted:
        sys.exit(EXIT_ENCRYPTED)
    except MemoryError:
        sys.exit(EXIT_TOO_COMPLEX)
    except Exception:  # noqa: BLE001 — 파일 내용을 로그로 흘리지 않고 원인 종류만 알린다
        sys.exit(EXIT_BROKEN)
    sys.stdout.buffer.write(out)


if __name__ == "__main__":
    main(sys.argv[1:])
