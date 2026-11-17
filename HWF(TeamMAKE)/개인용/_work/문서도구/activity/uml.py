"""UML 활동 다이어그램(스윔레인) 그리기: 한 번 정의하면 SVG 와 Mermaid 소스를 같이 만든다."""
from html import escape

FONT = "Malgun Gothic, sans-serif"
CW = 280          # 칸 하나 너비
PAD = 10          # 레인 안쪽 여백
PITCH = 100       # 줄 간격
TOP = 96          # 첫 줄 위치
AW = 226          # 행동 상자 너비
DW, DH = 210, 88  # 판단 마름모
LANE_COLOR = {
    "applicant": "#4b5563", "admin": "#4b5563", "user": "#4b5563",
    "front": "#1d4ed8", "api": "#6d28d9", "worker": "#b45309",
    "ai": "#be185d", "sandbox": "#0f766e", "db": "#047857",
}


def t(x, y, s, size=12.5, w=400, color="#111827", anchor="middle"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" font-weight="{w}" fill="{color}" '
            f'text-anchor="{anchor}" dominant-baseline="middle">{escape(s)}</text>')


class Diagram:
    def __init__(self, title, lanes, subtitle=""):
        self.title, self.subtitle = title, subtitle
        self.lanes = lanes  # [(key, name, ncols)]
        self.lx = {}
        x = 0
        for key, _, n in lanes:
            self.lx[key] = (x, n * CW + 2 * PAD)
            x += n * CW + 2 * PAD
        self.width = x
        self.nodes, self.order, self.edges, self.notes = {}, [], [], []

    # ---------- 정의 ----------
    def colX(self, lane, col):
        x, _ = self.lx[lane]
        return x + PAD + CW * (col + 0.5)

    def rowY(self, row):
        return TOP + row * PITCH

    def add(self, nid, lane, row, kind, text="", col=0, label=None, w=None):
        lines = [s for s in text.split("\n")] if text else []
        n = dict(id=nid, lane=lane, row=row, kind=kind, lines=lines, col=col, label=label, w=w,
                 x=self.colX(lane, col), y=self.rowY(row))
        if kind == "bar":
            n["x"] = w[0]
            n["w"] = w[1]
        self.nodes[nid] = n
        self.order.append(nid)
        return nid

    def edge(self, a, b, guard=None, out="bottom", inp="top", mid=None, xm=None):
        self.edges.append(dict(a=a, b=b, guard=guard, out=out, inp=inp, mid=mid, xm=xm))

    def note(self, lane, row, text, col=0, attach=None):
        self.notes.append(dict(x=self.colX(lane, col), y=self.rowY(row), lines=text.split("\n"), attach=attach))

    # ---------- 크기와 연결점 ----------
    def half(self, n):
        k = n["kind"]
        if k == "start":
            return 11, 11
        if k in ("final", "flowfinal"):
            return 13, 13
        if k == "decision":
            return DW / 2, DH / 2
        if k == "merge":
            return 15, 15
        if k == "bar":
            return n["w"] / 2, 3.5
        if k == "time":
            return 11, 15
        h = max(48, 17 * len(n["lines"]) + 18)
        return AW / 2, h / 2

    def port(self, n, side, ref=None):
        hw, hh = self.half(n)
        x, y = n["x"], n["y"]
        if n["kind"] == "bar" and side in ("top", "bottom") and ref is not None:
            x = min(max(ref, x - hw + 6), x + hw - 6)
        return {"top": (x, y - hh), "bottom": (x, y + hh), "left": (x - hw, y), "right": (x + hw, y)}[side]

    # ---------- 그리기 ----------
    def drawNode(self, n):
        k, x, y = n["kind"], n["x"], n["y"]
        color = LANE_COLOR.get(n["lane"], "#374151")
        out = []
        if k == "start":
            out.append(f'<circle cx="{x}" cy="{y}" r="11" fill="#111827"/>')
        elif k == "final":
            out.append(f'<circle cx="{x}" cy="{y}" r="13" fill="#fff" stroke="#111827" stroke-width="2"/>'
                       f'<circle cx="{x}" cy="{y}" r="7.5" fill="#111827"/>')
        elif k == "flowfinal":
            d = 13 * 0.707
            out.append(f'<circle cx="{x}" cy="{y}" r="13" fill="#fff" stroke="#111827" stroke-width="2"/>'
                       f'<path d="M{x-d},{y-d} L{x+d},{y+d} M{x-d},{y+d} L{x+d},{y-d}" stroke="#111827" stroke-width="2"/>')
        elif k == "decision":
            hw, hh = DW / 2, DH / 2
            out.append(f'<polygon points="{x},{y-hh} {x+hw},{y} {x},{y+hh} {x-hw},{y}" fill="#fffbeb" stroke="#b45309" stroke-width="1.6"/>')
        elif k == "merge":
            out.append(f'<polygon points="{x},{y-15} {x+15},{y} {x},{y+15} {x-15},{y}" fill="#fffbeb" stroke="#b45309" stroke-width="1.6"/>')
        elif k == "bar":
            hw = n["w"] / 2
            out.append(f'<rect x="{x-hw}" y="{y-3.5}" width="{2*hw}" height="7" rx="2" fill="#111827"/>')
        elif k == "time":
            out.append(f'<path d="M{x-11},{y-15} h22 L{x-11},{y+15} h22 Z" fill="#fff" stroke="#111827" stroke-width="1.8"/>')
        else:
            hw, hh = self.half(n)
            out.append(f'<rect x="{x-hw}" y="{y-hh}" width="{2*hw}" height="{2*hh}" rx="16" fill="#fff" stroke="{color}" stroke-width="1.6"/>')
        if k in ("action", "decision"):
            lines = n["lines"]
            yy = y - (len(lines) - 1) * 8.5
            for i, s in enumerate(lines):
                size = 12.5 if k == "action" else 11.3
                out.append(t(x, yy, s, size, 700 if i == 0 and k == "action" else 400))
                yy += 17
        if k == "time":
            yy = y - (len(n["lines"]) - 1) * 8.5
            for s in n["lines"]:
                out.append(t(x + 20, yy, s, 12, 400, "#111827", "start"))
                yy += 17
        if n["label"]:
            out.append(t(x + 20, y, n["label"], 12, 700, "#111827", "start"))
        return "".join(out)

    def route(self, e):
        A, B = self.nodes[e["a"]], self.nodes[e["b"]]
        out, inp = e["out"], e["inp"]
        S = self.port(A, out, ref=B["x"])
        T = self.port(B, inp, ref=S[0])
        if out == "bottom" and inp == "top":
            if abs(S[0] - T[0]) < 1:
                return [S, T]
            my = S[1] + 16 if e["mid"] is None else e["mid"]
            return [S, (S[0], my), (T[0], my), T]
        if out in ("left", "right") and inp == "top":
            if abs(S[0] - T[0]) < 1:
                return [S, T]
            return [S, (T[0], S[1]), T]
        if out in ("bottom", "top") and inp in ("left", "right"):
            return [S, (S[0], T[1]), T]
        if out in ("left", "right") and inp in ("left", "right"):
            if abs(S[1] - T[1]) < 1:
                return [S, T]
            xm = e["xm"] if e["xm"] is not None else (S[0] + (28 if out == "right" else -28))
            return [S, (xm, S[1]), (xm, T[1]), T]
        return [S, T]

    def drawEdge(self, e):
        pts = self.route(e)
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        out = f'<path d="{d}" fill="none" stroke="#374151" stroke-width="1.5" marker-end="url(#arr)"/>'
        if e["guard"]:
            g = f"[{e['guard']}]"
            (sx, sy), (nx, ny) = pts[0], pts[1]
            if e["out"] == "bottom":
                goesRight = len(pts) > 2 and pts[2][0] > sx
                out += t(sx - 6 if goesRight else sx + 6, sy + 11, g, 11.5, 700, "#b45309", "end" if goesRight else "start")
            elif e["out"] == "right":
                dx = 30 if self.nodes[e["a"]]["kind"] == "decision" else -4
                out += t(sx - dx, sy - 21, g, 11.5, 700, "#b45309", "start")
            elif e["out"] == "left":
                dx = 30 if self.nodes[e["a"]]["kind"] == "decision" else -4
                out += t(sx + dx, sy - 21, g, 11.5, 700, "#b45309", "end")
            else:
                out += t(sx + 6, sy - 10, g, 11.5, 700, "#b45309", "start")
        return out

    def drawNote(self, nt):
        x, y, lines = nt["x"], nt["y"], nt["lines"]
        w, h = AW, 17 * len(lines) + 16
        out = ""
        if nt["attach"]:
            n = self.nodes[nt["attach"]]
            out += f'<path d="M{x},{y} L{n["x"]},{n["y"]}" stroke="#a16207" stroke-width="1.2" stroke-dasharray="4 3"/>'
        out += f'<path d="M{x-w/2},{y-h/2} h{w-12} l12,12 v{h-12} h{-w} z" fill="#fefce8" stroke="#a16207" stroke-width="1.2"/>'
        yy = y - (len(lines) - 1) * 8.5
        for s in lines:
            out += t(x, yy, s, 11.5, 400, "#713f12")
            yy += 17
        return out

    def svg(self, footer=()):
        bottom = max(n["y"] + self.half(n)[1] for n in self.nodes.values())
        bottom = max([bottom] + [nt["y"] + 17 * len(nt["lines"]) / 2 + 8 for nt in self.notes]) + 40
        h = bottom + (16 + 20 * len(footer) if footer else 0)
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{h}" viewBox="0 0 {self.width} {h}">',
               '<defs><marker id="arr" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto">'
               '<path d="M0,0 L10,5 L0,10 z" fill="#374151"/></marker></defs>',
               f'<rect width="{self.width}" height="{h}" fill="#fff"/>',
               t(14, 20, self.title, 17, 700, "#111827", "start")]
        if self.subtitle:
            out.append(t(14, 42, self.subtitle, 12, 400, "#4b5563", "start"))
        laneTop = 56
        for i, (key, name, _) in enumerate(self.lanes):
            x, w = self.lx[key]
            out.append(f'<rect x="{x}" y="{laneTop}" width="{w}" height="{bottom-laneTop}" fill="{"#f8fafc" if i % 2 == 0 else "#ffffff"}" stroke="#cbd5e1"/>')
            out.append(f'<rect x="{x}" y="{laneTop}" width="{w}" height="30" fill="#e2e8f0" stroke="#cbd5e1"/>')
            out.append(t(x + w / 2, laneTop + 15, name, 13, 700, LANE_COLOR.get(key, "#111827")))
        for e in self.edges:
            out.append(self.drawEdge(e))
        for nid in self.order:
            out.append(self.drawNode(self.nodes[nid]))
        for nt in self.notes:
            out.append(self.drawNote(nt))
        yy = bottom + 18
        for s in footer:
            out.append(t(14, yy, s, 12, 400, "#374151", "start"))
            yy += 20
        out.append("</svg>")
        return "".join(out)

    # ---------- Mermaid ----------
    def mermaid(self):
        def q(s):
            return s.replace('"', "#quot;")

        def body(n):
            text = "<br/>".join(q(s) for s in n["lines"])
            k = n["kind"]
            if k == "start":
                return '(["시작"])'
            if k == "final":
                return f'(["종료{": " + q(n["label"]) if n["label"] else ""}"])'
            if k == "flowfinal":
                return f'(["흐름 끝{": " + q(n["label"]) if n["label"] else ""}"])'
            if k == "decision":
                return f'{{"{text}"}}'
            if k == "merge":
                return '{" "}'
            if k == "bar":
                return '[["병렬 분기"]]'
            if k == "time":
                return f'>"⏱ {text}"]'
            return f'("{text}")'

        lines = ["flowchart TB"]
        for key, name, _ in self.lanes:
            members = [self.nodes[i] for i in self.order if self.nodes[i]["lane"] == key]
            if not members:
                continue
            lines.append(f'    subgraph {key}["{q(name)}"]')
            for n in sorted(members, key=lambda n: (n["row"], n["col"])):
                lines.append(f'        {n["id"]}{body(n)}')
            lines.append("    end")
        for e in self.edges:
            arrow = f'-->|"[{q(e["guard"])}]"|' if e["guard"] else "-->"
            lines.append(f'    {e["a"]} {arrow} {e["b"]}')
        for i, nt in enumerate(self.notes):
            nid = f"note{i}"
            lines.append(f'    {nid}[/"{"<br/>".join(q(s) for s in nt["lines"])}"/]')
            if nt["attach"]:
                lines.append(f'    {nid} -.- {nt["attach"]}')
        return "\n".join(lines)
