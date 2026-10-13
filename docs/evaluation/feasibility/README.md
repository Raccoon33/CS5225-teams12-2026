# OneMap feasibility evidence (#3)

Raw evidence behind the GO decision in [#3](https://github.com/horiiiiii032929/CS5225-teams12-2026/issues/3), which is the source of record for the conclusions. This directory holds the artifacts so the numbers quoted in #3, #6 and #46 can be checked rather than taken on trust.

**Run date:** 11 October 2026. **Operator:** @lukerspace. **Target:** `https://www.onemap.gov.sg`, measured from outside Singapore.

> Raw files are unedited console output. Their section headings are in the operator's working language (Chinese); the tables below say what each section shows.

## What each file supports

| Claim (as stated in #3)                                                                                           | File                                                    | Section      |
| ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------ |
| Search works untokenised but is throttled — 4 of 10 sample queries resolved (86–110 ms), 6 returned 429           | `raw/2026-10-11/probe_out.txt`                          | A            |
| **429 bodies are HTML, not JSON, when no token is sent** — a bare `json.loads()` on the error path raises         | `raw/2026-10-11/probe_out.txt`                          | A            |
| Search returns HTTP 200 with full results _and_ an `Authentication token missing` error field (grace period)      | `raw/2026-10-11/probe_out.txt`, `sample_ok.json`        | B            |
| Error and boundary shapes for search (empty, 2-char, SQL-injection syntax → 403 WAF)                              | `raw/2026-10-11/probe_out.txt`                          | C            |
| Token-gated endpoints and their failure shapes                                                                    | `raw/2026-10-11/probe_out.txt`                          | D, E         |
| **C6 refuted** — Dhoby Ghaut returns `CC1`, `NS24`, `NE6` with one identical name ~100 m apart                    | `raw/2026-10-11/routing_out.txt`                        | 2            |
| **C6 refuted** — search returns slash-combined (`EW24 / NS1`), split and code-less entries for one station        | `raw/2026-10-11/stations_out.txt`                       | whole file   |
| Town names resolve to blocks, not centroids (ANG MO KIO → "ANG MO KIO 22")                                        | `raw/2026-10-11/stations_out.txt`                       | town section |
| Public-transport routing returns usable itineraries with legs, transfers and walk distance                        | `raw/2026-10-11/routing_out.txt`                        | 3            |
| Routing latency: min 131 ms, p50 861 ms, p95 1226 ms, max 1585 ms (n=10)                                          | `raw/2026-10-11/measure_out.txt`                        | A            |
| 404 on same origin/destination and on a 03:00 departure — must be marked `unavailable`, never 0 minutes           | `raw/2026-10-11/measure2_out.txt`                       | C-重測       |
| 400 on coordinates outside Singapore and on a date more than a year in the past                                   | `raw/2026-10-11/measure_out.txt`                        | C            |
| `numItineraries=1` missed the shortest route in 1 of 8 towns (TAMPINES 58.3 → 56.5 min); ordering was correct 8/8 | `raw/2026-10-11/itin_out.txt`                           | whole file   |
| Untokenised search sustains ~60/min; burst capacity ≈ 1                                                           | `raw/2026-10-11/threshold_out.txt`, `ratelimit_out.txt` | see note 2   |
| 26-town → principal MRT station table, with the `stationKey` normalisation proposed for C6                        | `data/towns.json`                                       | —            |

## Notes and corrections

1. **The rate-limit numbers in `measure_out.txt` §B are wrong and are kept only as the counter-example.** That run reused identical query parameters and reported 3,959 calls/min with routing p50 118 ms. It was measuring OneMap's upstream cache, not the absence of a limit — uncached routing p50 is 861–990 ms in the same file's §A. `measure2_out.txt` §B-重測 is the corrected form (unique parameters per request, concurrency 20: 57×200, 3×429 at an attempted 249 calls/min). **Any load test against OneMap must vary its parameters**, which is why this appears as an addition to D-E1 in #46.
2. **The untokenised sustainable rate was revised after this run.** `ratelimit_out.txt` §3 estimates ~12 req/min from 8 samples at one request per 5 s; `threshold_out.txt` is the better measurement — clean at a 1.00 s interval (61.5/min) and throttled at 0.50 s — so ~60/min with burst 1 is the figure quoted in #3. Burst capacity ≈ 1 is from `ratelimit_out.txt` §2.
3. **Official quota.** 250 calls/min raised to 300 calls/min from 1 October 2025, per the SLA OneMap Workshop deck of 26 August 2025, slide 17. The deck is third-party material marked © Singapore Land Authority and is not redistributed here; it is cited only.
4. **Measurement limits**, to be restated in the report: single account and IP, so per-account versus per-IP is untested; measured from outside Singapore, so `ap-southeast-1` should be faster; OneMap returns no `X-RateLimit-*` headers and no `Retry-After` on any 429 observed, so remaining allowance can only be inferred from behaviour.

## Not in this commit

Stated plainly so the gap is not mistaken for completeness:

- **The 12 October re-run is missing**: `measure_rate_limit.py` (paced fixed-window sweep plus a separate concurrency dimension) and its JSONL archive of 45 + 1,037 HTTP exchanges with redacted authorization headers. The concurrency sweep quoted in #3 and in the proposed D-E7 wording — 0/30 rejections at concurrency 20, 2/30 at 30, achieved rates 26 → 395/min — comes from that run, and the working copy that produced it is no longer available. It has to be re-run or recovered before D-E7's numbers can be checked against raw data.
- **`measure_out.txt`, `measure2_out.txt` and `itin_out.txt` have no script here.** They were produced by inline scripts that were not retained, so these three files do not meet D-E5's "script version" requirement. The four scripts in `scripts/` are complete and re-runnable.
- **The tokenised feasibility run is missing.** #3's acceptance criteria quote 8/8 destinations geocoded, 8/8 town → Kent Ridge routes returned and a search latency table of n=12 (p50 90 ms, p95 120 ms). In the run kept here the sample was throttled after 4 queries because it carried no token, so `probe_out.txt` §F reports n=4 (min 86 ms, p50 90 ms, max 110 ms). The latencies agree; the sample size does not.
- **The 12 October snapping-error table** (ANG MO KIO → NTU, 87.3 min exact versus 59.1 min snapped, 28.2 min maximum error) is also from the missing run. `measure2_out.txt` §D is the earlier attempt, in which two of three destinations were lost to 429s.

## Reproducing

```bash
# No credentials are stored in this tree. Search needs no token; routing does.
export ONEMAP_TOKEN="<token>"          # RS256 JWT, 3-day validity, no auto-renewal
python3 docs/evaluation/feasibility/scripts/probe.py        # feasibility + failure shapes
python3 docs/evaluation/feasibility/scripts/stations.py     # C6: station code representations
python3 docs/evaluation/feasibility/scripts/threshold.py    # untokenised rate threshold
python3 docs/evaluation/feasibility/scripts/ratelimit.py    # burst capacity and recovery
```

`threshold.py` and `ratelimit.py` deliberately drive the API into 429 and take several minutes; they consume shared quota, so do not run them while someone else is testing.
