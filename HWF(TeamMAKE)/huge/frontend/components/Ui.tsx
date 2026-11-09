"use client";

import { cloneElement, isValidElement, useEffect, useId, useRef, type ReactElement, type ReactNode, type RefObject } from "react";

import { ATTEMPT_BADGE, ATTEMPT_LABEL, type AttemptStatus } from "@/lib/status";

export function StatusBadge({ status }: { status: AttemptStatus }) {
    return <span className={`badge ${ATTEMPT_BADGE[status]}`}>{ATTEMPT_LABEL[status]}</span>;
}

export function Spinner({ label }: { label?: string }) {
    return <span className="spinner" role="status" aria-label={label ?? "처리 중"} />;
}

/** 요청 중에는 비활성 + 스피너 (중복 제출 방지, §4.3). 비활성 사유는 버튼 아래 한 줄 */
export function Button({ kind = "primary", busy = false, disabled, reason, children, size, ...rest }:
    { kind?: "primary" | "secondary" | "danger" | "text"; busy?: boolean; reason?: string | null; size?: "lg" | "sm" } &
    React.ButtonHTMLAttributes<HTMLButtonElement>) {
    const off = disabled || busy;
    const reasonId = useId();
    const showReason = Boolean(reason && disabled);
    // 비활성 사유를 버튼에 이어 화면 낭독기도 왜 못 누르는지 읽게 한다 (E16)
    const button = (
        <button type="button" className={`btn btn-${kind}${size ? ` btn-${size}` : ""}`} disabled={off} aria-busy={busy || undefined}
            aria-describedby={showReason ? reasonId : undefined} {...rest}>
            {busy && <Spinner />}
            {children}
        </button>
    );
    if (!showReason) return button;
    return (
        <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-end" }}>
            {button}
            <span className="disabled-reason" id={reasonId}>{reason}</span>
        </span>
    );
}

/** 모달: 포커스 가두기, ESC 닫기. 응시 중 모달은 escClose=false (§4.5) */
/** 대화상자 안에 포커스를 가두고, 닫히면 원래 자리로 돌려준다 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, escClose = false, onClose?: () => void) {
    // 부모가 다시 그려질 때마다 첫 칸으로 포커스가 튀지 않도록 onClose 는 ref 로 들고 있는다
    const closeRef = useRef(onClose);
    useEffect(() => { closeRef.current = onClose; }, [onClose]);

    useEffect(() => {
        const node = ref.current;
        const previous = document.activeElement as HTMLElement | null;
        const focusables = () => Array.from(node?.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], input, select, textarea") ?? []);
        const first = focusables()[0];
        if (first) first.focus();
        else if (node) {
            // 버튼 없는 대화상자(연결 확인 중 등)는 상자 자체에 포커스를 둔다. 안 그러면 뒤 화면에 포커스가 남는다 (E16)
            node.tabIndex = -1;
            node.focus();
        }
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape" && escClose && closeRef.current) closeRef.current();
            if (event.key !== "Tab") return;
            const list = focusables();
            if (list.length === 0) return;
            const first = list[0];
            const last = list[list.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        };
        document.addEventListener("keydown", onKey);
        return () => {
            document.removeEventListener("keydown", onKey);
            previous?.focus?.();
        };
    }, [ref, escClose]);
}

export function Modal({ title, children, actions, onClose, escClose = true, labelId = "modal-title" }:
    { title: string; children: ReactNode; actions: ReactNode; onClose?: () => void; escClose?: boolean; labelId?: string }) {
    const ref = useRef<HTMLDivElement>(null);
    useFocusTrap(ref, escClose, onClose);

    return (
        <div className="overlay">
            <div className="modal" role="dialog" aria-modal="true" aria-labelledby={labelId} ref={ref}>
                <h2 id={labelId}>{title}</h2>
                <div>{children}</div>
                <div className="actions">{actions}</div>
            </div>
        </div>
    );
}

export function Field({ label, required, error, hint, children }: { label: string; required?: boolean; error?: string | null; hint?: string; children: ReactNode }) {
    return (
        <FieldBody label={label} required={required} error={error} hint={hint}>{children}</FieldBody>
    );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
    return (
        <div className="card center" style={{ padding: 48 }}>
            <h3>{title}</h3>
            {children && <div className="muted">{children}</div>}
        </div>
    );
}

export function Loading() {
    return <div className="center muted" style={{ padding: 64 }}><Spinner label="불러오는 중" /> 불러오는 중…</div>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
    return (
        <div className="notice notice-error row between" role="alert">
            <span>{message}</span>
            {onRetry && <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>다시 시도</button>}
        </div>
    );
}

const FORM_TAGS = new Set(["input", "select", "textarea"]);

/** 입력이 하나면 라벨·오류·필수를 그 입력에 이어 붙인다. 여러 요소를 감싼 경우는 label 로 감싼다 */
function FieldBody({ label, required, error, hint, children }: { label: string; required?: boolean; error?: string | null; hint?: string; children: ReactNode }) {
    const id = useId();
    const noteId = `${id}-note`;
    const note = error ? <div id={noteId} className="field-error" role="alert">{error}</div> : hint ? <div id={noteId} className="field-hint">{hint}</div> : null;
    const head = <>{label}{required && <span className="req" aria-hidden>*</span>}</>;
    if (isValidElement(children) && typeof children.type === "string" && FORM_TAGS.has(children.type)) {
        const input = cloneElement(children as ReactElement<Record<string, unknown>>, {
            id, "aria-invalid": error ? true : undefined, "aria-describedby": note ? noteId : undefined, "aria-required": required || undefined,
        });
        return <div className="field"><label htmlFor={id}>{head}</label>{input}{note}</div>;
    }
    return <label className="field"><span>{head}</span>{children}{note}</label>;
}
