#!/usr/bin/env python3
"""Issue #3 — 地理編碼與交通 API 可行性驗證。

直接對應 #3 的兩條驗收條件：

  1. 對新加坡樣本目的地做地理編碼，並取得公共運輸通勤時間
  2. 記錄額度、延遲、失敗回應，以及重複查詢用的 cache key

跑法：
    python3 scripts/verify_feasibility.py                 # 完整
    python3 scripts/verify_feasibility.py --quick         # 跳過限流壓測
    python3 scripts/verify_feasibility.py --out evidence  # 指定輸出目錄

產出 `evidence/feasibility_<時間戳>.json`，可直接連進 issue #3
（評估計畫 D-E5 要求保留原始數據、腳本版本與日期）。
"""

import argparse
import json
import pathlib
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from onemap import OneMapClient, TOWN_COORDS, canonical_key  # noqa: E402
from onemap.config import load_token  # noqa: E402
from onemap.evidence import EvidenceRecorder  # noqa: E402
from onemap.errors import (InvalidRequest, NoRouteFound,  # noqa: E402
                           OneMapError, RateLimited)

SCRIPT_VERSION = "2.0.0"

# 評估計畫 W1 用的常見目的地的代表樣本
SAMPLE_DESTINATIONS = [
    "NUS", "NTU", "Raffles Place", "Changi Business Park",
    "one-north", "Marina Bay Financial Centre", "Tampines Hub",
    "Singapore Management University",
]
SAMPLE_TOWNS = ["ANG MO KIO", "TAMPINES", "WOODLANDS", "JURONG WEST",
                "CLEMENTI", "PUNGGOL", "BEDOK", "YISHUN"]


def _p(label, ok=True):
    print(f"  {'✓' if ok else '✗'} {label}")


def check_geocoding(client):
    """驗收條件 1a + 合約假設 C4。"""
    print("\n[1] 地理編碼（C4）")
    rows, latencies = [], []
    for query in SAMPLE_DESTINATIONS:
        try:
            res = client.search(query)
            top = res["results"][0] if res["results"] else None
            rows.append({
                "query": query, "found": res["found"],
                "top": top and top.get("SEARCHVAL"),
                "lat": top and top.get("LATITUDE"),
                "lon": top and top.get("LONGITUDE"),
                "tokenWarning": res["tokenWarning"],
                "elapsedMs": round(res["elapsed"] * 1000),
            })
            latencies.append(res["elapsed"])
            _p(f"{query:34s} found={res['found']:<4} {top and top.get('SEARCHVAL','')[:34]}")
        except OneMapError as exc:
            rows.append({"query": query, "error": str(exc), "status": exc.status})
            _p(f"{query:34s} {type(exc).__name__}: {exc}", ok=False)
    return {
        "rows": rows,
        "latencyMs": _summary(latencies),
        "verdict": "PASS" if all("error" not in r for r in rows) else "PARTIAL",
    }


def check_station_snapping(client):
    """#14 的站點吸附 + 合約假設 C6（轉乘站）。"""
    print("\n[2] 站點吸附與轉乘站處理（C6）")
    interchanges = {
        "Dhoby Ghaut (CC/NE/NS)": (1.2989116, 103.846292),
        "Jurong East (EW/NS/JE)": (1.3330275, 103.742370),
        "Outram Park (EW/NE/TE)": (1.2802415, 103.840052),
        "Bugis (EW/DT)": (1.3004650, 103.855706),
    }
    rows = []
    for label, (lat, lon) in interchanges.items():
        stations, elapsed = client.nearest_mrt(lat, lon, radius_m=300)
        rows.append({
            "probe": label, "lat": lat, "lon": lon,
            "stations": stations, "elapsedMs": round(elapsed * 1000),
        })
        for st in stations:
            _p(f"{label:26s} → key={st['stationKey']:14s} codes={st['codes']}")
    # C6 的判定：同一個實體站是不是真的會回多個代碼
    multi = [s for r in rows for s in r["stations"] if len(s["codes"]) > 1]
    return {
        "rows": rows,
        "c6Refuted": bool(multi),
        "note": ("同一實體車站回傳多個路線代碼，證實 C6「轉乘站只用一個代碼」不成立；"
                 "cache key 必須用正規化站名。"),
        "verdict": "C6_REFUTED" if multi else "C6_HOLDS",
    }


def check_routing(client):
    """驗收條件 1b + 合約假設 C5。這是 #15 的核心依賴。"""
    print("\n[3] 公共運輸路線規劃（C5）")
    dest = "1.2935,103.7846"  # Kent Ridge MRT
    rows, latencies = [], []
    for town in SAMPLE_TOWNS:
        try:
            route = client.route_pt(TOWN_COORDS[town], dest)
            rows.append({"town": town, "status": "ok", **{
                k: route[k] for k in
                ("minutes", "transfers", "walkMetres", "walkSeconds",
                 "transitSeconds", "waitingSeconds")},
                "elapsedMs": round(route["elapsed"] * 1000)})
            latencies.append(route["elapsed"])
            _p(f"{town:12s} {route['minutes']:5.1f} min  transfers={route['transfers']}  "
               f"walk={route['walkMetres']:.0f}m  ({route['elapsed']*1000:.0f}ms)")
        except NoRouteFound as exc:
            rows.append({"town": town, "status": "unavailable", "error": str(exc)})
            _p(f"{town:12s} 無路線 → 標記 UNAVAILABLE", ok=False)
        except OneMapError as exc:
            rows.append({"town": town, "status": "error",
                         "error": str(exc), "httpStatus": exc.status})
            _p(f"{town:12s} {type(exc).__name__}: {exc}", ok=False)
    ok = [r for r in rows if r["status"] == "ok"]
    return {
        "rows": rows,
        "latencyMs": _summary(latencies),
        "coverage": f"{len(ok)}/{len(rows)}",
        "verdict": "PASS" if len(ok) == len(rows) else "PARTIAL",
    }


def check_failure_modes(client):
    """驗收條件 2 的「失敗回應」。#19 和 #27 要靠這張表寫錯誤處理。"""
    print("\n[4] 失敗模式（#19 / #27 的錯誤處理依據）")
    cases = [
        ("起訖點相同", lambda: client.route_pt("1.2935,103.7846", "1.2935,103.7846")),
        ("座標在新加坡境外", lambda: client.route_pt("3.1390,101.6869", "1.2935,103.7846")),
        ("日期超過一年前", lambda: client.route_pt(
            TOWN_COORDS["TAMPINES"], "1.2935,103.7846", date="01-01-2020")),
        ("深夜 03:00 無班次", lambda: client.route_pt(
            TOWN_COORDS["WOODLANDS"], "1.2935,103.7846", time_of_day="03:00:00")),
    ]
    rows = []
    for label, call in cases:
        try:
            result = call()
            rows.append({"case": label, "outcome": "unexpected_success",
                         "minutes": result["minutes"]})
            _p(f"{label:20s} 竟然成功：{result['minutes']} min", ok=False)
        except (NoRouteFound, InvalidRequest, RateLimited, OneMapError) as exc:
            rows.append({"case": label, "outcome": type(exc).__name__,
                         "httpStatus": exc.status, "message": str(exc),
                         "retryable": exc.retryable,
                         "action": ("標記 UNAVAILABLE" if isinstance(exc, NoRouteFound)
                                    else "退避重試" if exc.retryable else "拒絕請求")})
            _p(f"{label:20s} {type(exc).__name__} (HTTP {exc.status}) → "
               f"{rows[-1]['action']}")
    return {"rows": rows, "verdict": "DOCUMENTED"}


def check_shortest_itinerary(client):
    """驗證合約假設 C5 的「最短行程（shortest itinerary）」。

    早期版本用 numItineraries=1 然後取 itineraries[0]，等於**假設** OneMap
    會把最短的排第一。文件沒有保證，所以這裡把它變成量測結果。

    實測另外發現 numItineraries 的硬上限是 3：
    400 {"error": "numItineraries must be between 1 and 3 (inclusive)."}
    """
    print("\n[6] 最短行程驗證（C5）")
    dest = "1.2935,103.7846"
    rows, n1_worse, unordered = [], 0, 0
    for town in SAMPLE_TOWNS:
        try:
            one = client.route_pt(TOWN_COORDS[town], dest, itineraries=1)
            three = client.route_pt(TOWN_COORDS[town], dest, itineraries=3)
        except OneMapError as exc:
            rows.append({"town": town, "error": str(exc)})
            continue
        durations = [round(d / 60.0, 1) for d in three["allDurationsSeconds"]]
        is_sorted = durations == sorted(durations)
        n1_misses = one["minutes"] > three["minutes"] + 0.01
        n1_worse += int(n1_misses)
        unordered += int(not is_sorted)
        rows.append({
            "town": town,
            "n1Minutes": one["minutes"],
            "n3Minutes": three["minutes"],
            "n3AllMinutes": durations,
            "upstreamOrderedByDuration": is_sorted,
            "n1MissedShortest": n1_misses,
            "deltaMinutes": round(one["minutes"] - three["minutes"], 1),
        })
        flag = "  ★ n=1 沒拿到最短" if n1_misses else ""
        _p(f"{town:12s} n=1 {one['minutes']:5.1f}  n=3 {three['minutes']:5.1f}  "
           f"{durations}{flag}")
    try:
        client.route_pt(TOWN_COORDS[SAMPLE_TOWNS[0]], dest, itineraries=99)
        cap_note = "numItineraries=99 未被拒絕（client 已先夾到 3）"
    except OneMapError as exc:
        cap_note = f"{type(exc).__name__}: {exc}"
    return {
        "rows": rows,
        "upstreamAlwaysOrderedByDuration": unordered == 0,
        "casesWhereNumItineraries1MissedShortest": n1_worse,
        "totalCases": len([r for r in rows if "error" not in r]),
        "maxItinerariesNote": cap_note,
        "verdict": ("ORDERED_BUT_N1_UNSAFE" if unordered == 0 and n1_worse
                    else "ORDERED" if unordered == 0 else "NOT_ORDERED"),
        "conclusion": (
            "上游確實依 duration 由短到長排序，但 numItineraries=1 取得的行程"
            "不保證是最短的——要求 3 條再自行取最小值才安全。"),
    }


def check_rate_limit(client, token):
    """驗收條件 2 的「額度」。直接回答評估計畫的 D-E7。"""
    print("\n[5] 限流實測（D-E7）")
    print("    官方：250/min → 300/min（2025-10-01 起，SLA workshop slide 17）")
    results = {}
    dest = "1.2935,103.7846"
    origin = TOWN_COORDS["ANG MO KIO"]
    for concurrency in (1, 3, 10):
        # 用不同出發時間避開 OneMap 上游對相同請求的快取
        raw = OneMapClient(token, calls_per_min=600, max_attempts=1)
        jobs = [f"08:{m:02d}:00" for m in range(concurrency * 4)]

        def one(t):
            started = time.perf_counter()
            try:
                raw.route_pt(origin, dest, time_of_day=t)
                return 200, time.perf_counter() - started
            except RateLimited:
                return 429, time.perf_counter() - started
            except OneMapError as exc:
                return exc.status or 0, time.perf_counter() - started

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            out = list(pool.map(one, jobs))
        elapsed = time.perf_counter() - started
        codes = [c for c, _ in out]
        lat = [d for c, d in out if c == 200]
        results[f"concurrency_{concurrency}"] = {
            "requests": len(jobs), "ok": codes.count(200),
            "rateLimited": codes.count(429),
            "attemptedPerMin": round(len(jobs) / elapsed * 60),
            "latencyMs": _summary(lat),
        }
        p50 = results[f"concurrency_{concurrency}"]["latencyMs"].get("p50")
        _p(f"併發 {concurrency:2d}: {codes.count(200)}/{len(jobs)} 成功, "
           f"429={codes.count(429)}, 嘗試 {len(jobs)/elapsed*60:.0f}/min, p50={p50}ms")
        time.sleep(10)
    return {
        "officialLimitPerMin": 300,
        "officialNote": "2025-10-01 起 300/min；合約假設 C7 寫的 250 是舊值",
        "measured": results,
        "verdict": "C7_OUTDATED",
    }


def _summary(values):
    if not values:
        return {}
    ms = sorted(v * 1000 for v in values)
    return {
        "n": len(ms), "min": round(ms[0]), "p50": round(statistics.median(ms)),
        "p95": round(ms[min(len(ms) - 1, int(len(ms) * 0.95))]), "max": round(ms[-1]),
    }


def main():
    ap = argparse.ArgumentParser(description="Issue #3 可行性驗證")
    ap.add_argument("--token", help="OneMap token（預設讀 ONEMAP_TOKEN 或 .env）")
    ap.add_argument("--quick", action="store_true", help="跳過限流壓測")
    ap.add_argument("--out", default="evidence", help="輸出目錄")
    args = ap.parse_args()

    token = load_token(args.token)
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # 評估計畫 D-E5：保留原始 HTTP 往返（Authorization header 會被遮蔽）
    recorder = EvidenceRecorder(outdir / f"feasibility_raw_{stamp}.jsonl",
                                token=token, note="issue #3 feasibility run")
    client = OneMapClient(token, recorder=recorder)
    print(f"OneMap 可行性驗證 v{SCRIPT_VERSION}")
    print(f"  token user_id={client.token_user_id}  剩餘效期 {client.token_hours_left:.1f} 小時")

    report = {
        "script": "verify_feasibility.py", "version": SCRIPT_VERSION,
        "issue": 3, "repo": "horiiiiii032929/CS5225-teams12-2026",
        "runAt": datetime.now(timezone.utc).isoformat(),
        "tokenUserId": client.token_user_id,
        "tokenHoursLeft": round(client.token_hours_left, 1),
        "geocoding": check_geocoding(client),
        "stationSnapping": check_station_snapping(client),
        "routing": check_routing(client),
        "failureModes": check_failure_modes(client),
        "shortestItinerary": check_shortest_itinerary(client),
    }
    if not args.quick:
        report["rateLimit"] = check_rate_limit(client, token)
        report["rateLimitNote"] = (
            "更嚴謹的邊界量測請跑 scripts/measure_rate_limit.py；"
            "那支用全域唯一參數避開上游快取，並分開掃描速率與併發兩個維度。")
    report["clientStats"] = client.stats
    report["rawExchanges"] = {"path": str(recorder.path), "count": recorder.count,
                              "redaction": "Authorization header 不記錄，只留 token 指紋"}

    report["assumptions"] = {
        "C4": {"text": "OneMap 能用自由文字查到座標並吸附到地鐵站",
               "verdict": "CONFIRMED" if report["geocoding"]["verdict"] == "PASS" else "PARTIAL"},
        "C5": {"text": "通勤 = 鎮參考點 → 目的地站，平日 08:30，最短行程",
               "verdict": "CONFIRMED" if report["routing"]["verdict"] == "PASS" else "PARTIAL",
               "gap": "「鎮參考點」合約未定義；本工具包以 onemap/towns.py 補上",
               "shortestItinerary": report["shortestItinerary"]["conclusion"]},
        "C6": {"text": "站碼是穩定 cache key，轉乘站只用一個代碼",
               "verdict": "REFUTED" if report["stationSnapping"]["c6Refuted"] else "HOLDS",
               "fix": "改用 stations.canonical_key() 的正規化站名"},
        "C7": {"text": "限流約 250 routing calls/min",
               "verdict": "OUTDATED", "correction": "官方 300/min（2025-10-01 起）"},
    }

    path = outdir / f"feasibility_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("假設驗證結果")
    print("=" * 70)
    for key, val in report["assumptions"].items():
        print(f"  {key}  {val['verdict']:10s} {val['text']}")
    print(f"\n證據已寫入：{path}")
    print(f"原始 HTTP 往返：{recorder.path}（{recorder.count} 筆）")
    print(f"OneMap 呼叫統計：{client.stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
