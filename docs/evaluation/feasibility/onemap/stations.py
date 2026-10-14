"""地鐵站的正規化 cache key — 修正合約假設 C6。

## 為什麼需要這個

合約 `docs/api-contract.md` 的假設 C6 寫：
> 站碼（例如 CC24）是穩定的 cache key；轉乘站只用一個代碼

**2026-10-11 實測證明這是錯的。** 對 Dhoby Ghaut 的座標呼叫
`getNearestMrtStops`，回傳三筆**不同 id、相同 name** 的結果：

    [{"id":"CC1",  "name":"DHOBY GHAUT MRT STATION", "lat":1.29886885771, ...},
     {"id":"NS24", "name":"DHOBY GHAUT MRT STATION", "lat":1.29868872292, ...},
     {"id":"NE6",  "name":"DHOBY GHAUT MRT STATION", "lat":1.29962061580, ...}]

文字搜尋端點更混亂，同一批資料有三種格式：
- `JURONG EAST MRT STATION (EW24 / NS1)` — 斜線合併
- `DHOBY GHAUT MRT STATION (CC1)` / `(NE6)` / `(NS24)` — 完全拆開
- `BUGIS MRT STATION` — 根本沒有代碼

若直接用 `id` 當 DynamoDB 的 `pk = COMMUTE#<stationId>`，同一個實體車站
會產生最多 4 組 key：快取命中率（評估實驗 E4 的主要指標）會崩掉，而且
同一組使用者查兩次可能拿到相差 100 公尺起點算出來的不同通勤時間。

## 解法

用 **name** 正規化後當 cache key。實測顯示 `getNearestMrtStops` 的 `name`
對同一個實體站是一致的，所以它是可靠的正規化來源。
"""

import re

_SUFFIX = re.compile(r"\s+MRT\s+STATION\b.*$", re.IGNORECASE)
_PAREN = re.compile(r"\s*\([^)]*\)")
_NONWORD = re.compile(r"[^A-Z0-9]+")

# 路線代碼前綴 → 路線名稱。純粹給人看的，不參與 key 計算。
LINE_NAMES = {
    "NS": "North South", "EW": "East West", "CG": "Changi Airport Branch",
    "NE": "North East", "CC": "Circle", "CE": "Circle Extension",
    "DT": "Downtown", "TE": "Thomson-East Coast", "JE": "Jurong Region",
    "JS": "Jurong Region", "JW": "Jurong Region", "BP": "Bukit Panjang LRT",
    "STC": "Sengkang LRT", "PTC": "Punggol LRT",
}

_CODE = re.compile(r"^([A-Z]{2,3})(\d+)$")


def canonical_key(name):
    """把站名轉成穩定的 cache key。

    >>> canonical_key("DHOBY GHAUT MRT STATION")
    'DHOBY_GHAUT'
    >>> canonical_key("JURONG EAST MRT STATION (EW24 / NS1)")
    'JURONG_EAST'
    >>> canonical_key("Kent Ridge MRT Station (CC24)")
    'KENT_RIDGE'
    >>> canonical_key("BUGIS MRT STATION EXIT A")
    'BUGIS'
    """
    s = (name or "").upper()
    s = _PAREN.sub("", s)
    s = _SUFFIX.sub("", s)
    s = _NONWORD.sub("_", s).strip("_")
    return s


def parse_codes(search_val):
    """從文字搜尋的 SEARCHVAL 取出所有路線代碼。

    >>> parse_codes("JURONG EAST MRT STATION (EW24 / NS1)")
    ['EW24', 'NS1']
    >>> parse_codes("BUGIS MRT STATION")
    []
    """
    inner = re.findall(r"\(([^)]*)\)", search_val or "")
    codes = []
    for group in inner:
        for part in group.split("/"):
            part = part.strip().upper()
            if _CODE.match(part):
                codes.append(part)
    return codes


def is_station_entry(search_val):
    """過濾掉出入口。

    實測：搜尋 `MRT STATION` 回報 found=785，其中大量是 `... EXIT A/B/C`
    而不是車站本身。不過濾的話站點清單會膨脹好幾倍。
    """
    s = (search_val or "").upper()
    return "MRT STATION" in s and " EXIT " not in s


def line_of(code):
    """`CC24` -> `Circle`。未知前綴回傳 None。"""
    m = _CODE.match((code or "").upper())
    return LINE_NAMES.get(m.group(1)) if m else None


def dedupe_stations(entries):
    """把 getNearestMrtStops 的結果依 canonical key 收斂。

    輸入是 [{"id","name","lat","lon","road"}, ...]（可能同站多筆）。
    輸出每個實體站一筆，附上所有路線代碼，座標取第一筆（最近的那個出入口）。
    """
    out = {}
    for e in entries:
        key = canonical_key(e.get("name"))
        if not key:
            continue
        rec = out.setdefault(key, {
            "stationKey": key,
            "name": e.get("name"),
            "codes": [],
            "lat": e.get("lat"),
            "lon": e.get("lon"),
            "road": e.get("road"),
        })
        # ⚠️ `id` 不一定是單一代碼。實測 Jurong East 回傳的 id 是
        # "EW24 / NS1"（斜線合併），Dhoby Ghaut 則是三筆各自單一代碼。
        for code in re.split(r"[/,]", (e.get("id") or "").upper()):
            code = code.strip()
            if code and code not in rec["codes"]:
                rec["codes"].append(code)
    for rec in out.values():
        rec["codes"].sort()
        rec["lines"] = sorted({l for l in (line_of(c) for c in rec["codes"]) if l})
    return list(out.values())
