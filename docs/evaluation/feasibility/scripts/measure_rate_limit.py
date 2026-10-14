#!/usr/bin/env python3
"""限流邊界量測 — 回答評估計畫的 D-E7。

這支的存在理由：早期量測只記了「撞到幾次 429」，那只能證明節流存在，
**無法指出邊界在哪**。短批次再外推成 per-minute 數字也不算數。

做法：在固定長度的觀察視窗內，以目標速率持續送請求，記錄嘗試數、成功數、
429 數、實際達成速率與延遲。回報兩個不同的東西：

  - **最高未被節流的測試速率**（確定的下界）
  - **最低出現節流的測試速率**（確定的上界）

邊界落在兩者之間。如果識別不出來就照實說，不要假裝有精確值。

同時檢查**限流是跨端點共用還是各自獨立**——這會影響 #15 的 worker 要不要
和 `/places` 搶額度。

跑法：
    python3 scripts/measure_rate_limit.py                    # 預設視窗 20s
    python3 scripts/measure_rate_limit.py --window 60        # 更嚴謹但更久
    python3 scripts/measure_rate_limit.py --rates 150 250 300
"""

import argparse
import itertools
import json
import pathlib
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from onemap import OneMapClient, TOWN_COORDS  # noqa: E402
from onemap.config import load_token  # noqa: E402
from onemap.errors import OneMapError, RateLimited  # noqa: E402
from onemap.evidence import EvidenceRecorder  # noqa: E402

SCRIPT_VERSION = "1.2.0"
DEFAULT_RATES = (150, 250, 300, 350, 420)

# ⚠️ 每次請求的參數必須唯一，否則量到的不是限流而是 OneMap 的上游快取。
# v1.0.0 送相同參數，結果 350/min 都不會被節流、routing 延遲只有 117ms
# （非快取時是 861ms）——那是快取命中，不是真的沒有節流。
UNIQUE_QUERIES = [
    "Raffles Place", "Kent Ridge", "Jurong East", "Tampines", "Bishan",
    "Clementi", "Serangoon", "Woodlands", "Bedok", "Yishun", "Punggol",
    "Sengkang", "Hougang", "Queenstown", "Toa Payoh", "Pasir Ris",
    "Bukit Batok", "Choa Chu Kang", "Ang Mo Kio", "Sembawang",
]
TOWN_CYCLE = ["ANG MO KIO", "TAMPINES", "WOODLANDS", "JURONG WEST",
              "CLEMENTI", "YISHUN", "BEDOK", "PUNGGOL", "SENGKANG", "BISHAN"]

#: 平日日期池。v1.1.0 只輪替出發時間，跨視窗還是會撞到同一組參數，
#: routing p50 又掉回 ~130ms（快取命中）而不是未快取的 ~860ms。
WEEKDAYS = ["10-12-2026", "10-13-2026", "10-14-2026", "10-15-2026",
            "10-16-2026", "10-19-2026", "10-20-2026", "10-21-2026"]

_GLOBAL_SEQ = itertools.count()


def unique_route_params():
    """全域唯一的 (town, date, time) 組合，確保永遠不會命中上游快取。"""
    n = next(_GLOBAL_SEQ)
    return {
        "town": TOWN_CYCLE[n % len(TOWN_CYCLE)],
        "date": WEEKDAYS[(n // len(TOWN_CYCLE)) % len(WEEKDAYS)],
        "time_of_day": f"{6 + (n // 60) % 12:02d}:{n % 60:02d}:{n % 60:02d}",
    }


def unique_search_query():
    n = next(_GLOBAL_SEQ)
    return f"{UNIQUE_QUERIES[n % len(UNIQUE_QUERIES)]} {n}"


def _route_unique(client):
    p = unique_route_params()
    return client.route_pt(TOWN_COORDS[p["town"]], "1.2935,103.7846",
                           itineraries=1, date=p["date"],
                           time_of_day=p["time_of_day"])


def concurrency_sweep(client, levels, per_level):
    """併發維度掃描。

    速率掃描到 420/min 都沒被節流，但早先在併發 20 時確實撞到 429，
    所以真正的觸發條件可能是**同時在途的請求數**而不是每分鐘速率。
    這一段分開量這件事：每個併發度盡最大速度送固定筆數。
    """
    print("\n[2b] 併發維度掃描（routing，全速）")
    rows = []
    for level in levels:
        started = time.monotonic()
        results = []
        with ThreadPoolExecutor(max_workers=level) as pool:
            futs = [pool.submit(_safe_route, client) for _ in range(per_level)]
            for f in futs:
                results.append(f.result())
        elapsed = time.monotonic() - started
        codes = [c for c, _ in results]
        lat = sorted(d for c, d in results if c == 200)
        row = {
            "concurrency": level, "requests": per_level,
            "ok": codes.count(200), "rateLimited": codes.count(429),
            "otherErrors": sorted({c for c in codes if c not in (200, 429)}),
            "elapsedSeconds": round(elapsed, 1),
            "achievedPerMin": round(per_level / elapsed * 60, 1),
            "latencyMs": {
                "p50": round(statistics.median(lat) * 1000) if lat else None,
                "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))] * 1000) if lat else None,
                "max": round(lat[-1] * 1000) if lat else None,
            },
            "throttled": codes.count(429) > 0,
        }
        rows.append(row)
        print(f"  併發 {level:>3}  {per_level} 筆  成功 {row['ok']:>3}  "
              f"429 {row['rateLimited']:>3}  達成 {row['achievedPerMin']:>6.1f}/min  "
              f"p50 {row['latencyMs']['p50']}ms  max {row['latencyMs']['max']}ms  "
              f"{'★ 被節流' if row['throttled'] else ''}")
        time.sleep(20)
    return rows


def _safe_route(client):
    t0 = time.perf_counter()
    try:
        _route_unique(client)
        return 200, time.perf_counter() - t0
    except RateLimited:
        return 429, time.perf_counter() - t0
    except OneMapError as exc:
        return (exc.status or 0), time.perf_counter() - t0


def _pacer(target_per_min, window_s, stop_at):
    """產生符合目標速率的送出時刻。"""
    gap = 60.0 / target_per_min
    t = time.monotonic()
    while t < stop_at:
        yield t
        t += gap


def run_window(client, make_call, *, target_per_min, window_s, concurrency, label):
    """在 window_s 秒內以 target_per_min 的速率送請求。"""
    outcomes = []
    lock = threading.Lock()
    started = time.monotonic()
    stop_at = started + window_s

    def fire(args):
        seq, due = args
        delay = due - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        t0 = time.perf_counter()
        try:
            make_call(seq)
            status, elapsed = 200, time.perf_counter() - t0
        except RateLimited:
            status, elapsed = 429, time.perf_counter() - t0
        except OneMapError as exc:
            status, elapsed = (exc.status or 0), time.perf_counter() - t0
        with lock:
            outcomes.append((status, elapsed))

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(fire, (seq, due)) for seq, due
                   in enumerate(_pacer(target_per_min, window_s, stop_at))]
        for f in futures:
            f.result()

    elapsed = time.monotonic() - started
    codes = [c for c, _ in outcomes]
    ok_lat = sorted(d for c, d in outcomes if c == 200)
    row = {
        "label": label,
        "targetPerMin": target_per_min,
        "windowSeconds": round(elapsed, 1),
        "concurrency": concurrency,
        "attempted": len(outcomes),
        "ok": codes.count(200),
        "rateLimited": codes.count(429),
        "otherErrors": sorted({c for c in codes if c not in (200, 429)}),
        "achievedPerMin": round(len(outcomes) / elapsed * 60, 1),
        "successfulPerMin": round(codes.count(200) / elapsed * 60, 1),
        "latencyMs": {
            "p50": round(statistics.median(ok_lat) * 1000) if ok_lat else None,
            "p95": round(ok_lat[min(len(ok_lat) - 1, int(len(ok_lat) * 0.95))] * 1000)
                   if ok_lat else None,
            "max": round(ok_lat[-1] * 1000) if ok_lat else None,
        },
        "throttled": codes.count(429) > 0,
    }
    print(f"  目標 {target_per_min:>4}/min  送出 {row['attempted']:>4}  "
          f"成功 {row['ok']:>4}  429 {row['rateLimited']:>3}  "
          f"達成 {row['achievedPerMin']:>6.1f}/min  "
          f"p50 {row['latencyMs']['p50']}ms  "
          f"{'★ 被節流' if row['throttled'] else '未被節流'}")
    return row


def check_endpoint_sharing(client, token, recorder):
    """限流是跨端點共用還是各自獨立？

    做法：用一條執行緒把 search 灌到高速率，同時另一條慢慢打 route。
    如果 route 也開始 429，代表額度是共用的。
    """
    print("\n[3] 限流是否跨端點共用")
    saturator = OneMapClient(token, calls_per_min=100000, max_attempts=1,
                             recorder=recorder)
    prober = OneMapClient(token, calls_per_min=100000, max_attempts=1,
                          recorder=recorder)
    stop = threading.Event()
    sat_codes = []

    seq_lock = threading.Lock()
    seq_box = [0]

    def next_seq():
        with seq_lock:
            seq_box[0] += 1
            return seq_box[0]

    def saturate():
        while not stop.is_set():
            try:
                saturator.search(unique_search_query())
                sat_codes.append(200)
            except RateLimited:
                sat_codes.append(429)
            except OneMapError:
                sat_codes.append(0)

    threads = [threading.Thread(target=saturate, daemon=True) for _ in range(6)]
    for t in threads:
        t.start()
    time.sleep(2.0)  # 先讓 search 把額度吃滿

    probe = []
    for _ in range(6):
        try:
            _route_unique(prober)
            probe.append(200)
        except RateLimited:
            probe.append(429)
        except OneMapError as exc:
            probe.append(exc.status or 0)
        time.sleep(0.5)

    stop.set()
    for t in threads:
        t.join(timeout=5)

    shared = 429 in probe
    print(f"  search 飽和中：{sat_codes.count(200)} 成功 / "
          f"{sat_codes.count(429)} 被節流")
    print(f"  同時間 route 的結果：{probe}")
    print(f"  → 判定：限流{'**跨端點共用**' if shared else '看起來各端點獨立'}")
    return {
        "saturatorOk": sat_codes.count(200),
        "saturatorThrottled": sat_codes.count(429),
        "probeResults": probe,
        "appearsShared": shared,
        "note": ("search 被節流時 route 也被節流 → 額度共用"
                 if shared else
                 "search 被節流時 route 仍可用 → 兩個端點的額度看起來是分開的"),
    }


def main():
    ap = argparse.ArgumentParser(description="限流邊界量測（D-E7）")
    ap.add_argument("--token")
    ap.add_argument("--window", type=int, default=20, help="每個速率的觀察視窗秒數")
    ap.add_argument("--rates", type=int, nargs="+", default=list(DEFAULT_RATES))
    ap.add_argument("--cooldown", type=int, default=25, help="視窗之間的冷卻秒數")
    ap.add_argument("--concurrency-levels", type=int, nargs="+",
                    default=[1, 3, 5, 10, 20, 30])
    ap.add_argument("--per-level", type=int, default=30)
    ap.add_argument("--skip-sharing", action="store_true")
    ap.add_argument("--out", default="evidence")
    args = ap.parse_args()

    token = load_token(args.token)
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    recorder = EvidenceRecorder(outdir / f"ratelimit_raw_{stamp}.jsonl",
                                token=token, note="rate limit boundary probe")

    probe_client = OneMapClient(token, calls_per_min=100000, max_attempts=1,
                                recorder=recorder)
    print(f"限流邊界量測 v{SCRIPT_VERSION}")
    print(f"  視窗 {args.window}s，冷卻 {args.cooldown}s，速率 {args.rates}")
    print(f"  官方上限：300/min（2025-10-01 起；改制前 250）")
    print(f"  token 剩餘 {probe_client.token_hours_left:.1f} 小時")

    print("\n[1] search 端點（輕量，延遲約 90ms）")
    search_rows = []
    for rate in args.rates:
        search_rows.append(run_window(
            probe_client, lambda seq: probe_client.search(unique_search_query()),
            target_per_min=rate, window_s=args.window,
            concurrency=max(2, round(rate / 60 * 0.3)), label="search"))
        time.sleep(args.cooldown)

    print("\n[2] routing 端點（重，延遲約 860ms）")
    route_rows = []
    route_rates = [r for r in args.rates if r <= 300]
    for rate in route_rates:
        route_rows.append(run_window(
            probe_client,
            lambda seq: _route_unique(probe_client),
            target_per_min=rate, window_s=args.window,
            concurrency=max(3, round(rate / 60 * 1.2)), label="route"))
        time.sleep(args.cooldown)

    conc_rows = concurrency_sweep(probe_client, args.concurrency_levels,
                                  args.per_level)

    sharing = None if args.skip_sharing else check_endpoint_sharing(
        probe_client, token, recorder)

    def boundary(rows):
        clean = [r["targetPerMin"] for r in rows if not r["throttled"]]
        dirty = [r["targetPerMin"] for r in rows if r["throttled"]]
        return {
            "highestRateWithoutThrottling": max(clean) if clean else None,
            "lowestRateWithThrottling": min(dirty) if dirty else None,
            "boundaryIdentified": bool(clean and dirty),
            "interpretation": (
                f"邊界落在 {max(clean)}–{min(dirty)}/min 之間" if clean and dirty
                else f"測到的速率全部未被節流（最高 {max(clean)}/min），邊界高於此" if clean
                else "測到的速率全部被節流，邊界低於最低測試值"),
        }

    report = {
        "script": "measure_rate_limit.py", "version": SCRIPT_VERSION,
        "issue": 3, "answers": "D-E7",
        "runAt": datetime.now(timezone.utc).isoformat(),
        "method": {
            "windowSeconds": args.window,
            "cooldownSeconds": args.cooldown,
            "targetRatesPerMin": args.rates,
            "uniqueParameters": True,
            "note": ("每個速率在固定視窗內持續送請求，記錄嘗試/成功/429。"
                     "每次請求都用唯一參數（輪替查詢詞 / 出發時間），避免量到"
                     "OneMap 上游對相同請求的快取而非真正的節流。"
                     "視窗較短，足以定位短期節流邊界，但不足以證明長時段配額。"),
        },
        "officialLimit": {
            "current": 300, "previous": 250, "changedOn": "2025-10-01",
            "source": "SLA OneMap Workshop 26/08/2025, slide 17",
            "higherLimitContact": "onemap@sla.gov.sg",
        },
        "search": {"windows": search_rows, "boundary": boundary(search_rows)},
        "routing": {"windows": route_rows, "boundary": boundary(route_rows)},
        "concurrencySweep": {
            "rows": conc_rows,
            "highestCleanConcurrency": max(
                [r["concurrency"] for r in conc_rows if not r["throttled"]],
                default=None),
            "lowestThrottledConcurrency": min(
                [r["concurrency"] for r in conc_rows if r["throttled"]],
                default=None),
        },
        "endpointSharing": sharing,
        "rawExchanges": str(recorder.path),
        "exchangeCount": recorder.count,
        "limitations": [
            f"觀察視窗只有 {args.window} 秒，無法證明每小時或每日配額。",
            "量測點在新加坡境外，延遲含跨境 RTT。",
            "單一帳號單一 IP；未測試額度是否以帳號或 IP 為單位。",
            "OneMap 未回傳任何 X-RateLimit-* 或 Retry-After header，"
            "所以剩餘額度無法從回應讀取，只能從行為推論。",
        ],
    }
    path = outdir / f"ratelimit_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("邊界判定")
    print("=" * 70)
    for name, section in (("search", report["search"]), ("routing", report["routing"])):
        b = section["boundary"]
        print(f"  {name:8s} {b['interpretation']}")
    cs = report["concurrencySweep"]
    if cs["lowestThrottledConcurrency"]:
        print(f"  併發     最高無節流 {cs['highestCleanConcurrency']}，"
              f"最低出現節流 {cs['lowestThrottledConcurrency']}")
    else:
        print(f"  併發     測到最高 {cs['highestCleanConcurrency']} 仍無節流")
    print(f"\n原始往返：{recorder.path}（{recorder.count} 筆）")
    print(f"報告：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
