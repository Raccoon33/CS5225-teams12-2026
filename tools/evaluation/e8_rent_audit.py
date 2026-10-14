#!/usr/bin/env python3
"""Compare HDB detailed rental records with HDB's published quarterly medians."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path


QUARTER = "2026-Q2"
MONTH_FROM = "2026-04"
MONTH_TO = "2026-06"
RECOMMENDATION_TYPES = {"3-ROOM", "4-ROOM", "5-ROOM"}
PUBLISHED_FLAT_TYPES = {
    "1-RM": "1-ROOM",
    "2-RM": "2-ROOM",
    "3-RM": "3-ROOM",
    "4-RM": "4-ROOM",
    "5-RM": "5-ROOM",
    "EXEC": "EXECUTIVE",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--published-medians", type=Path, required=True)
    parser.add_argument("--bootstrap-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_number(value: float | int | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def main() -> None:
    args = parse_args()

    quarterly_rents: dict[tuple[str, str], list[int]] = defaultdict(list)
    towns: set[str] = set()
    flat_types: set[str] = set()
    with args.transactions.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            town = row["town"]
            flat_type = row["flat_type"]
            towns.add(town)
            flat_types.add(flat_type)
            if MONTH_FROM <= row["rent_approval_date"] <= MONTH_TO:
                quarterly_rents[(town, flat_type)].append(int(row["monthly_rent"]))

    published: dict[tuple[str, str], str] = {}
    published_towns: set[str] = set()
    with args.published_medians.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            if row["quarter"] != QUARTER:
                continue
            # The official Q2 2026 CSV contains "QUEENSTOWN " with a trailing
            # space. Strip comparison keys but preserve this fact in the notes.
            town = row["town"].strip()
            flat_type = PUBLISHED_FLAT_TYPES[row["flat_type"]]
            published[(town, flat_type)] = row["median_rent"]
            published_towns.add(town)

    trailing_quality: dict[tuple[str, str], dict[str, str]] = {}
    with args.bootstrap_evidence.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            relative_width = float(row["relative_width"])
            row["quality_status"] = (
                "USABLE" if relative_width <= 0.10 else "LOW_CONFIDENCE"
            )
            trailing_quality[(row["town"], row["flat_type"])] = row

    fieldnames = [
        "quarter",
        "town",
        "flat_type",
        "recommendation_scope",
        "detailed_record_count",
        "computed_median",
        "published_median",
        "published_status",
        "signed_difference",
        "absolute_difference",
        "trailing_12_count",
        "trailing_12_block_count",
        "trailing_12_ci95_low",
        "trailing_12_ci95_high",
        "trailing_12_relative_width",
        "trailing_12_quality_status",
    ]
    output_rows: list[dict[str, str]] = []
    scope_differences: list[float] = []
    scope_percentage_differences: list[float] = []
    scope_statuses: list[str] = []

    for town in sorted(towns):
        for flat_type in sorted(flat_types):
            values = quarterly_rents.get((town, flat_type), [])
            computed_median = statistics.median(values) if values else None
            published_value = published.get((town, flat_type))
            if town not in published_towns:
                published_status = "TOWN_ABSENT"
                published_median = None
            elif published_value is not None and published_value.isdigit():
                published_status = "NUMERIC"
                published_median = int(published_value)
            else:
                published_status = f"NON_NUMERIC:{published_value}"
                published_median = None

            difference = (
                computed_median - published_median
                if computed_median is not None and published_median is not None
                else None
            )
            quality = trailing_quality.get((town, flat_type))
            quality_status = quality["quality_status"] if quality else "MISSING"
            in_scope = flat_type in RECOMMENDATION_TYPES
            if in_scope:
                scope_statuses.append(published_status)
                if difference is not None:
                    scope_differences.append(abs(difference))
                    scope_percentage_differences.append(
                        abs(difference) / published_median
                    )

            output_rows.append(
                {
                    "quarter": QUARTER,
                    "town": town,
                    "flat_type": flat_type,
                    "recommendation_scope": str(in_scope).lower(),
                    "detailed_record_count": str(len(values)),
                    "computed_median": display_number(computed_median),
                    "published_median": display_number(published_median),
                    "published_status": published_status,
                    "signed_difference": display_number(difference),
                    "absolute_difference": display_number(
                        abs(difference) if difference is not None else None
                    ),
                    "trailing_12_count": quality["count"] if quality else "0",
                    "trailing_12_block_count": (
                        quality["block_count"] if quality else "0"
                    ),
                    "trailing_12_ci95_low": quality["ci95_low"] if quality else "",
                    "trailing_12_ci95_high": quality["ci95_high"] if quality else "",
                    "trailing_12_relative_width": (
                        quality["relative_width"] if quality else ""
                    ),
                    "trailing_12_quality_status": quality_status,
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(
            destination, fieldnames=fieldnames, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output_rows)

    exact_matches = sum(value == 0 for value in scope_differences)
    low_confidence = sum(
        row["recommendation_scope"] == "true"
        and row["trailing_12_quality_status"] == "LOW_CONFIDENCE"
        for row in output_rows
    )
    missing = sum(
        row["recommendation_scope"] == "true"
        and row["trailing_12_quality_status"] == "MISSING"
        for row in output_rows
    )
    summary = {
        "auditVersion": 1,
        "quarter": QUARTER,
        "detailedSourceSha256": sha256(args.transactions),
        "publishedMedianSourceSha256": sha256(args.published_medians),
        "townsAudited": len(towns),
        "recommendationScopeGroups": len(towns) * len(RECOMMENDATION_TYPES),
        "publishedNumericGroups": scope_statuses.count("NUMERIC"),
        "publishedNonNumericGroups": sum(
            value.startswith("NON_NUMERIC:") for value in scope_statuses
        ),
        "publishedTownAbsentGroups": scope_statuses.count("TOWN_ABSENT"),
        "comparableGroups": len(scope_differences),
        "exactMatches": exact_matches,
        "nonExactMatches": len(scope_differences) - exact_matches,
        "medianAbsoluteDifferenceSgd": statistics.median(scope_differences),
        "meanAbsoluteDifferenceSgd": round(statistics.mean(scope_differences), 6),
        "maximumAbsoluteDifferenceSgd": max(scope_differences),
        "maximumAbsolutePercentageDifference": round(
            max(scope_percentage_differences), 10
        ),
        "trailing12UsableGroups": (
            len(towns) * len(RECOMMENDATION_TYPES) - low_confidence - missing
        ),
        "trailing12LowConfidenceGroups": low_confidence,
        "trailing12MissingGroups": missing,
    }
    with args.summary_output.open("w", encoding="utf-8") as destination:
        json.dump(summary, destination, indent=2)
        destination.write("\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
