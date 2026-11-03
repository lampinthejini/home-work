"use client";

import { useState } from "react";

import type { ResumeData } from "@/components/ApplyFlow";

export type ListKey = "education" | "career" | "projects" | "certificates";
type Column = { key: string; label: string; placeholder?: string; wide?: boolean };

export const RESUME_SECTIONS: Record<ListKey, { title: string; columns: Column[]; blank: () => Record<string, unknown> }> = {
    education: {
        title: "학력",
        columns: [{ key: "school", label: "학교" }, { key: "major", label: "전공" }, { key: "degree", label: "학위", placeholder: "학사" },
            { key: "start", label: "입학", placeholder: "2020-03" }, { key: "end", label: "졸업", placeholder: "2024-02" }],
        blank: () => ({ school: "", major: "", degree: "", start: "", end: "" }),
    },
    career: {
        title: "경력",
        columns: [{ key: "company", label: "회사" }, { key: "role", label: "직무" }, { key: "start", label: "시작", placeholder: "2022-01" },
            { key: "end", label: "종료", placeholder: "재직 중이면 비움" }, { key: "description", label: "주요 업무", wide: true }],
        blank: () => ({ company: "", role: "", start: "", end: "", description: "" }),
    },
    projects: {
        title: "프로젝트",
        columns: [{ key: "name", label: "프로젝트명" }, { key: "period", label: "기간", placeholder: "2023.03~2023.08" }, { key: "description", label: "설명", wide: true }],
        blank: () => ({ name: "", period: "", description: "", skills: [] }),
    },
    certificates: {
        title: "자격",
        columns: [{ key: "name", label: "자격명" }, { key: "acquired", label: "취득", placeholder: "2023-05" }],
        blank: () => ({ name: "", acquired: "" }),
    },
};

export function resumeRequirement(resume: ResumeData) {
    const name = resume.name.trim().length > 0;
    const history = resume.education.some((e) => e.school.trim()) || resume.career.some((c) => c.company.trim());
    return { name, history, ok: name && history };
}

/** S-A05 입력 영역. 바뀐 칸 이름을 onEdit 으로 알린다 (edited_fields) */
const LOW_CONF_STYLE = { background: "var(--color-warning-soft)", borderColor: "var(--color-warning)" };

/** OCR 신뢰도가 낮은 칸 표시: 이름 앞 🔍 + [확인] 버튼 */
function LowConfLabel({ label, field, lowConf, onConfirm, className }: {
    label: string; field: string; lowConf?: Set<string>; onConfirm?: (field: string) => void; className?: string;
}) {
    if (!lowConf?.has(field)) return <span className={className}>{label}</span>;
    return (
        <span className={`row ${className ?? ""}`} style={{ gap: 6 }}>
            <span title="글자 인식이 불확실합니다">🔍 {label}</span>
            <button type="button" className="btn btn-text btn-sm" style={{ minHeight: 0, padding: "0 4px" }}
                onClick={(e) => { e.preventDefault(); onConfirm?.(field); }}>확인</button>
        </span>
    );
}

export function ResumeForm({ value, onChange, onEdit, invalid, lowConf, onConfirm }: {
    value: ResumeData; onChange: (next: ResumeData) => void; onEdit?: (field: string) => void; invalid?: { name?: boolean; history?: boolean };
    lowConf?: Set<string>; onConfirm?: (field: string) => void;
}) {
    const flagged = (field: string) => (lowConf?.has(field) ? LOW_CONF_STYLE : undefined);
    const [skill, setSkill] = useState("");
    const edit = (field: string, next: ResumeData) => { onEdit?.(field); onChange(next); };

    function updateItem(list: ListKey, index: number, key: string, text: string) {
        const items = [...(value[list] as Record<string, unknown>[])];
        items[index] = { ...items[index], [key]: text };
        edit(`${list}[${index}].${key}`, { ...value, [list]: items });
    }

    function addSkill() {
        const s = skill.trim();
        if (s && !value.skills.includes(s) && value.skills.length < 60) edit("skills", { ...value, skills: [...value.skills, s] });
        setSkill("");
    }

    return (
        <div className="stack">
            <section className="stack">
                <h3>기본 정보</h3>
                <label className="field" id="field-name">
                    <span className="row" style={{ gap: 0 }}><LowConfLabel label="성명" field="name" lowConf={lowConf} onConfirm={onConfirm} /><span className="req" aria-hidden>*</span></span>
                    <input className="input" value={value.name} maxLength={100} aria-invalid={invalid?.name || undefined} style={flagged("name")}
                        onChange={(e) => edit("name", { ...value, name: e.target.value })} />
                </label>
            </section>
            {(Object.keys(RESUME_SECTIONS) as ListKey[]).map((list) => {
                const spec = RESUME_SECTIONS[list];
                const items = value[list] as Record<string, string>[];
                const highlight = invalid?.history && (list === "education" || list === "career");
                return (
                    <section key={list} className="stack" id={`field-${list}`}
                        style={highlight ? { outline: "2px solid var(--color-danger)", outlineOffset: 6, borderRadius: 8 } : undefined}>
                        <div className="row between">
                            <h3 style={{ margin: 0 }}>{spec.title}</h3>
                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => edit(list, { ...value, [list]: [...items, spec.blank()] })}>+ 추가</button>
                        </div>
                        {items.length === 0 && <p className="small muted">아직 없습니다</p>}
                        {items.map((item, index) => (
                            <div key={index} className="card tight" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 8, alignItems: "end" }}>
                                {spec.columns.map((col) => (
                                    <label key={col.key} className="field" style={col.wide ? { gridColumn: "1 / -1" } : undefined}>
                                        <LowConfLabel className="tiny" label={col.label} field={`${list}[${index}].${col.key}`} lowConf={lowConf} onConfirm={onConfirm} />
                                        {col.wide ? (
                                            <textarea className="input" value={item[col.key] ?? ""} placeholder={col.placeholder} maxLength={2000}
                                                onChange={(e) => updateItem(list, index, col.key, e.target.value)} style={{ minHeight: 64, ...flagged(`${list}[${index}].${col.key}`) }} />
                                        ) : (
                                            <input className="input" value={item[col.key] ?? ""} placeholder={col.placeholder} maxLength={200}
                                                style={flagged(`${list}[${index}].${col.key}`)} onChange={(e) => updateItem(list, index, col.key, e.target.value)} />
                                        )}
                                    </label>
                                ))}
                                <button type="button" className="btn btn-text btn-sm" style={{ color: "var(--color-danger)", justifySelf: "end" }}
                                    onClick={() => edit(list, { ...value, [list]: items.filter((_, i) => i !== index) })}>삭제</button>
                            </div>
                        ))}
                    </section>
                );
            })}
            <section className="stack">
                <h3>기술</h3>
                <div className="row">
                    {value.skills.map((s) => (
                        <span key={s} className="badge badge-blue" style={{ height: 30 }}>
                            {s}
                            <button type="button" aria-label={`${s} 지우기`} onClick={() => edit("skills", { ...value, skills: value.skills.filter((x) => x !== s) })}
                                style={{ background: "none", border: 0, cursor: "pointer", color: "inherit", marginLeft: 4 }}>✕</button>
                        </span>
                    ))}
                    <input className="input" style={{ width: 180, minHeight: 36 }} value={skill} placeholder="기술 입력 후 Enter" maxLength={40}
                        onChange={(e) => setSkill(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSkill(); } }} />
                    <button type="button" className="btn btn-secondary btn-sm" onClick={addSkill}>+</button>
                </div>
            </section>
            <label className="field">
                <span>자기소개서 (선택)</span>
                <textarea className="input" value={value.cover_letter ?? ""} maxLength={5000} style={{ minHeight: 160 }}
                    onChange={(e) => edit("cover_letter", { ...value, cover_letter: e.target.value })} />
                <div className="field-hint">{(value.cover_letter ?? "").length} / 5000자</div>
            </label>
        </div>
    );
}
