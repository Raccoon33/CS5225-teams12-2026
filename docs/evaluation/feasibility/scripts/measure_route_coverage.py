#!/usr/bin/env python3
"""Issue #19 — 路線覆蓋率與「吸附站 vs 精確地址」誤差。

對應 #19 的驗收條件：

  1. 針對代表性的鎮與目的地回報覆蓋率
  2. 缺失路線標記為 unavailable；搜尋誠實降級並可重試

同時產出評估實驗 **E8**（「我們的數字可不可信」）要的證據：
以地鐵站代表目的地，和用精確地址相比差幾分鐘。

跑法：
    python3 scripts/measure_route_coverage.py                  # 預設 8 鎮 × 5 目的地
    python3 scripts/measure_route_coverage.py --full           # 26 鎮 × 全部目的地
    python3 scripts/measure_route_coverage.py --towns 5 --dests 3
"""

import argparse
import json
import math
import pathlib
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from onemap import OneMapClient, TOWNS, TOWN_COORDS  # noqa: E402
from onemap.config import load_token  # noqa: E402
from onemap.errors import NoRouteFound, OneMapError  # noqa: E402

SCRIPT_VERSION = "1.0.0"

# 評估計畫 W1 的「30 個常見目的地」代表樣本
DESTINATIONS = [
    "National University of Singapore",
    "Nanyang Technological University",
    "Raffles Place MRT Station",
    "Changi Business Park",
    "one-north MRT Station",
    "Singapore Management University",
    "Mapletree Business City",
    "Singapore General Hospital",
]


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_destinations(client, names):
    """每個目的地取得「精確座標」和「吸附後的地鐵站座標」。"""
    out = []
    for name in names:
        res = client.search(name)
        if not res["results"]:
            print(f"  ✗ {name}: 查無地點")
            continue
        top = res["results"][0]
        lat, lon = float(top["LATITUDE"]), float(top["LONGITUDE"])
        stations, _ = client.nearest_mrt(lat, lon, radius_m=2000)
        if not stations:
            print(f"  ✗ {name}: 2km 內沒有地鐵站")
            continue
        st = stations[0]
        walk = haversine_m(lat, lon, st["lat"], st["lon"])
        out.append({
            "name": name, "label": top["SEARCHVAL"],
            "exact": f"{lat},{lon}",
            "stationKey": st["stationKey"], "codes": st["codes"],
            "station": f"{st['lat']},{st['lon']}",
            "walkMetres": round(walk),
        })
        print(f"  ✓ {name[:38]:38s} → {st['stationKey']:16s} "
              f"{st['codes']}  直線 {walk:.0f}m")
    return out


def main():
    ap = argparse.ArgumentParser(description="Issue #19 覆蓋率與吸附誤差")
    ap.add_argument("--token")
    ap.add_argument("--towns", type=int, default=8, help="取幾個鎮（--full 時忽略）")
    ap.add_argument("--dests", type=int, default=5, help="取幾個目的地（--full 時忽略）")
    ap.add_argument("--full", action="store_true", help="26 鎮 × 全部目的地")
    ap.add_argument("--out", default="evidence")
    args = ap.parse_args()

    client = OneMapClient(load_token(args.token))
    towns = TOWNS if args.full else TOWNS[:args.towns]
    dest_names = DESTINATIONS if args.full else DESTINATIONS[:args.dests]

    print(f"Issue #19 覆蓋率量測 v{SCRIPT_VERSION}")
    print(f"  {len(towns)} 鎮 × {len(dest_names)} 目的地 = {len(towns)*len(dest_names)} 組配對")
    print(f"  token 剩餘 {client.token_hours_left:.1f} 小時\n")

    print("[1] 解析目的地並吸附到地鐵站")
    dests = resolve_destinations(client, dest_names)

    print(f"\n[2] 計算 {len(towns)*len(dests)} 組通勤（吸附站為終點）")
    pairs, unavailable, errors = [], [], []
    for town in towns:
        for dest in dests:
            try:
                route = client.route_pt(TOWN_COORDS[town], dest["station"])
                pairs.append({
                    "town": town, "destination": dest["name"],
                    "stationKey": dest["stationKey"], "status": "ok",
                    "minutes": route["minutes"], "transfers": route["transfers"],
                    "walkMetres": route["walkMetres"],
                })
            except NoRouteFound as exc:
                pairs.append({"town": town, "destination": dest["name"],
                              "stationKey": dest["stationKey"],
                              "status": "unavailable", "error": str(exc)})
                unavailable.append((town, dest["name"]))
            except OneMapError as exc:
                pairs.append({"town": town, "destination": dest["name"],
                              "stationKey": dest["stationKey"],
                              "status": "error", "error": str(exc),
                              "httpStatus": exc.status})
                errors.append((town, dest["name"], type(exc).__name__))
        ok = sum(1 for p in pairs if p["town"] == town and p["status"] == "ok")
        print(f"  {town:16s} {ok}/{len(dests)} 可達")

    print("\n[3] 吸附站 vs 精確地址的誤差（實驗 E8）")
    deltas = []
    probe_town = towns[0]
    for dest in dests:
        try:
            exact = client.route_pt(TOWN_COORDS[probe_town], dest["exact"])
            snapped = client.route_pt(TOWN_COORDS[probe_town], dest["station"])
            delta = snapped["minutes"] - exact["minutes"]
            deltas.append({
                "destination": dest["name"], "stationKey": dest["stationKey"],
                "exactMinutes": exact["minutes"], "snappedMinutes": snapped["minutes"],
                "deltaMinutes": round(delta, 1),
                "walkMetres": dest["walkMetres"],
            })
            print(f"  {dest['name'][:34]:34s} 精確={exact['minutes']:5.1f}  "
                  f"吸附={snapped['minutes']:5.1f}  誤差={delta:+5.1f} min")
        except OneMapError as exc:
            print(f"  {dest['name'][:34]:34s} {type(exc).__name__}: {exc}")

    total = len(pairs)
    ok_n = sum(1 for p in pairs if p["status"] == "ok")
    abs_deltas = [abs(d["deltaMinutes"]) for d in deltas]
    report = {
        "script": "measure_route_coverage.py", "version": SCRIPT_VERSION,
        "issue": 19, "experiment": "E8",
        "runAt": datetime.now(timezone.utc).isoformat(),
        "towns": towns, "destinations": dests,
        "coverage": {
            "totalPairs": total, "ok": ok_n,
            "unavailable": len(unavailable), "errors": len(errors),
            "coveragePct": round(ok_n / total * 100, 1) if total else 0.0,
            "unavailablePairs": unavailable,
        },
        "snapError": {
            "rows": deltas,
            "medianAbsMinutes": round(statistics.median(abs_deltas), 1) if abs_deltas else None,
            "maxAbsMinutes": round(max(abs_deltas), 1) if abs_deltas else None,
        },
        "pairs": pairs,
        "clientStats": client.stats,
    }
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = outdir / f"coverage_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print(f"覆蓋率：{ok_n}/{total} = {report['coverage']['coveragePct']}%  "
          f"(unavailable={len(unavailable)}, error={len(errors)})")
    if abs_deltas:
        print(f"吸附誤差：中位數 {report['snapError']['medianAbsMinutes']} min，"
              f"最大 {report['snapError']['maxAbsMinutes']} min")
    print(f"證據：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
