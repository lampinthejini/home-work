"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Mascot } from "@/components/Brand";
import { PostingEditor } from "@/components/PostingEditor";

/** 새 공고: 작성 방식 선택 (S-R01 모달 내용을 한 화면으로) → AI 초안(S-R02) 또는 직접 작성(S-R03) */
function NewPosting() {
    const mode = useSearchParams().get("mode");
    if (mode === "manual") return <PostingEditor posting={null} />;
    return (
        <div className="grid2" style={{ maxWidth: 880 }}>
            <div className="card stack center">
                <Mascot name="01-guide" size={120} />
                <h2 style={{ margin: 0 }}>✨ AI로 공고 자동 만들기</h2>
                <p className="muted">몇 가지 질문에 답하면 AI가 우리 회사에 맞는 초안을 씁니다.<br />1분 이내 · 초안은 검토·수정 후 게시합니다.</p>
                <Link className="btn btn-primary" href="/admin/postings/ai">AI로 만들기</Link>
            </div>
            <div className="card stack center">
                <Mascot name="05-report" size={120} />
                <h2 style={{ margin: 0 }}>✍ 직접 작성</h2>
                <p className="muted">빈 양식에 처음부터 작성합니다.<br />&nbsp;</p>
                <Link className="btn btn-secondary" href="/admin/postings/new?mode=manual">직접 작성</Link>
            </div>
        </div>
    );
}

export default function NewPostingPage() {
    return <AdminShell title="새 공고 만들기"><Suspense><NewPosting /></Suspense></AdminShell>;
}
