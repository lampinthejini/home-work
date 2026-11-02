"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApplyFlow, BottomBar, useApplication } from "@/components/ApplyFlow";
import { Precheck } from "@/components/Precheck";
import { useApp } from "@/components/Providers";
import { Button } from "@/components/Ui";
import { shortDateTime } from "@/lib/format";

function PrecheckStep() {
    const { app } = useApplication();
    const router = useRouter();
    const { toast } = useApp();
    const [passed, setPassed] = useState(false);

    function later() {
        toast("info", `마이페이지에서 언제든 응시를 이어서 준비할 수 있습니다 (접수 마감 ${shortDateTime(app.posting.close_at)}까지)`);
        router.push("/jobs");
    }

    return (
        <>
            <Precheck applicationId={app.application_id} onPassed={setPassed} />
            <BottomBar>
                <button type="button" className="btn btn-secondary" onClick={later}>나중에 응시하기</button>
                <span style={{ flex: 1 }} />
                <Button disabled={!passed} reason="5개 항목을 모두 통과해야 다음으로 갈 수 있습니다" onClick={() => router.push(`/apply/${app.application_id}/rules`)}>
                    다음: 시작 안내 ▶
                </Button>
            </BottomBar>
        </>
    );
}

export default function PrecheckPage() {
    return <ApplyFlow step="precheck"><PrecheckStep /></ApplyFlow>;
}
