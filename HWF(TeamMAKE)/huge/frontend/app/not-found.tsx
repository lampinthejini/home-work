import Link from "next/link";

import { Mascot } from "@/components/Brand";
import { SiteShell } from "@/components/Shell";

export default function NotFound() {
    return (
        <SiteShell>
            <div className="narrow center stack">
                <Mascot name="04-discovery" size={180} />
                <h2>찾을 수 없는 페이지입니다</h2>
                <p className="muted">주소가 바뀌었거나 볼 수 있는 권한이 없는 페이지입니다.</p>
                <Link className="btn btn-primary" href="/jobs">공고 목록으로</Link>
            </div>
        </SiteShell>
    );
}
