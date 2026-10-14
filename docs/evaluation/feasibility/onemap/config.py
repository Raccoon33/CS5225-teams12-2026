"""Token 載入。

Token 永遠不進原始碼、不進 git。讀取順序：

1. 環境變數 `ONEMAP_TOKEN`
2. 專案根目錄的 `.env`（已被 .gitignore 排除）

正式部署時 token 放 AWS Secrets Manager（`docs/backend-design.md` 已決定），
這支只服務本機驗證腳本。
"""

import os
import pathlib

ENV_VAR = "ONEMAP_TOKEN"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_token(explicit=None):
    if explicit:
        return explicit.strip()
    value = os.environ.get(ENV_VAR)
    if value:
        return value.strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == ENV_VAR:
                return val.strip().strip('"').strip("'")
    raise SystemExit(
        f"找不到 {ENV_VAR}。\n"
        f"  export {ENV_VAR}='<你的 token>'\n"
        f"或把它寫進 {env_file}（參考 .env.example）。\n"
        f"Token 取得方式：POST https://www.onemap.gov.sg/api/auth/post/getToken\n"
        f"  body: {{\"email\": \"...\", \"password\": \"...\"}}  （效期 3 天）"
    )
