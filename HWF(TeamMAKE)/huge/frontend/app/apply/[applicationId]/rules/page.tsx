"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApplyFlow, BottomBar, useApplication } from "@/components/ApplyFlow";
import { useApp } from "@/components/Providers";
import { Button, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { examSessionKey, type ExamSession } from "@/lib/exam";
import { longDateTime } from "@/lib/format";

const RETRY_LOCK_SEC = 10;

function Rules() {
    const { app } = useApplication();
    const router = useRouter();
    const { toast } = useApp();
    const [agreed, setAgreed] = useState(false);
    const [busy, setBusy] = useState(false);
    const [full, setFull] = useState(false);
    const [lockLeft, setLockLeft] = useState(0);
    const [fullscreenRefused, setFullscreenRefused] = useState(false);
    // 남은 시간은 화면을 연 순간의 서버 시각 기준 (안내용)
    const [serverNow] = useState(() => new Date(app.server_time).getTime());

    useEffect(() => {
        if (lockLeft <= 0) return;
        const timer = window.setTimeout(() => setLockLeft((v) => v - 1), 1000);
        return () => window.clearTimeout(timer);
    }, [lockLeft]);

    const expectedMin = app.posting.has_coding_test ? 90 : 30;
    const leftMin = Math.floor((new Date(app.posting.close_at).getTime() - serverNow) / 60_000);

    async function start() {
        setBusy(true);
        setFullscreenRefused(false);
        // 전체 화면 요청은 클릭(사용자 동작) 안에서 먼저 한다. 시작이 막히면 다시 푼다
        try {
            await document.documentElement.requestFullscreen({ navigationUI: "hide" });
        } catch {
            setFullscreenRefused(true);
            setBusy(false);
            return;
        }
        try {
            const res = await api<ExamSession>(`/applications/${app.application_id}/interview/start`, { method: "POST" });
            sessionStorage.setItem(examSessionKey(app.application_id), JSON.stringify(res));
            router.replace(`/exam/${app.application_id}`);
        } catch (err) {
            await document.exitFullscreen().catch(() => undefined);
            const e = err as ApiError;
            if (e.code === "CAPACITY_FULL") {
                setFull(true);
                setLockLeft(RETRY_LOCK_SEC);
            } else if (e.code === "PRECHECK_REQUIRED") {
                toast("warn", e.message);
                router.replace(`/apply/${app.application_id}/precheck`);
            } else {
                toast("error", e.message);
            }
            setBusy(false);
        }
    }

    return (
        <div className="stack">
            <h2>면접을 시작하기 전에 꼭 읽어 주세요.</h2>
            <div className="grid3">
                <div className="card"><h3>진행 방식</h3><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                    <li>AI가 음성+자막으로 질문</li><li>3-2-1 뒤 답변 녹음</li><li>카메라 영상과 마이크 소리 녹화 (녹화는 평가에 쓰지 않음)</li></ul></div>
                <div className="card"><h3>질문과 시간</h3><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                    <li>기본 질문 10개 · 각 90초</li><li>꼬리질문 최대 4개 · 각 60초</li><li>AI 면접 예상 약 25분</li></ul></div>
                <div className="card"><h3>코딩테스트</h3><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                    {app.posting.has_coding_test ? <><li>포함 · 2문항 · 60분</li><li>Python 3</li><li>AI 면접 직후 바로 시작</li></> : <li>이 공고는 코딩테스트가 없습니다</li>}</ul></div>
            </div>
            <div className="notice notice-warn">
                <strong>⚠ 응시 규칙</strong>
                <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
                    <li>한 번만 응시할 수 있고, 중단·일시정지 버튼이 없습니다.</li>
                    <li>다른 탭·창으로 이동, 전체 화면 해제(ESC 포함)는 화면 이탈입니다. 1회: 경고 후 멈춘 시점의 남은 시간부터 이어서 · 2회: 면접 자동 취소(1차 불합격)</li>
                    <li>새로고침하거나 창을 닫으면 응시가 종료되고 다시 응시할 수 없습니다.</li>
                    <li>인터넷·장비 문제로 끊기면 답변은 저장되고, 마이페이지에서 이어갈 수 있습니다.</li>
                    <li>다른 프로그램 알림(메신저 등)은 미리 꺼 주세요.</li>
                    <li>접수 마감 시각({longDateTime(app.posting.close_at)})이 되면 진행 중이어도 면접이 중단됩니다.</li>
                </ul>
            </div>
            {leftMin < expectedMin && (
                <p style={{ color: "var(--color-warning-text)", fontWeight: 600 }}>
                    ⚠ 마감까지 {Math.floor(leftMin / 60)}시간 {leftMin % 60}분 남았습니다. 예상 소요 약 {expectedMin >= 60 ? "1시간 30분" : "30분"}보다 짧습니다.
                </p>
            )}
            <p>결과는 {longDateTime(app.posting.release_at)}에 공개됩니다.</p>
            <label className="check"><input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />위 응시 규칙을 모두 확인했습니다.</label>
            {fullscreenRefused && <div className="notice notice-error" role="alert">전체 화면으로 전환해야 시작할 수 있습니다.</div>}
            <BottomBar>
                <button type="button" className="btn btn-secondary" onClick={() => router.push(`/apply/${app.application_id}/precheck`)}>이전</button>
                <span style={{ flex: 1 }} />
                <Button size="lg" busy={busy} disabled={!agreed} reason="응시 규칙 확인에 체크해 주세요" onClick={start}>면접 시작 (전체 화면으로 전환) ▶</Button>
            </BottomBar>
            {full && (
                <Modal title="지금은 면접을 시작할 수 없습니다" escClose={false} actions={(
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => router.push("/mypage")}>마이페이지로</button>
                        <Button disabled={lockLeft > 0} onClick={() => { setFull(false); void start(); }}>{lockLeft > 0 ? `다시 시도 (${lockLeft})` : "다시 시도"}</Button>
                    </>
                )}>
                    <p>지금 동시에 면접을 보는 지원자가 많습니다. 잠시 후 다시 시도해 주세요.</p>
                    <p className="small muted">응시 횟수는 쓰이지 않았고 상태는 &apos;면접 준비 중&apos; 그대로입니다. 접수 마감({longDateTime(app.posting.close_at)}) 전까지 언제든 다시 시도할 수 있습니다.</p>
                </Modal>
            )}
        </div>
    );
}

export default function RulesPage() {
    return <ApplyFlow step="rules"><Rules /></ApplyFlow>;
}
