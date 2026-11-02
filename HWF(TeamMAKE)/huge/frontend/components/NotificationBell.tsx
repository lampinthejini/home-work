"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { shortDateTime } from "@/lib/format";

type Item = { notification_id: string; kind: string; title: string; link: string | null; read: boolean; created_at: string };
const POLL_MS = 60_000;

/** 머리글 🔔 사이트 알림 최근 20건 (API 명세서 9장 GET /notifications) */
export function NotificationBell() {
    const router = useRouter();
    const [items, setItems] = useState<Item[]>([]);
    const [unread, setUnread] = useState(0);
    const [open, setOpen] = useState(false);
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

    return (
        <div ref={box} style={{ position: "relative" }}>
            <button type="button" className="btn btn-text btn-sm" aria-haspopup="true" aria-expanded={open}
                aria-label={`알림${unread ? ` ${unread}건 안 읽음` : ""}`} onClick={() => setOpen((v) => !v)}>
                🔔{unread > 0 && <span className="badge badge-orange" style={{ marginLeft: 4, height: 20 }}>{unread}</span>}
            </button>
            {open && (
                <div className="card stack" role="menu" style={{ position: "absolute", right: 0, top: "100%", zIndex: 50, width: 340, maxHeight: 420, overflow: "auto", gap: 4, padding: 8 }}>
                    {items.length === 0 && <p className="small muted" style={{ margin: 8 }}>새 알림이 없습니다</p>}
                    {items.map((item) => (
                        <button key={item.notification_id} type="button" role="menuitem" className="btn btn-text"
                            style={{ display: "block", textAlign: "left", height: "auto", padding: "8px 10px", fontWeight: item.read ? 400 : 700 }}
                            onClick={() => choose(item)}>
                            <span className="small">{item.title}</span>
                            <span className="tiny muted" style={{ display: "block" }}>{shortDateTime(item.created_at)}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
