"""OneMap 錯誤分類。

每一種都是 2026-10-11 對 www.onemap.gov.sg 實測到的真實回應形狀，
不是從文件猜的。對應 issue #27 的重試策略與 #19 的 unavailable 標記。
"""


class OneMapError(Exception):
    """所有 OneMap 錯誤的基底。"""

    retryable = False

    def __init__(self, message, *, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


class AuthError(OneMapError):
    """401 {"message":"Unauthorized"} — token 缺少/無效，或端點需要 token。

    不可重試：重試只會再被擋一次。要換成更新 token。
    """


class TokenExpiring(OneMapError):
    """JWT 的 exp 已到或即將到期（本地判斷，不是 API 回應）。

    OneMap token 效期固定 3 天且不會自動續期（官方 workshop slide 7）。
    """


class RateLimited(OneMapError):
    """429。回應形狀有兩種，都實測過：

    - 帶 token：JSON {"message":"Too Many Requests"}
    - 不帶 token：HTML <title>429 Too Many Requests</title>

    兩者都沒有 Retry-After header，所以退避排程要自己算。
    """

    retryable = True


class InvalidRequest(OneMapError):
    """400 {"error": "..."} — 參數錯誤。實測到的訊息：

    - "Coordinates are outside Singapore's valid range."
    - "Date cannot be more than 1 year in the past."

    不可重試：同樣的參數重送還是錯。
    """


class NoRouteFound(OneMapError):
    """404 {"error": "No route found between the specified locations"}

    這是 #19 的核心案例。實測觸發情境：起訖點相同、深夜 03:00 無班次。
    必須標記成 UNAVAILABLE，絕對不能當成 0 分鐘（團隊決議 D06）。
    """


class Blocked(OneMapError):
    """403 — WAF 擋下（實測：查詢字串含 `'; DROP TABLE--` 時）。回應是 HTML。"""


class UpstreamError(OneMapError):
    """5xx 或連線失敗。可重試。"""

    retryable = True
