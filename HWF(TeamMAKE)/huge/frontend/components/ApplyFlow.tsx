"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { useApp } from "@/components/Providers";
import { DesktopOnly, Footer, Gnb, useGuard } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { longDateTime } from "@/lib/format";
import { ATTEMPT_LABEL, type AttemptStatus } from "@/lib/status";

export type ResumeData = {
    name: string;
    education: { school: string; major: string; degree: string; start: string; end: string | null }[];
    career: { company: string; role: string; start: string; end: string | null; description: string }[];
    projects: { name: string; period: string; description: string; skills: string[] }[];
    skills: string[];
    certificates: { name: string; acquired: string }[];
    cover_letter: string | null;
};

export type ApplicationState = {
    application_id: string;
    attempt_status: AttemptStatus;
    next_step: "consent" | "resume";
    posting: { posting_id: string; title: string; close_at: string; release_at: string; has_coding_test: boolean };
    resume: Omit<ResumeData, "name"> | null;
    resume_name: string | null;
    pending_upload: { upload_id: string; stage: string; file_name: string } | null;
    server_time: string;
    consent_version: string;
};

export type Step = "consent" | "resume" | "precheck" | "rules";
const STEPS: { key: Step; label: string }[] = [
    { key: "consent", label: "동의" }, { key: "resume", label: "이력서" }, { key: "precheck", label: "환경 점검" }, { key: "rules", label: "시작 안내" },
];

const Ctx = createContext<{ app: ApplicationState; reload: () => Promise<void> } | null>(null);

export function useApplication() {
    const ctx = useContext(Ctx);
    if (!ctx) throw new Error("ApplyFlow missing");
    return ctx;
}

export function emptyResume(): ResumeData {
    return { name: "", education: [], career: [], projects: [], skills: [], certificates: [], cover_letter: "" };
}

/** 응시 상태로 들어갈 수 있는 단계를 정한다 (§2.3 상태별 가드). 허용이면 null, 아니면 보낼 경로 */
function redirectFor(app: ApplicationState, step: Step): { to: string; toast?: string } | null {
    const id = app.application_id;
    switch (app.attempt_status) {
        case "drafting":
            if (step === "precheck" || step === "rules") return { to: `/apply/${id}/${app.next_step}`, toast: "지원서 작성을 이어서 진행합니다" };
            if (step === "resume" && app.next_step === "consent") return { to: `/apply/${id}/consent` };
            if (step === "consent" && app.next_step === "resume") return { to: `/apply/${id}/resume` };
            return null;
        case "ready":
            return step === "precheck" || step === "rules" ? null : { to: `/apply/${id}/precheck` };
        case "interrupted":
            return { to: `/exam/${id}/resume` };
        case "interviewing":
        case "coding":
            return { to: "/mypage", toast: "다른 창에서 응시 중입니다" };
        case "completed":
            return { to: "/mypage", toast: `응시가 완료되었습니다. 결과는 ${longDateTime(app.posting.release_at)}에 공개됩니다` };
        case "not_taken_closed":
            return { to: "/mypage", toast: "마감이 되어 면접을 진행할 수 없습니다." };
        default:
            return { to: "/mypage", toast: `${ATTEMPT_LABEL[app.attempt_status]} 상태입니다` };
    }
}

export function Stepper({ current, done }: { current: Step; done: Step[] }) {
    return (
        <ol className="stepper" aria-label="지원 단계">
            {STEPS.map((s, i) => {
                const isDone = done.includes(s.key) && s.key !== current;
                const cls = s.key === current ? "current" : isDone ? "done" : "";
                return (
                    <li key={s.key} className={cls} aria-current={s.key === current ? "step" : undefined}>
                        <span className="dot">{isDone ? "✓" : i + 1}</span>{s.label}
                    </li>
                );
            })}
        </ol>
    );
}

export function ApplyFlow({ step, children }: { step: Step; children: ReactNode }) {
    const me = useGuard("applicant");
    const { applicationId } = useParams<{ applicationId: string }>();
    const router = useRouter();
    const { toast } = useApp();
    const [app, setApp] = useState<ApplicationState | null>(null);
    const [error, setError] = useState<{ status: number; message: string } | null>(null);
    const [allowed, setAllowed] = useState(false);

    const reload = useCallback(async () => {
        try {
            setApp(await api<ApplicationState>(`/applications/${applicationId}`));
        } catch (err) {
            const e = err as ApiError;
            setError({ status: e.status, message: e.message });
        }
    }, [applicationId]);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        if (me) void reload();
    }, [me, reload]);

    useEffect(() => {
        if (!app) return;
        const target = redirectFor(app, step);
        if (target) {
            if (target.toast) toast("info", target.toast);
            router.replace(target.to);
        } else {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setAllowed(true);
        }
    }, [app, step, router, toast]);

    const done: Step[] = app ? (app.attempt_status === "drafting" ? (app.next_step === "resume" ? ["consent"] : []) : ["consent", "resume"]) : [];

    return (
        <>
            <Gnb />
            <DesktopOnly>
                {error?.status === 404 ? (
                    <div className="narrow center stack"><h2>찾을 수 없는 페이지입니다</h2><Link className="btn btn-primary" href="/jobs">공고 목록으로</Link></div>
                ) : error ? (
                    <div className="container page"><ErrorBox message={error.message} onRetry={reload} /></div>
                ) : !app || !allowed ? <Loading /> : (
                    <Ctx.Provider value={{ app, reload }}>
                        <div className="apply-head">
                            <div className="container stack">
                                <Stepper current={step} done={done} />
                                <div className="row between small">
                                    <span>지원 공고: <strong>{app.posting.title}</strong></span>
                                    <span className="muted">결과 공개: {longDateTime(app.posting.release_at)}</span>
                                </div>
                            </div>
                        </div>
                        <main className="page"><div className="container">{children}</div></main>
                    </Ctx.Provider>
                )}
            </DesktopOnly>
            <Footer />
        </>
    );
}

export function BottomBar({ children }: { children: ReactNode }) {
    return <div className="bottom-bar"><div className="container">{children}</div></div>;
}
