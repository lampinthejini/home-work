"""발표 11~14쪽 화면 묶음 v2: 글자가 보이게 필요한 곳만 잘라 붙이고, 이야기 순서를 ①②③ 로 붙인다."""
import sys, os, cv2
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SP, OUT = sys.argv[1], sys.argv[2]
V2 = os.path.join(SP, "shots", "v2")
VID = r"C:\big21\hw-repo\HWF(TeamMAKE)\2026-11-17 12-17-48.mp4"
S = 3
W, H = 860 * S, 290 * S
GAP = 10 * S
PAD = 6 * S
FONT = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", 8 * S)
NUMF = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", 8 * S)


def frame(t, box):
    cap = cv2.VideoCapture(VID); cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, im = cap.read()
    x0, y0, x1, y1 = box
    return Image.fromarray(cv2.cvtColor(im[y0:y1, x0:x1], cv2.COLOR_BGR2RGB))


def src(name, pw=900):
    """미리보기(폭 pw) 좌표로 자를 수 있게 (그림, 배율) 을 돌려준다."""
    im = Image.open(os.path.join(V2, name)).convert("RGB")
    return im, im.size[0] / pw


def cut(name, box, pw=900):
    im, f = src(name, pw)
    return im.crop(tuple(int(v * f) for v in box))


def hcat(*ims, gap=24, bg=(244, 246, 250)):
    h = max(i.size[1] for i in ims)
    w = sum(i.size[0] for i in ims) + gap * (len(ims) - 1)
    c = Image.new("RGB", (w, h), bg); x = 0
    for i in ims:
        c.paste(i, (x, 0)); x += i.size[0] + gap
    return c


def vcat(*ims, bg=(255, 255, 255)):
    w = max(i.size[0] for i in ims)
    h = sum(i.size[1] for i in ims)
    c = Image.new("RGB", (w, h), bg); y = 0
    for i in ims:
        c.paste(i, (0, y)); y += i.size[1]
    return c


def fit(im, w, h):
    """잘라내지 않고 통째로 넣는다(남는 곳은 화면 바탕색)."""
    iw, ih = im.size; k = min(w / iw, h / ih)
    nw, nh = int(iw * k), int(ih * k)
    bg = im.getpixel((2, 2))
    c = Image.new("RGB", (w, h), bg)
    c.paste(im.resize((nw, nh), Image.LANCZOS), ((w - nw) // 2, (h - nh) // 2))
    return c


def tile(canvas, im, x, y, w, h, num, label):
    x, y, w, h = x * S + PAD, y * S + PAD, w * S, h * S
    rad = 10 * S
    sh = Image.new("L", canvas.size, 0); ImageDraw.Draw(sh).rounded_rectangle((x, y + 2 * S, x + w, y + h + 2 * S), rad, fill=60)
    sh = sh.filter(ImageFilter.GaussianBlur(4 * S))
    canvas.paste(Image.new("RGBA", canvas.size, (15, 23, 42, 255)), (0, 0), sh)
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), rad, fill=255)
    band = 22 * S
    body = Image.new("RGB", (w, h), (255, 255, 255))
    body.paste(fit(im, w - 8 * S, h - band - 6 * S), (4 * S, 4 * S))
    ImageDraw.Draw(body).line((0, h - band, w, h - band), fill=(226, 232, 240), width=S)
    canvas.paste(body.convert("RGBA"), (x, y), m)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x, y, x + w - 1, y + h - 1), rad, outline=(203, 213, 225, 255), width=S)
    # 아래 왼쪽: 파란 번호 + 이름표
    tw = d.textlength(label, font=FONT)
    ph = 16 * S; px, py = x + 6 * S, y + h - 3 * S - ph
    d.rounded_rectangle((px, py, px + ph + tw + 12 * S, py + ph), 8 * S, fill=(15, 23, 42, 230))
    d.ellipse((px + 2 * S, py + 2 * S, px + ph - 2 * S, py + ph - 2 * S), fill=(37, 99, 235, 255))
    d.text((px + ph / 2, py + ph / 2), str(num), font=NUMF, fill="white", anchor="mm")
    d.text((px + ph + 4 * S, py + ph / 2), label, font=FONT, fill="white", anchor="lm")


def build(key, tiles):
    c = Image.new("RGBA", (W + 2 * PAD, H + 2 * PAD), (0, 0, 0, 0))
    for t in tiles:
        tile(c, *t)
    c.save(os.path.join(OUT, f"slide{key}_screens.png")); print(key, c.size)


# 11: ① 공고 상세(왼쪽 위) ② 질문 준비(왼쪽 아래) ③ 면접 화면(오른쪽 크게)
LW = 360; RH = (290 - 10) // 2
build("11", [
    (cut("11_job_detail.png", (70, 118, 830, 470)), 0, 0, LW, RH, 1, "공고 상세 · 지원"),
    (frame(305, (420, 323, 1500, 755)), 0, RH + 10, LW, 290 - RH - 10, 2, "면접 질문 준비"),
    (frame(1290, (480, 290, 1440, 900)), LW + 10, 0, 860 - LW - 10, 290, 3, "AI 면접 화면 · 질문 음성과 실시간 자막"),
])

# 12: ① 공고 목록(오른쪽 위) ② AI 공고 만들기(왼쪽) ③ 평가 기준(오른쪽 아래)
LW = 330; RX = LW + 10; RW = 860 - RX
build("12", [
    (cut("12_postings.png", (185, 112, 878, 290)), RX, 0, RW, 130, 1, "공고 목록 · 상태"),
    (cut("12_posting_ai.png", (185, 65, 805, 600)), 0, 0, LW, 290, 2, "AI로 공고 만들기"),
    (cut("12_posting_criteria.png", (195, 222, 640, 462)), RX, 140, RW, 150, 3, "평가 기준 · 가중치"),
])

# 13: ① 지원자 목록(왼쪽 위) ② 대시보드(왼쪽 아래) ③ 운영 설정(오른쪽)
LW = 440; RX = LW + 10; RW = 860 - RX
build("13", [
    (cut("13_applicants_done.png", (185, 62, 878, 298)), 0, 0, LW, 135, 1, "지원자 목록 · 점수 · 합격 여부"),
    (cut("13_dashboard.png", (85, 20, 425, 168), pw=433), 0, 145, LW, 145, 2, "대시보드 · 통계"),
    (cut("13_settings.png", (185, 65, 692, 437)), RX, 0, RW, 290, 3, "운영 설정 · 동시 면접 상한"),
])

# 14: ① 서류 평가(왼쪽) ② 리포트(오른쪽 위) ③ 면접 평가 · 질문별 근거(오른쪽 아래)
LW = 290; RX = LW + 10; RW = 860 - RX
doc = hcat(cut("14_report.png", (178, 195, 300, 550)), cut("14_report.png", (430, 195, 668, 550)), gap=0, bg=(255, 255, 255))
rep = hcat(cut("14_report.png", (170, 1760, 400, 1925)), cut("14_report.png", (163, 2035, 463, 2240)), cut("14_report.png", (473, 2035, 772, 2240)))
ans = vcat(cut("14_answers.png", (185, 1995, 880, 2035)), cut("14_answers.png", (185, 2185, 880, 2330)))
build("14", [
    (doc, 0, 0, LW, 290, 1, "서류 평가 · 항목별 근거"),
    (rep, RX, 0, RW, 140, 2, "리포트 · 항목 점수 · 강점 · 개선점"),
    (ans, RX, 150, RW, 140, 3, "면접 평가 · 질문별 근거 문장"),
])
