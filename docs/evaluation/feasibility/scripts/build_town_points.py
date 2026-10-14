#!/usr/bin/env python3
"""重新產生 onemap/towns.py 的 26 鎮參考點。

只有在 OneMap 的站點資料變動時才需要跑（例如新線通車）。
會把結果印成可以直接貼回 towns.py 的格式。

⚠️ 一定要用 canonical key 精確比對來挑站。用模糊比對（取搜尋第一筆）時，
PASIR RIS 會抓到 PASIR RIS EAST、PUNGGOL 抓到 PUNGGOL COAST、
TAMPINES 抓到 TAMPINES EAST —— 這三個都踩過。
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from onemap import OneMapClient  # noqa: E402
from onemap.config import load_token  # noqa: E402
from onemap.stations import canonical_key, is_station_entry, parse_codes  # noqa: E402

#: HDB 鎮 → 代表該鎮的主要地鐵站查詢詞
TOWN_QUERY = {
    "ANG MO KIO": "ANG MO KIO MRT STATION", "BEDOK": "BEDOK MRT STATION",
    "BISHAN": "BISHAN MRT STATION", "BUKIT BATOK": "BUKIT BATOK MRT STATION",
    "BUKIT MERAH": "REDHILL MRT STATION", "BUKIT PANJANG": "BUKIT PANJANG MRT STATION",
    "BUKIT TIMAH": "BEAUTY WORLD MRT STATION", "CENTRAL AREA": "DHOBY GHAUT MRT STATION",
    "CHOA CHU KANG": "CHOA CHU KANG MRT STATION", "CLEMENTI": "CLEMENTI MRT STATION",
    "GEYLANG": "ALJUNIED MRT STATION", "HOUGANG": "HOUGANG MRT STATION",
    "JURONG EAST": "JURONG EAST MRT STATION", "JURONG WEST": "BOON LAY MRT STATION",
    "KALLANG/WHAMPOA": "BOON KENG MRT STATION", "MARINE PARADE": "MARINE PARADE MRT STATION",
    "PASIR RIS": "PASIR RIS MRT STATION", "PUNGGOL": "PUNGGOL MRT STATION",
    "QUEENSTOWN": "QUEENSTOWN MRT STATION", "SEMBAWANG": "SEMBAWANG MRT STATION",
    "SENGKANG": "SENGKANG MRT STATION", "SERANGOON": "SERANGOON MRT STATION",
    "TAMPINES": "TAMPINES MRT STATION", "TOA PAYOH": "TOA PAYOH MRT STATION",
    "WOODLANDS": "WOODLANDS MRT STATION", "YISHUN": "YISHUN MRT STATION",
}


def main():
    client = OneMapClient(load_token())
    out, fuzzy = {}, []
    for town, query in TOWN_QUERY.items():
        want = canonical_key(query)
        res = client.search(query)
        cands = [r for r in res["results"] if is_station_entry(r.get("SEARCHVAL", ""))]
        exact = [r for r in cands if canonical_key(r["SEARCHVAL"]) == want]
        hit = (exact or cands or res["results"] or [None])[0]
        if hit is None:
            print(f"  ✗ {town}: 查無", file=sys.stderr)
            continue
        if not exact:
            fuzzy.append(town)
        out[town] = {
            "stationKey": canonical_key(hit["SEARCHVAL"]),
            "stationName": hit["SEARCHVAL"],
            "codes": parse_codes(hit["SEARCHVAL"]),
            "lat": round(float(hit["LATITUDE"]), 6),
            "lon": round(float(hit["LONGITUDE"]), 6),
        }
        print(f"  {'✓' if exact else '⚠'} {town:16s} → {out[town]['stationKey']}",
              file=sys.stderr)
    if fuzzy:
        print(f"\n⚠️ 這些鎮只有模糊比對，請人工確認：{fuzzy}", file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
