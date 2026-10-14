"""27 個 HDB 鎮的通勤參考點（其中 26 個可路由） — 補上合約假設 C5 缺的那一塊。

## 為什麼需要這個

合約的 C5 假設把通勤定義成「從**該鎮的參考點**到目的地站」，但
`docs/api-contract.md` 和 `docs/backend-design.md` 都沒有定義參考點是什麼，
也沒說從哪裡來。

2026-10-11 實測確認：**直接用鎮名查 OneMap 拿不到鎮中心。** 搜尋結果是
依相關度排序的建築物，不是行政區重心：

    ANG MO KIO  -> found=310, 第一筆 "ANG MO KIO 22"（一棟樓）
    TAMPINES    -> found=623, 第一筆 "TAMPINES 9 BUILDING"
    WOODLANDS   -> found=535, 第一筆 "WOODLANDS 11"

而 OneMap 的行政區端點（popapi）需要 token，且回傳的是行政區（planning area）
不是 HDB 的 town，兩者並不是一對一。

## 這份表怎麼來的

每個鎮取**該鎮的主要地鐵站**當參考點，座標由 `scripts/build_town_points.py`
透過 OneMap 文字搜尋產生，比對時要求 canonical key 完全相等。

⚠️ 一開始用模糊比對時有三個鎮抓錯站（PASIR RIS 抓到 PASIR RIS EAST、
PUNGGOL 抓到 PUNGGOL COAST、TAMPINES 抓到 TAMPINES EAST），所以才加上
精確比對。要重新產生這份表時務必沿用同一套規則。

## 要寫進報告 Limitations 的話

「以單一地鐵站代表整個 HDB 鎮」是刻意的簡化。面積大的鎮（TAMPINES、
JURONG WEST、WOODLANDS）內部不同地點的實際通勤時間會和這個參考點有出入。
這個誤差由 #19 量測（評估實驗 E8）。

生成日期：2026-10-11 · 資料來源：OneMap `/api/common/elastic/search`
"""

TOWN_REFERENCE_POINTS = {
    'ANG MO KIO': {
        "stationKey": 'ANG_MO_KIO',
        "stationName": 'ANG MO KIO MRT STATION',
        "codes": [],
        "lat": 1.369933,
        "lon": 103.849558,
    },
    'BEDOK': {
        "stationKey": 'BEDOK',
        "stationName": 'BEDOK MRT STATION (EW5)',
        "codes": ['EW5'],
        "lat": 1.32398,
        "lon": 103.929984,
    },
    'BISHAN': {
        "stationKey": 'BISHAN',
        "stationName": 'BISHAN MRT STATION',
        "codes": [],
        "lat": 1.351019,
        "lon": 103.850057,
    },
    'BUKIT BATOK': {
        "stationKey": 'BUKIT_BATOK',
        "stationName": 'BUKIT BATOK MRT STATION (NS2)',
        "codes": ['NS2'],
        "lat": 1.349033,
        "lon": 103.749566,
    },
    'BUKIT MERAH': {
        "stationKey": 'REDHILL',
        "stationName": 'REDHILL MRT STATION (EW18)',
        "codes": ['EW18'],
        "lat": 1.289635,
        "lon": 103.816741,
    },
    'BUKIT PANJANG': {
        "stationKey": 'BUKIT_PANJANG',
        "stationName": 'BUKIT PANJANG MRT STATION',
        "codes": [],
        "lat": 1.379561,
        "lon": 103.761189,
    },
    'BUKIT TIMAH': {
        "stationKey": 'BEAUTY_WORLD',
        "stationName": 'BEAUTY WORLD MRT STATION',
        "codes": [],
        "lat": 1.340901,
        "lon": 103.775747,
    },
    'CENTRAL AREA': {
        "stationKey": 'DHOBY_GHAUT',
        "stationName": 'DHOBY GHAUT MRT STATION (CC1)',
        "codes": ['CC1'],
        "lat": 1.298912,
        "lon": 103.846293,
    },
    'CHOA CHU KANG': {
        "stationKey": 'CHOA_CHU_KANG',
        "stationName": 'CHOA CHU KANG MRT STATION (JS1)',
        "codes": ['JS1'],
        "lat": 1.385368,
        "lon": 103.744085,
    },
    'CLEMENTI': {
        "stationKey": 'CLEMENTI',
        "stationName": 'CLEMENTI MRT STATION (EW23)',
        "codes": ['EW23'],
        "lat": 1.315116,
        "lon": 103.765191,
    },
    'GEYLANG': {
        "stationKey": 'ALJUNIED',
        "stationName": 'ALJUNIED MRT STATION (EW9)',
        "codes": ['EW9'],
        "lat": 1.316433,
        "lon": 103.882906,
    },
    'HOUGANG': {
        "stationKey": 'HOUGANG',
        "stationName": 'HOUGANG MRT STATION',
        "codes": [],
        "lat": 1.370335,
        "lon": 103.892262,
    },
    'JURONG EAST': {
        "stationKey": 'JURONG_EAST',
        "stationName": 'JURONG EAST MRT STATION (EW24 / NS1)',
        "codes": ['EW24', 'NS1'],
        "lat": 1.333028,
        "lon": 103.74237,
    },
    'JURONG WEST': {
        "stationKey": 'BOON_LAY',
        "stationName": 'BOON LAY MRT STATION (EW27)',
        "codes": ['EW27'],
        "lat": 1.338604,
        "lon": 103.706065,
    },
    'KALLANG/WHAMPOA': {
        "stationKey": 'BOON_KENG',
        "stationName": 'BOON KENG MRT STATION',
        "codes": [],
        "lat": 1.31994,
        "lon": 103.862053,
    },
    'MARINE PARADE': {
        "stationKey": 'MARINE_PARADE',
        "stationName": 'MARINE PARADE MRT STATION (TE26)',
        "codes": ['TE26'],
        "lat": 1.302612,
        "lon": 103.904983,
    },
    'PASIR RIS': {
        "stationKey": 'PASIR_RIS',
        "stationName": 'PASIR RIS MRT STATION (EW1)',
        "codes": ['EW1'],
        "lat": 1.373043,
        "lon": 103.949285,
    },
    'PUNGGOL': {
        "stationKey": 'PUNGGOL',
        "stationName": 'PUNGGOL MRT STATION (NE17)',
        "codes": ['NE17'],
        "lat": 1.404547,
        "lon": 103.902073,
    },
    'QUEENSTOWN': {
        "stationKey": 'QUEENSTOWN',
        "stationName": 'QUEENSTOWN MRT STATION (EW19)',
        "codes": ['EW19'],
        "lat": 1.294551,
        "lon": 103.806077,
    },
    'SEMBAWANG': {
        "stationKey": 'SEMBAWANG',
        "stationName": 'SEMBAWANG MRT STATION (NS11)',
        "codes": ['NS11'],
        "lat": 1.449051,
        "lon": 103.820046,
    },
    'SENGKANG': {
        "stationKey": 'SENGKANG',
        "stationName": 'SENGKANG MRT STATION (NE16)',
        "codes": ['NE16'],
        "lat": 1.391695,
        "lon": 103.895485,
    },
    'SERANGOON': {
        "stationKey": 'SERANGOON',
        "stationName": 'SERANGOON MRT STATION',
        "codes": [],
        "lat": 1.351048,
        "lon": 103.87107,
    },
    'TAMPINES': {
        "stationKey": 'TAMPINES',
        "stationName": 'TAMPINES MRT STATION (DT32)',
        "codes": ['DT32'],
        "lat": 1.35515,
        "lon": 103.94301,
    },
    'TOA PAYOH': {
        "stationKey": 'TOA_PAYOH',
        "stationName": 'TOA PAYOH MRT STATION (NS19)',
        "codes": ['NS19'],
        "lat": 1.332629,
        "lon": 103.847502,
    },
    'WOODLANDS': {
        "stationKey": 'WOODLANDS',
        "stationName": 'WOODLANDS MRT STATION (NS9)',
        "codes": ['NS9'],
        "lat": 1.43682,
        "lon": 103.786067,
    },
    'TENGAH': {
        "stationKey": 'TENGAH',
        "stationName": 'MRT STATION (JS3)',
        "codes": ['JS3'],
        "lat": 1.366346890987177,
        "lon": 103.7300631359935,
        "routable": False,
    },
    'YISHUN': {
        "stationKey": 'YISHUN',
        "stationName": 'YISHUN MRT STATION (NS13)',
        "codes": ['NS13'],
        "lat": 1.429443,
        "lon": 103.835005,
    },
}


#: 給 OneMap routing 端點用的 "lat,lon" 字串
TOWN_COORDS = {
    town: f"{v['lat']},{v['lon']}" for town, v in TOWN_REFERENCE_POINTS.items()
}

#: HDB 鎮名（大寫，照 HDB 資料集拼法 — 合約假設 C3）。
#: 2026-10-14 更新為 27 個 —— Mani 在 #2 的資料剖析發現 9 月的租金來源有 27 個鎮，
#: 包含 TENGAH（PR #52）。
TOWNS = sorted(TOWN_REFERENCE_POINTS)

#: 可以實際算出通勤路線的鎮（26 個）。
#:
#: TENGAH 不在內：它的參考點只有 Jurong Region Line 的 JS3/JS4，2026-10-14 實測
#: OneMap PT routing 從該座標回 404 NoRouteFound（同時以 BUKIT BATOK 對照，39.8 分
#: 正常回傳），因為 JRL 尚未通車。OneMap 搜尋對它回的 SEARCHVAL 也是
#: 'MRT STATION (JS3)'，沒有鎮名，過不了其他 26 鎮用的精確比對規則。
#:
#: 這個區分有產品意義：TENGAH 存在於租金資料裡，所以搜尋結果必須把它列為
#: ROUTE_UNAVAILABLE，而不是悄悄消失（團隊決議 D06）。
ROUTABLE_TOWNS = sorted(
    t for t, v in TOWN_REFERENCE_POINTS.items() if v.get("routable", True)
)


def coords(town):
    """鎮名 -> "lat,lon"。查不到丟 KeyError，不要默默回 None。"""
    return TOWN_COORDS[town.strip().upper()]
