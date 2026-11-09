"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, ApiError, UNAUTHORIZED_EVENT } from "@/lib/api";

export type Me = { user_id: string; email: string; name: string; phone: string | null; role: "applicant" | "admin"; password_change_required: boolean };

type ToastKind = "ok" | "info" | "warn" | "error";
type Toast = { id: number; kind: ToastKind; text: string; retry?: () => void };

type AppContext = {
    me: Me | null;
    meLoaded: boolean;
    refreshMe: () => Promise<Me | null>;
    toast: (kind: ToastKind, text: string, retry?: () => void) => void;
};

const Ctx = createContext<AppContext | null>(null);
// 자동 닫힘 시간 (§4.5). 오류는 수동으로 닫는다
const TOAST_MS: Record<ToastKind, number | null> = { ok: 3000, info: 4000, warn: 6000, error: null };

export function Providers({ children }: { children: ReactNode }) {
    const [me, setMe] = useState<Me | null>(null);
    const [meLoaded, setMeLoaded] = useState(false);
    const [toasts, setToasts] = useState<Toast[]>([]);

    const refreshMe = useCallback(async () => {
        try {
            const data = await api<Me>("/auth/me");
            setMe(data);
            return data;
        } catch (error) {
            if (!(error instanceof ApiError) || error.status !== 401) console.warn("auth/me failed", error);
            setMe(null);
            return null;
        } finally {
            setMeLoaded(true);
        }
    }, []);

    useEffect(() => {
        // 처음 한 번 서버에서 로그인 상태를 읽어 온다 (외부 시스템 동기화)
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void refreshMe();
    }, [refreshMe]);

    const dismiss = useCallback((id: number) => setToasts((list) => list.filter((t) => t.id !== id)), []);

    const toast = useCallback((kind: ToastKind, text: string, retry?: () => void) => {
        const id = Date.now() + Math.random();
        setToasts((list) => [...list.slice(-3), { id, kind, text, retry }]);
        const ms = TOAST_MS[kind];
        if (ms) window.setTimeout(() => dismiss(id), ms);
    }, [dismiss]);

    // 다른 API 가 401 이면 로그인이 끝난 것: 이전 사용자 정보를 지우고, 보호된 화면은 가드가 로그인으로 보낸다
    const meRef = useRef<Me | null>(null);
    useEffect(() => { meRef.current = me; }, [me]);
    useEffect(() => {
        const onUnauthorized = () => {
            if (meRef.current === null) return;
            meRef.current = null;
            setMe(null);
            toast("warn", "로그인이 끝났습니다. 다시 로그인해 주세요");
        };
        window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
        return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    }, [toast]);

    const value = useMemo(() => ({ me, meLoaded, refreshMe, toast }), [me, meLoaded, refreshMe, toast]);

    return (
        <Ctx.Provider value={value}>
            {children}
            <div className="toasts">
                <div aria-live="polite" className="sr-only">{toasts.filter((t) => t.kind !== "error").map((t) => t.text).join(" ")}</div>
                <div aria-live="assertive" className="sr-only">{toasts.filter((t) => t.kind === "error").map((t) => t.text).join(" ")}</div>
                {toasts.map((t) => (
                    <div key={t.id} className={`toast toast-${t.kind}`}>
                        <span style={{ flex: 1 }}>{t.text}</span>
                        {t.retry && <button type="button" onClick={() => { dismiss(t.id); t.retry?.(); }}>다시 시도</button>}
                        {t.kind === "error" && <button type="button" onClick={() => dismiss(t.id)} aria-label="알림 닫기">닫기</button>}
                    </div>
                ))}
            </div>
        </Ctx.Provider>
    );
}

export function useApp(): AppContext {
    const ctx = useContext(Ctx);
    if (!ctx) throw new Error("Providers missing");
    return ctx;
}
