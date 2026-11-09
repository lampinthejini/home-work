import { NextResponse, type NextRequest } from "next/server";

// localhost 와 127.0.0.1 은 다른 출처라 쿠키·WebSocket Origin 검사가 어긋난다 → 127.0.0.1 로 맞춘다 (API 명세서 2-5)
export function proxy(request: NextRequest) {
    const host = request.headers.get("host") ?? "";
    if (host.startsWith("localhost")) {
        const url = new URL(request.url);
        url.host = host.replace("localhost", "127.0.0.1");
        return NextResponse.redirect(url);
    }
    return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/|api/).*)"] };
