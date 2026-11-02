"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { PostingBody, type PostingDetail } from "@/components/PostingBody";
import { useApp } from "@/components/Providers";
import { SiteShell } from "@/components/Shell";
import { Button, ErrorBox, Loading, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { shortDateTime, untilText } from "@/lib/format";
import { POSTING_BUTTON } from "@/lib/status";

type Detail = PostingDetail & { server_time: string; my_application: { application_id: string; attempt_status: keyof typeof POSTING_BUTTON } | null };

function JobDetail() {
    const { postingId } = useParams<{ postingId: string }>();
    const params = useSearchParams();
    const router = useRouter();
    const { me, meLoaded } = useApp();
    const [data, setData] = useState<Detail | null>(null);
    const [error, setError] = useState<{ status: number; message: string } | null>(null);
    const [busy, setBusy] = useState(false);
    const [modal, setModal] = useState<{ title: string; text: string; toMypage?: boolean } | null>(null);
    const autoApplied = useRef(false);

    const load = useCallback(async () => {
        try {
            setData(await api<Detail>(`/postings/${postingId}`));
            setError(null);
        } catch (err) {
            const e = err as ApiError;
            setError({ status: e.status, message: e.message });
        }
    }, [postingId]);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void load();
    }, [load, me]);

    const apply = useCallback(async () => {
        if (!me) {
            router.push(`/login?next=${encodeURIComponent(`/jobs/${postingId}?apply=1`)}`);
            return;
        }
        setBusy(true);
        try {
            const res = await api<{ application_id: string; next_step: string }>("/applications", { body: { posting_id: postingId } });
            router.push(`/apply/${res.application_id}/${res.next_step === "consent" ? "consent" : "resume"}`);
        } catch (err) {
            const e = err as ApiError;
            if (e.code === "ALREADY_APPLIED") setModal({ title: "이미 지원한 공고입니다", text: "진행 상황은 마이페이지에서 확인할 수 있습니다.", toMypage: true });
            else if (e.code === "POSTING_CLOSED") setModal({ title: "접수가 마감된 공고입니다", text: "이 공고는 지금 지원할 수 없습니다." });
            else setModal({ title: "지원할 수 없습니다", text: e.message });
            void load();
        } finally {
            setBusy(false);
        }
    }, [me, postingId, router, load]);

    // 로그인하고 돌아오면 지원 검증을 자동으로 한 번 실행 (T-03)
    useEffect(() => {
        if (params.get("apply") === "1" && meLoaded && me?.role === "applicant" && data && !data.my_application && !autoApplied.current) {
            autoApplied.current = true;
            void apply();
        }
    }, [params, meLoaded, me, data, apply]);

    if (error?.status === 404) {
        return (
            <div className="narrow center stack">
                <h2>찾을 수 없는 공고입니다</h2>
                <Link className="btn btn-primary" href="/jobs">공고 목록으로</Link>
            </div>
        );
    }
    if (error) return <div className="container"><ErrorBox message={error.message} onRetry={load} /></div>;
    if (!data) return <Loading />;

    const serverNow = new Date(data.server_time).getTime();
    const notOpen = new Date(data.open_at).getTime() > serverNow;
    const closed = data.status === "closed" || new Date(data.close_at).getTime() <= serverNow;
    const mine = data.my_application;
    let action: React.ReactNode;
    if (me?.role === "admin") {
        action = <Button disabled reason="관리자 계정은 지원할 수 없습니다">지원하기</Button>;
    } else if (mine) {
        const rule = POSTING_BUTTON[mine.attempt_status];
        const target = mine.attempt_status === "drafting" ? `/apply/${mine.application_id}/consent` : "/mypage";
        action = (
            <div className="stack">
                {rule.active ? (
                    <Link className={`btn ${mine.attempt_status === "drafting" ? "btn-primary" : "btn-secondary"}`} style={{ width: "100%" }} href={target}>{rule.label}</Link>
                ) : <button type="button" className="btn" disabled style={{ width: "100%" }}>{rule.label}</button>}
                <span className="disabled-reason">{rule.hint}</span>
            </div>
        );
    } else if (notOpen) {
        action = <button type="button" className="btn" disabled style={{ width: "100%" }}>{shortDateTime(data.open_at).slice(0, 5)} 접수 시작</button>;
    } else if (closed) {
        action = <button type="button" className="btn" disabled style={{ width: "100%" }}>접수 마감</button>;
    } else {
        action = (
            <div className="stack">
                <Button busy={busy} onClick={apply} size="lg" style={{ width: "100%" }}>지원하기</Button>
                <span className="small center" style={{ display: "block" }}>마감까지 {untilText(serverNow, data.close_at)}</span>
            </div>
        );
    }

    return (
        <div className="container">
            <Link href="/jobs" className="small">← 공고 목록</Link>
            <PostingBody posting={data} action={action} />
            {modal && (
                <Modal title={modal.title} onClose={() => setModal(null)} actions={modal.toMypage ? (
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>닫기</button>
                        <Link className="btn btn-primary" href="/mypage">마이페이지로</Link>
                    </>
                ) : <button type="button" className="btn btn-primary" onClick={() => setModal(null)}>확인</button>}>
                    <p>{modal.text}</p>
                </Modal>
            )}
        </div>
    );
}

export default function JobDetailPage() {
    return <SiteShell><Suspense><JobDetail /></Suspense></SiteShell>;
}
