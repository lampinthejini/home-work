"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useFocusTrap } from "@/components/Ui";

import { longDateTime } from "@/lib/format";

export type Overlay =
    | { kind: "paused"; reason: string; resumeUntil: string | null; resumesLeft?: number | null }
    | { kind: "warn"; label: string; phase: "interview" | "coding" }
    | { kind: "cancelled" }
    | { kind: "closed" }
    | { kind: "withdrawn" }
    | { kind: "ended"; detail: string | null }
    | { kind: "checking"; long?: boolean };

function Shell({ icon, title, children, labelId }: { icon: string; title: string; children: React.ReactNode; labelId: string }) {
    // 응시 중 오버레이는 ESC 로 닫히지 않는다 (§8). 뒤 화면은 포커스·클릭을 받지 않게 한다
    const outer = useRef<HTMLDivElement>(null);
    const box = useRef<HTMLDivElement>(null);
    useFocusTrap(box);
    useEffect(() => {
        const siblings = Array.from(outer.current?.parentElement?.children ?? []).filter((el) => el !== outer.current) as HTMLElement[];
        siblings.forEach((el) => { el.inert = true; });
        return () => siblings.forEach((el) => { el.inert = false; });
    }, []);
    return (
        <div className="overlay" style={{ zIndex: 95 }} ref={outer}>
            <div className="modal center" ref={box} role="alertdialog" aria-modal="true" aria-labelledby={labelId} style={{ maxWidth: 640 }}>
                <div style={{ fontSize: 44 }} aria-hidden>{icon}</div>
                <h2 id={labelId}>{title}</h2>
                <div style={{ textAlign: "left" }}>{children}</div>
            </div>
        </div>
    );
}

function useOnline() {
    const [online, setOnline] = useState(true);
    useEffect(() => {
        const update = () => setOnline(navigator.onLine);
        update();
        window.addEventListener("online", update);
        window.addEventListener("offline", update);
        return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
    }, []);
    return online;
}

function ToMypage() {
    return <div className="center" style={{ marginTop: 20 }}><Link className="btn btn-primary btn-lg" href="/mypage">마이페이지로</Link></div>;
}

const PAUSED_TITLE: Record<string, string> = {
    server_error: "일시적인 서버 오류로 면접이 멈췄습니다.",
    device_error: "카메라나 마이크에 문제가 생겨 면접이 멈췄습니다.",
};

export function ExamOverlay({ overlay, closeAt, releaseAt, onWarnAck }: { overlay: Overlay; closeAt: string | null; releaseAt: string | null; onWarnAck: () => void }) {
    const online = useOnline();
    switch (overlay.kind) {
        case "checking":
            return (
                <Shell icon="⏳" title="연결 상태를 확인하고 있습니다" labelId="ov-checking">
                    <p className="center muted">{overlay.long
                        ? "면접 서버와 연결되지 않았습니다. 서버가 응시 상태를 정하는 데 2~3분 걸릴 수 있습니다. 이 화면을 닫지 말고 기다려 주세요."
                        : "잠시만 기다려 주세요. 최대 20초 정도 걸립니다."}</p>
                </Shell>
            );
        case "paused":
            return (
                <Shell icon="⚠" title={PAUSED_TITLE[overlay.reason] ?? "연결이 끊겼습니다."} labelId="ov-01">
                    <p className="center">답변은 안전하게 저장되었습니다.<br />다시 접속하면 끊긴 질문부터 이어서 진행합니다.</p>
                    <ul>
                        <li>끊긴 질문은 처음부터 새 답변 시간으로 다시 진행합니다. 감점은 없습니다.</li>
                        <li>접수 마감 {longDateTime(overlay.resumeUntil ?? closeAt)}까지 이어갈 수 있습니다.</li>
                        {overlay.resumesLeft != null && <li>{overlay.resumesLeft > 0
                            ? `이번에 이어간 뒤에도 연결 끊김이 ${overlay.resumesLeft}번 더 생기면 다시 이어갈 수 있습니다.`
                            : "이번이 마지막 이어가기입니다. 이어간 뒤 다시 끊기면 응시가 끝나고 답변한 문항까지 평가합니다."}</li>}
                        <li>연결 상태: <span className={online ? "conn conn-ok" : "conn conn-down"}>{online ? "다시 연결됨" : "연결 안 됨"}</span></li>
                    </ul>
                    <div className="center" style={{ marginTop: 20 }}>
                        {online ? <Link className="btn btn-primary btn-lg" href="/mypage">마이페이지에서 이어가기</Link>
                            : <><button type="button" className="btn btn-lg" disabled>마이페이지에서 이어가기</button><p className="disabled-reason">연결이 돌아오면 버튼이 활성화됩니다</p></>}
                    </div>
                </Shell>
            );
        case "warn":
            return (
                <Shell icon="⚠" title="화면 이탈이 감지되었습니다 (1 / 2)" labelId="ov-02">
                    <p>감지된 동작: <strong>{overlay.label}</strong></p>
                    <p><strong>한 번 더 이탈하면 면접이 취소됩니다.</strong><br />확인을 누르면 전체 화면으로 돌아가</p>
                    <ul>
                        <li>AI 면접: 같은 질문을 멈춘 시점의 남은 시간부터 이어서 답합니다. (이탈 전에 한 답변은 그대로 이어 붙습니다)</li>
                        <li>코딩테스트: <strong>시간은 멈추지 않습니다.</strong> 화면을 벗어나 있던 시간도 코딩 시간에서 빠집니다.</li>
                    </ul>
                    <p style={{ color: "var(--color-danger)", fontWeight: 600 }}>⚠ 이 창이 떠 있는 동안 다른 탭·창으로 이동해도 2회째 이탈입니다.</p>
                    <div className="center" style={{ marginTop: 20 }}><button type="button" className="btn btn-primary btn-lg" onClick={onWarnAck}>확인하고 돌아가기</button></div>
                </Shell>
            );
        case "cancelled":
            return (
                <Shell icon="✕" title="응시가 취소되었습니다." labelId="ov-03">
                    <p className="center">화면 이탈이 2회 감지되어 응시 규칙에 따라 면접이 자동으로 취소되었습니다.<br />이 지원은 1차 불합격으로 처리되며, 다시 응시할 수 없습니다.</p>
                    <ToMypage />
                </Shell>
            );
        case "closed":
            return (
                <Shell icon="⏰" title="마감이 되어 면접을 진행할 수 없습니다." labelId="ov-06">
                    <p className="center">접수 마감 시각({longDateTime(closeAt)})이 되어 면접이 종료되었습니다.</p>
                    <ul>
                        <li>답변한 문항까지 평가합니다. 남은 질문은 0점으로 처리됩니다.</li>
                        <li>코딩테스트는 마지막으로 저장된 코드로 채점합니다.</li>
                        <li>결과는 {longDateTime(releaseAt)}에 공개됩니다.</li>
                    </ul>
                    <ToMypage />
                </Shell>
            );
        case "withdrawn":
            return (
                <Shell icon="✕" title="동의 철회로 응시가 취소되었습니다." labelId="ov-withdrawn">
                    <p className="center">이 지원의 동의를 철회해 면접을 멈추고 응시 데이터를 삭제했습니다.</p>
                    <ToMypage />
                </Shell>
            );
        case "ended":
            return (
                <Shell icon="⏹" title="응시가 종료되었습니다." labelId="ov-07">
                    <p className="center">
                        {overlay.detail === "permission_revoked" ? "마이크·카메라 권한이 꺼져 응시 규칙에 따라 면접이 종료되었습니다."
                            : overlay.detail === "resume_limit" ? "연결 끊김으로 이어가기를 여러 번 해 응시 규칙에 따라 면접이 종료되었습니다."
                                : "창 닫기·새로고침으로 응시 규칙에 따라 면접이 종료되었습니다."}
                    </p>
                    <ul>
                        <li>답변한 문항까지 평가합니다. 남은 질문은 0점으로 처리됩니다.</li>
                        <li>다시 응시할 수 없습니다.</li>
                        <li>결과는 {longDateTime(releaseAt)}에 공개됩니다.</li>
                    </ul>
                    <ToMypage />
                </Shell>
            );
    }
}
