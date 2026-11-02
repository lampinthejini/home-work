// 모든 시각은 서버가 준 Asia/Seoul 시각으로 보여 준다 (기술 아키텍처 11장)

const TZ = "Asia/Seoul";

function parts(iso: string) {
    const date = new Date(iso);
    const fmt = new Intl.DateTimeFormat("ko-KR", {
        timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, weekday: "short",
    });
    const map: Record<string, string> = {};
    for (const p of fmt.formatToParts(date)) map[p.type] = p.value;
    return { year: map.year, month: map.month, day: map.day, hour: map.hour === "24" ? "00" : map.hour, minute: map.minute, weekday: map.weekday };
}

/** 11월 12일(목) 10:00 */
export function longDateTime(iso?: string | null): string {
    if (!iso) return "-";
    const p = parts(iso);
    return `${Number(p.month)}월 ${Number(p.day)}일(${p.weekday}) ${p.hour}:${p.minute}`;
}

/** 11.12 10:00 */
export function shortDateTime(iso?: string | null): string {
    if (!iso) return "-";
    const p = parts(iso);
    return `${p.month}.${p.day} ${p.hour}:${p.minute}`;
}

/** 2026.11.12 */
export function dateOnly(iso?: string | null): string {
    if (!iso) return "-";
    const p = parts(iso);
    return `${p.year}.${p.month}.${p.day}`;
}

/** datetime-local 입력값 ↔ ISO(+09:00) */
export function toLocalInput(iso?: string | null): string {
    if (!iso) return "";
    const p = parts(iso);
    return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

export function fromLocalInput(value: string): string | null {
    return value ? `${value}:00+09:00` : null;
}

export function mmss(totalSec: number): string {
    const sec = Math.max(0, Math.round(totalSec));
    return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
}

export function untilText(fromMs: number, toIso: string): string {
    const diff = new Date(toIso).getTime() - fromMs;
    if (diff <= 0) return "마감";
    const days = Math.floor(diff / 86_400_000);
    if (days >= 1) return `D-${days}`;
    const hours = Math.floor(diff / 3_600_000);
    return hours >= 1 ? `${hours}시간 남음` : `${Math.max(1, Math.floor(diff / 60_000))}분 남음`;
}
