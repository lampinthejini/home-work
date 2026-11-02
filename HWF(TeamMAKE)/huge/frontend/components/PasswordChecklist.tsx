// 비밀번호 규칙 4줄 체크리스트 (PRD 5-1, 화면정의서 §5.2). 서버도 같은 규칙으로 검사한다

export function passwordRules(password: string, email: string) {
    const localPart = email.split("@")[0]?.toLowerCase() ?? "";
    return [
        { ok: password.length >= 8 && password.length <= 64, text: "8~64자" },
        { ok: /[A-Za-z]/.test(password) && /\d/.test(password) && /[^A-Za-z0-9]/.test(password), text: "영문·숫자·특수문자 각 1자 이상" },
        { ok: password.length > 0 && !(localPart && password.toLowerCase().includes(localPart)), text: "이메일 아이디(@ 앞) 포함 금지" },
        { ok: password.length > 0 && !/(.)\1{3,}/.test(password), text: "같은 문자 4번 이상 연속 금지" },
    ];
}

export function PasswordChecklist({ password, email }: { password: string; email: string }) {
    return (
        <ul className="tiny" style={{ listStyle: "none", padding: 0, margin: "6px 0 0" }} aria-label="비밀번호 규칙">
            {passwordRules(password, email).map((rule) => (
                <li key={rule.text} style={{ color: rule.ok ? "var(--color-success)" : "var(--color-neutral)" }}>
                    {rule.ok ? "✓" : "✕"} {rule.text}<span className="sr-only">{rule.ok ? " 충족" : " 미충족"}</span>
                </li>
            ))}
        </ul>
    );
}
