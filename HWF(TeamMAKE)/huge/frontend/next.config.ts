import type { NextConfig } from "next";

const API = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
    output: "standalone",
    poweredByHeader: false,
    // 화면과 API 를 같은 출처(127.0.0.1:8080)로 묶어 쿠키·sendBeacon 이 사전 요청 없이 가게 한다 (API 명세서 2장)
    async rewrites() {
        return [{ source: "/api/:path*", destination: `${API}/:path*` }];
    },
    async headers() {
        return [{
            source: "/:path*",
            headers: [
                { key: "X-Frame-Options", value: "SAMEORIGIN" },
                { key: "X-Content-Type-Options", value: "nosniff" },
                { key: "Referrer-Policy", value: "same-origin" },
                { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=()" },
            ],
        }];
    },
};

export default nextConfig;
