"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { shortDateTime } from "@/lib/format";

type Item = { notification_id: string; kind: string; title: string; link: string | null; read: boolean; created_at: string };
const POLL_MS = 60_000;
const MENU_WIDTH = 340;
const EDGE = 12;

/** 머리글 🔔 사이트 알림 최근 20건 (API 명세서 9장 GET /notifications) */
export function NotificationBell() {
    const router = useRouter();
    const [items, setItems] = useState<Item[]>([]);
    const [unread, setUnread] = useState(0);
    const [open, setOpen] = useState(false);
    const [pos, setPos] = useState({ top: 0, left: 0, width: MENU_WIDTH });
    const box = useRef<HTMLDivElement>(null);

    const load = useCallback(() => {
        api<{ unread: number; items: Item[] }>("/notifications").then((r) => { setItems(r.items); setUnread(r.unread); }).catch(() => undefined);
    }, []);

    useEffect(() => {
        load();
        const timer = window.setInterval(load, POLL_MS);
        return () => window.clearInterval(timer);
    }, [load]);

    useEffect(() => {
        if (!open) return;
        const close = (e: MouseEvent | KeyboardEvent) => {
            if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", close);
        document.addEventListener("keydown", close);
        return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
    }, [open]);

    async function choose(item: Item) {
        setOpen(false);
        if (!item.read) {
            await api(`/notifications/${item.notification_id}/read`, { method: "POST" }).catch(() => undefined);
            load();
        }
        if (item.link) router.push(item.link);
    }

    // 지우기는 목록에서 숨기는 것이다 (메일 발송 기록은 남는다)
    async function hide(item: Item) {
        setItems((cur) => cur.filter((x) => x.notification_id !== item.notification_id));
        await api(`/notifications/${item.notification_id}/hide`, { method: "POST" }).catch(() => undefined);
        load();
    }

    async function hideRead() {
        setItems((cur) => cur.filter((x) => !x.read));
        await api("/notifications/hide-read", { method: "POST" }).catch(() => undefined);
        load();
    }

    const hasRead = items.some((x) => x.read);

    // 상자를 🔔 아래에 두되 화면 밖으로 나가지 않게 한다 (좁은 화면에서 머리글이 줄바꿈되면 🔔가 왼쪽에 온다)
    const place = useCallback(() => {
        if (!box.current) return;
        const rect = box.current.getBoundingClientRect();
        const width = Math.min(MENU_WIDTH, window.innerWidth - EDGE * 2);
        const left = Math.min(Math.max(rect.right - width, EDGE), window.innerWidth - width - EDGE);
        setPos({ top: rect.bottom + 4, left, width });
    }, []);

    // 열린 채로 창 크기가 바뀌거나 스크롤되면 🔔를 따라간다
    useEffect(() => {
        if (!open) return;
        window.addEventListener("resize", place);
        window.addEventListener("scroll", place, true);
        return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
    }, [open, place]);

    function toggle() {
        if (!open) place();
        setOpen((v) => !v);
    }

    return (
        <div ref={box} style={{ position: "relative" }}>
            <button type="button" className="btn btn-text btn-sm" aria-haspopup="true" aria-expanded={open}
                aria-label={`알림${unread ? ` ${unread}건 안 읽음` : ""}`} onClick={toggle}>
                🔔{unread > 0 && <span className="badge badge-orange" style={{ marginLeft: 4, height: 20 }}>{unread}</span>}
            </button>
            {open && (
                <div className="card stack" role="menu" style={{ position: "fixed", top: pos.top, left: pos.left, zIndex: 50, width: pos.width, maxHeight: 420, overflowY: "auto", overflowX: "hidden", gap: 4, padding: 8 }}>
                    {hasRead && (
                        <div className="row" style={{ justifyContent: "flex-end" }}>
                            <button type="button" className="btn btn-text btn-sm tiny" onClick={hideRead}>읽은 알림 모두 지우기</button>
                        </div>
                    )}
                    {items.length === 0 && <p className="small muted" style={{ margin: 8 }}>새 알림이 없습니다</p>}
                    {items.map((item) => (
                        <div key={item.notification_id} className="row" style={{ gap: 0, alignItems: "flex-start", flexWrap: "nowrap" }}>
                            <button type="button" role="menuitem" className="btn btn-text"
                                style={{ display: "block", flex: 1, minWidth: 0, textAlign: "left", height: "auto", padding: "8px 10px", whiteSpace: "normal", overflowWrap: "anywhere", fontWeight: item.read ? 400 : 700 }}
                                onClick={() => choose(item)}>
                                <span className="small">{item.title}</span>
                                <span className="tiny muted" style={{ display: "block" }}>{shortDateTime(item.created_at)}</span>
                            </button>
                            <button type="button" className="btn btn-text btn-sm muted" aria-label={`${item.title} 알림 지우기`} title="지우기"
                                style={{ padding: "8px 6px", flexShrink: 0 }} onClick={() => hide(item)}>✕</button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
