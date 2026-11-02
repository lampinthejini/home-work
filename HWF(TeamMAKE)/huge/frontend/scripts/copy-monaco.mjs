// 코드 편집기(Monaco)를 CDN 없이 우리 서버에서 내려주도록 public/monaco 로 복사한다 (화면정의서 Tech-xx, 외부 전송 없음)
import { cpSync, existsSync } from "node:fs";

const target = "public/monaco/vs";
if (!existsSync(target)) {
    cpSync("node_modules/monaco-editor/min/vs", target, { recursive: true });
}
