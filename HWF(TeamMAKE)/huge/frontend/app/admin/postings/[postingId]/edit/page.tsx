"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { PostingEditor } from "@/components/PostingEditor";
import { ErrorBox, Loading } from "@/components/Ui";
import { api, ApiError } from "@/lib/api";
import type { AdminPosting } from "@/lib/admin";

export default function EditPostingPage() {
    const { postingId } = useParams<{ postingId: string }>();
    const [posting, setPosting] = useState<AdminPosting | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api<AdminPosting>(`/admin/postings/${postingId}`).then(setPosting).catch((err) => setError((err as ApiError).message));
    }, [postingId]);

    return (
        <AdminShell title="공고 수정">
            {error && <ErrorBox message={error} />}
            {!error && !posting && <Loading />}
            {posting && posting.status === "closed" && (
                <div className="notice notice-info">마감된 공고는 수정할 수 없습니다. <Link href={`/admin/applicants?posting=${posting.posting_id}`}>지원자 보기</Link></div>
            )}
            {posting && posting.status !== "closed" && <PostingEditor posting={posting} />}
        </AdminShell>
    );
}
