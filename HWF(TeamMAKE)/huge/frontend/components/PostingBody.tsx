import type { ReactNode } from "react";

import { longDateTime, shortDateTime } from "@/lib/format";
import { EMPLOYMENT_LABEL } from "@/lib/status";

export type PostingDetail = {
    posting_id: string; status: string; title: string; job_code: string; company_intro: string; duties: string;
    requirements: string; preferred: string; employment_type: string; location: string; headcount: number; open_at: string;
    close_at: string; release_at: string; contact_email: string; has_coding_test: boolean;
    revisions?: { revised_at: string; field: string; summary: string }[];
};

function Section({ title, text }: { title: string; text: string }) {
    if (!text?.trim()) return null;
    // 본문은 텍스트로만 보여 준다 (HTML 해석 안 함, §6.2)
    return (
        <section>
            <h3>■ {title}</h3>
            <p className="pre">{text}</p>
        </section>
    );
}

/** S-A02 본문 + 요약. 관리자 미리보기(S-R03 3단계)도 같은 모양을 쓴다 */
export function PostingBody({ posting: p, action }: { posting: PostingDetail; action: ReactNode }) {
    const expected = p.has_coding_test ? "약 1시간 30분" : "약 30분";
    const revisions = p.revisions ?? [];
    return (
        <div style={{ marginTop: 12 }}>
            <div className="row" style={{ marginBottom: 8 }}>
                <span className="badge badge-blue">AI/AX 엔지니어</span>
                {p.has_coding_test && <span className="badge badge-gray">코딩테스트 포함</span>}
            </div>
            <h1 style={{ marginBottom: 4 }}>{p.title || "(제목 없음)"}</h1>
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 340px", gap: 24, alignItems: "start", marginTop: 20 }}>
                <article className="card stack">
                    <Section title="회사 소개" text={p.company_intro} />
                    <Section title="주요 업무" text={p.duties} />
                    <Section title="자격 요건" text={p.requirements} />
                    <Section title="우대 사항" text={p.preferred} />
                    <section>
                        <h3>■ 면접 안내</h3>
                        <ul style={{ margin: 0, paddingLeft: 20 }}>
                            <li>AI가 음성과 자막으로 10개 질문을 합니다 (답변 90초)</li>
                            <li>꼬리질문이 최대 4개 추가될 수 있습니다 (답변 60초)</li>
                            <li>한 번만 응시할 수 있고 중단 버튼이 없습니다</li>
                            <li>웹캠·마이크·스피커와 PC의 Chrome 또는 Edge 최신 버전이 필요합니다</li>
                            {p.has_coding_test && <li>AI 면접 직후 코딩테스트 2문항(Python 3, 60분)이 이어집니다</li>}
                            <li style={{ color: "var(--color-warning-text)", fontWeight: 600 }}>
                                ⚠ 접수 마감 시각({longDateTime(p.close_at)})이 되면 진행 중인 면접도 중단됩니다
                            </li>
                        </ul>
                    </section>
                    {revisions.length > 0 && (
                        <section>
                            <h3>■ 수정 사항 ({revisions.length}건)</h3>
                            <ul style={{ margin: 0, paddingLeft: 20 }} className="small">
                                {revisions.map((r) => <li key={`${r.revised_at}-${r.field}`}>{shortDateTime(r.revised_at)} {r.summary}</li>)}
                            </ul>
                        </section>
                    )}
                </article>
                <aside className="card stack" style={{ position: "sticky", top: 88 }} aria-label="공고 요약">
                    <h3>요약</h3>
                    <dl className="small" style={{ display: "grid", gridTemplateColumns: "84px 1fr", gap: "6px 8px", margin: 0 }}>
                        <dt className="muted">접수 기간</dt><dd style={{ margin: 0 }}>{shortDateTime(p.open_at)} ~ {shortDateTime(p.close_at)}</dd>
                        <dt className="muted">모집 인원</dt><dd style={{ margin: 0 }}>{p.headcount}명</dd>
                        <dt className="muted">고용 형태</dt><dd style={{ margin: 0 }}>{EMPLOYMENT_LABEL[p.employment_type] ?? p.employment_type}</dd>
                        <dt className="muted">근무지</dt><dd style={{ margin: 0 }}>{p.location}</dd>
                    </dl>
                    <hr style={{ border: 0, borderTop: "1px solid var(--color-line)", width: "100%" }} />
                    <div className="small">
                        <strong>전형 절차</strong>
                        <ol style={{ margin: "6px 0 0", paddingLeft: 20 }}>
                            <li>지원·사전 준비</li>
                            <li>AI 면접 약 25분</li>
                            {p.has_coding_test && <li>코딩테스트 60분 (Python)</li>}
                            <li>결과 공개 {longDateTime(p.release_at)}</li>
                        </ol>
                        <p style={{ marginTop: 8 }}>예상 소요 <strong>{expected}</strong></p>
                    </div>
                    {action}
                </aside>
            </div>
        </div>
    );
}
