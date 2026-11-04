"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { useApp } from "@/components/Providers";
import { Button, ErrorBox, Loading, Modal } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import { shortDateTime } from "@/lib/format";

type Settings = {
    max_concurrent_interviews: number; active_interviews: number; login_contact_email: string;
    history: { key: string; from: number | null; to: number; at: string }[];
};

function SettingsBody() {
    const { toast } = useApp();
    const [data, setData] = useState<Settings | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [value, setValue] = useState("");
    const [contact, setContact] = useState("");
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        try {
            const s = await api<Settings>("/admin/settings");
            setData(s);
            setValue(String(s.max_concurrent_interviews));
            setContact(s.login_contact_email);
            setError(null);
        } catch (err) {
            setError((err as ApiError).message);
        }
    }, []);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void load();
    }, [load]);

    async function save() {
        setBusy(true);
        try {
            await api("/admin/settings/max_concurrent_interviews", { method: "PUT", body: { value: Number(value) } });
            toast("ok", "저장했습니다");
            setConfirming(false);
            await load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    async function saveContact() {
        setBusy(true);
        try {
            await api("/admin/settings/login_contact_email", { method: "PUT", body: { value: contact.trim() } });
            toast("ok", "저장했습니다");
            await load();
        } catch (err) {
            toast("error", (err as ApiError).message);
        } finally {
            setBusy(false);
        }
    }

    if (error) return <ErrorBox message={error} onRetry={load} />;
    if (!data) return <Loading />;
    const next = Number(value);
    const valid = Number.isInteger(next) && next >= 1 && next <= 20;

    return (
        <div className="card stack" style={{ maxWidth: 720 }}>
            <div className="row" style={{ gap: 12, alignItems: "center" }}>
                <label htmlFor="max-concurrent" style={{ fontWeight: 600 }}>동시 면접 상한 (N)</label>
                <input id="max-concurrent" className="input" type="number" min={1} max={20} style={{ width: 90 }} value={value}
                    onChange={(e) => setValue(e.target.value)} aria-invalid={!valid} />명
                <span className="small muted">현재 진행 중 {data.active_interviews}명</span>
            </div>
            <div className="small muted">
                ⓘ 바꾸면 다음 입장부터 바로 적용됩니다. 낮춰도 진행 중인 면접은 끊지 않습니다. AI 면접만 세고 코딩테스트는 세지 않습니다.
            </div>
            {!valid && <div className="small" style={{ color: "var(--color-danger)" }}>1~20 사이의 정수로 입력해 주세요.</div>}
            <div className="row">
                <span style={{ flex: 1 }} />
                <Button onClick={() => setConfirming(true)} disabled={!valid || next === data.max_concurrent_interviews}
                    reason={valid ? "지금 값과 같습니다" : "1~20 사이의 정수로 입력해 주세요"}>저장</Button>
            </div>
            <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
            <div className="row" style={{ gap: 12, alignItems: "center" }}>
                <label htmlFor="login-contact" style={{ fontWeight: 600 }}>로그인 차단 문의 이메일</label>
                <input id="login-contact" className="input" type="email" maxLength={254} style={{ flex: 1 }} value={contact}
                    onChange={(e) => setContact(e.target.value)} />
                <Button busy={busy} onClick={saveContact} disabled={contact.trim() === data.login_contact_email}
                    reason="지금 값과 같습니다">저장</Button>
            </div>
            <div className="small muted">ⓘ 비워 두면 차단 안내에 &apos;담당자에게 보내 주세요&apos;로 표시됩니다.</div>
            <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
            <div className="small">
                <strong>최근 변경</strong>
                {data.history.length === 0 ? <div className="muted">변경 기록이 없습니다</div> : (
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                        {data.history.map((h) => <li key={h.at}>{shortDateTime(h.at)} · {h.from ?? "?"} → {h.to} (관리자)</li>)}
                    </ul>
                )}
            </div>
            {confirming && (
                <Modal title="설정을 바꿀까요?" onClose={() => setConfirming(false)} actions={(
                    <>
                        <button type="button" className="btn btn-secondary" onClick={() => setConfirming(false)}>취소</button>
                        <Button busy={busy} onClick={save}>바꾸기</Button>
                    </>
                )}>
                    <p>동시 면접 상한을 {data.max_concurrent_interviews}명에서 {next}명으로 바꿉니다.</p>
                </Modal>
            )}
        </div>
    );
}

export default function SettingsPage() {
    return <AdminShell title="운영 설정"><SettingsBody /></AdminShell>;
}
