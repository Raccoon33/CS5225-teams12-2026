#!/usr/bin/env python3
"""Issue #15 — 通勤快取填充 / #3 的離線 fallback 矩陣。

兩個用途：

1. **正常路徑**：預先把 `(鎮 × 目的地站)` 的通勤時間算好，灌進 DynamoDB 的
   Commute item。冷啟動的搜尋就不用等 SQS worker 跑完。
2. **Fallback 路徑**：issue #3 要求準備「bounded fallback」。如果 OneMap 的
   存取出問題，這支產生的 JSON 可以當靜態種子資料載入，`/searches` 的介面
   形狀完全不變，只是資料不是即時算的。

輸出的每一筆都照合約 `docs/api-contract.md` 的 Commute item 欄位：

    pk = COMMUTE#<stationKey>     sk = TOWN#<town>
    status / minutes / transfers / walkMinutes / attempts / computedAt / error

⚠️ 注意 pk 用的是 **stationKey（正規化站名）不是路線代碼** — 原因見
`onemap/stations.py` 的說明（合約假設 C6 實測不成立）。

跑法：
    python3 scripts/seed_commute_cache.py --dests "NUS" "Raffles Place"
    python3 scripts/seed_commute_cache.py --dests-file dests.txt --full
    python3 scripts/seed_commute_cache.py --dests "NUS" --dry-run
"""

import argparse
import json
import pathlib
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from onemap import OneMapClient, TOWNS, TOWN_COORDS  # noqa: E402
from onemap.config import load_token  # noqa: E402
from onemap.errors import NoRouteFound, OneMapError, RateLimited  # noqa: E402

SCRIPT_VERSION = "1.0.0"


def resolve_station(client, query):
    """目的地文字 → 吸附後的地鐵站（stationKey + 座標）。"""
    res = client.search(query)
    if not res["results"]:
        return None
    top = res["results"][0]
    lat, lon = float(top["LATITUDE"]), float(top["LONGITUDE"])
    stations, _ = client.nearest_mrt(lat, lon, radius_m=2000)
    if not stations:
        return None
    st = stations[0]
    return {"query": query, "label": top["SEARCHVAL"], "stationKey": st["stationKey"],
            "codes": st["codes"], "coords": f"{st['lat']},{st['lon']}"}


def build_items(client, towns, stations, *, date, time_of_day):
    """產生 Commute item。失敗的配對也會留下 unavailable 紀錄，不會靜默消失。"""
    items, stats = [], {"ok": 0, "unavailable": 0, "error": 0}
    total = len(towns) * len(stations)
    done = 0
    for st in stations:
        for town in towns:
            done += 1
            attempts, record = 0, None
            while attempts < 3 and record is None:
                attempts += 1
                try:
                    route = client.route_pt(TOWN_COORDS[town], st["coords"],
                                            date=date, time_of_day=time_of_day)
                    record = {
                        "pk": f"COMMUTE#{st['stationKey']}", "sk": f"TOWN#{town}",
                        "status": "ok", "minutes": int(round(route["minutes"])),
                        "transfers": route["transfers"],
                        "walkMinutes": int(round((route["walkSeconds"] or 0) / 60)),
                        "attempts": attempts,
                        "computedAt": datetime.now(timezone.utc).isoformat(),
                        "error": None,
                    }
                    stats["ok"] += 1
                except NoRouteFound as exc:
                    record = {
                        "pk": f"COMMUTE#{st['stationKey']}", "sk": f"TOWN#{town}",
                        "status": "unavailable", "minutes": None, "transfers": None,
                        "walkMinutes": None, "attempts": attempts,
                        "computedAt": datetime.now(timezone.utc).isoformat(),
                        "error": str(exc),
                    }
                    stats["unavailable"] += 1
                except RateLimited:
                    # client 內部已經退避重試過；還是撞到就多等一下再試。
                    time.sleep(2.0 * attempts)
                except OneMapError as exc:
                    record = {
                        "pk": f"COMMUTE#{st['stationKey']}", "sk": f"TOWN#{town}",
                        "status": "unavailable", "minutes": None, "transfers": None,
                        "walkMinutes": None, "attempts": attempts,
                        "computedAt": datetime.now(timezone.utc).isoformat(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    stats["error"] += 1
            if record is None:
                record = {
                    "pk": f"COMMUTE#{st['stationKey']}", "sk": f"TOWN#{town}",
                    "status": "unavailable", "minutes": None, "transfers": None,
                    "walkMinutes": None, "attempts": attempts,
                    "computedAt": datetime.now(timezone.utc).isoformat(),
                    "error": "重試 3 次後仍被限流（實際部署時會進 DLQ）",
                }
                stats["error"] += 1
            items.append(record)
            if done % 10 == 0 or done == total:
                print(f"  {done}/{total}  ok={stats['ok']} "
                      f"unavailable={stats['unavailable']} error={stats['error']}")
    return items, stats


def main():
    ap = argparse.ArgumentParser(description="Issue #15 通勤快取填充 / 離線 fallback")
    ap.add_argument("--token")
    ap.add_argument("--dests", nargs="+", help="目的地文字（可多個）")
    ap.add_argument("--dests-file", help="一行一個目的地的檔案")
    ap.add_argument("--towns", type=int, default=0, help="只取前 N 個鎮（0 = 全部 26）")
    ap.add_argument("--date", default="10-13-2026", help="MM-DD-YYYY，平日")
    ap.add_argument("--time", dest="time_of_day", default="08:30:00")
    ap.add_argument("--dry-run", action="store_true", help="只印預估成本，不呼叫 API")
    ap.add_argument("--out", default="evidence")
    args = ap.parse_args()

    names = list(args.dests or [])
    if args.dests_file:
        names += [l.strip() for l in pathlib.Path(args.dests_file).read_text().splitlines()
                  if l.strip() and not l.startswith("#")]
    if not names:
        ap.error("請用 --dests 或 --dests-file 指定目的地")

    towns = TOWNS[:args.towns] if args.towns else TOWNS
    n_pairs = len(towns) * len(names)
    # 解析每個目的地要 2 次呼叫（search + nearest_mrt）
    n_calls = len(names) * 2 + n_pairs
    print(f"通勤快取填充 v{SCRIPT_VERSION}")
    print(f"  {len(towns)} 鎮 × {len(names)} 目的地 = {n_pairs} 組配對")
    print(f"  預估 OneMap 呼叫 {n_calls} 次 "
          f"→ 以 250/min 計約 {n_calls/250*60:.0f} 秒（官方上限 300/min）")
    if args.dry_run:
        print("  --dry-run：不呼叫 API，結束。")
        return 0

    client = OneMapClient(load_token(args.token))
    print(f"  token 剩餘 {client.token_hours_left:.1f} 小時\n")
    if client.token_hours_left * 3600 < n_calls / 250 * 60:
        print("  ⚠️ token 可能在填充完成前就到期，建議先換新 token")

    print("[1] 解析目的地")
    stations = []
    for name in names:
        st = resolve_station(client, name)
        if st:
            stations.append(st)
            print(f"  ✓ {name[:34]:34s} → {st['stationKey']} {st['codes']}")
        else:
            print(f"  ✗ {name[:34]:34s} 無法吸附到地鐵站")

    print(f"\n[2] 計算 {len(towns)*len(stations)} 組通勤")
    started = time.time()
    items, stats = build_items(client, towns, stations,
                               date=args.date, time_of_day=args.time_of_day)
    elapsed = time.time() - started

    payload = {
        "script": "seed_commute_cache.py", "version": SCRIPT_VERSION,
        "issue": 15, "fallbackFor": 3,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "basis": {"date": args.date, "time": args.time_of_day,
                  "mode": "TRANSIT", "routeType": "pt",
                  "description": "Public transport, weekday 08:30 departure"},
        "cacheKeyNote": ("pk 用正規化站名而非路線代碼；原因見 onemap/stations.py"
                         "（合約假設 C6 實測不成立）"),
        "towns": towns, "destinations": stations,
        "stats": {**stats, "elapsedSeconds": round(elapsed, 1),
                  "pairsPerMinute": round(len(items) / elapsed * 60, 1)},
        "clientStats": client.stats,
        "items": items,
    }
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = outdir / f"commute_seed_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print(f"ok={stats['ok']} unavailable={stats['unavailable']} error={stats['error']}")
    print(f"耗時 {elapsed:.1f}s → {len(items)/elapsed*60:.0f} 組/分鐘")
    print(f"種子資料：{path}")
    print(f"OneMap 呼叫統計：{client.stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
