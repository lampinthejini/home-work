// API 호출. 같은 출처 /api → FastAPI (next.config rewrites). 오류는 {code, message} 한 모양 (API 명세서 2장)

export class ApiError extends Error {
    status: number;
    code: string;

    constructor(status: number, code: string, message: string) {
        super(message);
        this.status = status;
        this.code = code;
    }
}

export const UNAUTHORIZED_EVENT = "huge:unauthorized";

type Body = Record<string, unknown> | unknown[] | FormData | undefined;

export async function api<T = unknown>(path: string, options: { method?: string; body?: Body; signal?: AbortSignal } = {}): Promise<T> {
    const { method = options.body === undefined ? "GET" : "POST", body, signal } = options;
    const init: RequestInit = { method, credentials: "same-origin", signal, cache: "no-store" };
    if (body instanceof FormData) {
        init.body = body;
    } else if (body !== undefined) {
        init.body = JSON.stringify(body);
        init.headers = { "content-type": "application/json" };
    }
    let res: Response;
    try {
        res = await fetch(`/api${path}`, init);
    } catch (error) {
        if ((error as Error).name === "AbortError") throw error;
        throw new ApiError(0, "NETWORK", "서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.");
    }
    if (res.status === 204) return undefined as T;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        // 로그인이 끝났다: 화면에 남은 사용자 정보를 지우도록 알린다 (§2.3). 로그인 확인용 /auth/* 는 제외
        if (res.status === 401 && !path.startsWith("/auth/") && typeof window !== "undefined") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
        throw new ApiError(res.status, data.code ?? "UNKNOWN", data.message ?? "요청을 처리하지 못했습니다.");
    }
    return data as T;
}

export function loginPath(): string {
    const here = typeof window === "undefined" ? "/" : window.location.pathname + window.location.search;
    return `/login?next=${encodeURIComponent(here)}`;
}
