"""原始 HTTP 請求/回應記錄器。

評估計畫 D-E5 要求保留原始數據。只存「處理過的結果」不夠：審閱時要能自己
檢查真正的回應長什麼樣，包含非 JSON 的失敗回應（429 的 HTML、403 的 WAF 頁）。

每一次嘗試記一行 JSONL：method、URL、query 參數、UTC 時間戳、HTTP 狀態、
content-type、挑選過的回應 header、耗時、原始 body。

**Authorization header 一律不記錄**，只記 token 的 SHA-256 前 12 碼，
讓人能分辨「同一顆 token」但拿不到 token 本身。
"""

import hashlib
import json
import pathlib
import threading
from datetime import datetime, timezone

#: 值得留下來的回應 header。OneMap 實測不給 Retry-After，但還是記著，
#: 因為「沒有這個 header」本身就是要證明的事。
KEEP_HEADERS = (
    "content-type", "content-length", "date", "retry-after",
    "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
    "x-amzn-requestid", "x-amz-apigw-id", "x-amzn-trace-id",
)

MAX_BODY_CHARS = 40000


def token_fingerprint(token):
    """token 的可辨識指紋，但無法還原出 token。"""
    if not token:
        return None
    return hashlib.sha256(token.encode()).hexdigest()[:12]


class EvidenceRecorder:
    """把每次 HTTP 嘗試寫成一行 JSONL。執行緒安全。"""

    def __init__(self, path, *, token=None, note=None):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._n = 0
        self.token_fp = token_fingerprint(token)
        self._write({
            "type": "session",
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "tokenFingerprint": self.token_fp,
            "note": note,
            "redaction": "Authorization header 不記錄；只留 token 的 sha256 前 12 碼",
        })

    def _write(self, obj):
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def record(self, *, method, url, params, status, headers, body,
               elapsed, attempt, error=None):
        """記一次嘗試。body 原封不動存成字串（非 JSON 也照存）。"""
        self._n += 1
        text = body
        if isinstance(text, (bytes, bytearray)):
            text = text.decode("utf-8", "replace")
        # ⚠️ 先判斷是不是 JSON 再截斷，否則大的回應會被誤判成非 JSON。
        body_is_json = _looks_json(text)
        truncated = False
        if isinstance(text, str) and len(text) > MAX_BODY_CHARS:
            text, truncated = text[:MAX_BODY_CHARS], True
        kept = {}
        for key, val in (headers or {}).items():
            if key.lower() in KEEP_HEADERS:
                kept.setdefault(key.lower(), val)
        self._write({
            "type": "exchange",
            "seq": self._n,
            "at": datetime.now(timezone.utc).isoformat(),
            "request": {
                "method": method, "url": url, "params": params,
                "tokenFingerprint": self.token_fp,
                "authorizationHeader": "<redacted>",
            },
            "response": {
                "status": status,
                "headers": kept,
                "contentType": kept.get("content-type"),
                "retryAfterPresent": "retry-after" in kept,
                "bodyIsJson": body_is_json,
                "body": text,
                "bodyTruncated": truncated,
            },
            "elapsedMs": round(elapsed * 1000, 1),
            "attempt": attempt,
            "transportError": error,
        })

    @property
    def count(self):
        return self._n


def _looks_json(text):
    if not isinstance(text, str):
        return False
    stripped = text.lstrip()
    if not stripped.startswith(("{", "[")):
        return False
    try:
        json.loads(text)
        return True
    except ValueError:
        return False
