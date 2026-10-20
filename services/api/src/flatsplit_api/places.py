"""Place and station persistence behind `GET /places` (#14).

`find_places` resolved candidates but wrote nothing, so every preference save
failed with `Place not found or expired.`: `groups.py::_place` reads
`PLACE#<placeId>/META` and the save transaction condition-checks its `ttl`, but
nothing ever created the record they read. This module is that missing write
side. A lookup that cannot be persisted is not a successful lookup, because the
`placeId` it returns cannot be saved.

Two different lifetimes, both from `docs/api-contract.md`:

- `PLACE#<placeId>/META` is a 24-hour lookup cache. Looking the same place up
  again rewrites the record and refreshes the ttl. An older `placeId` is not
  valid for a save and must fail honestly rather than invent a destination.
- `STATION#<stationKey>/META` is the pinned routing coordinate and carries no
  ttl. It is created conditionally, the first writer wins, and every later
  lookup that snaps to that station reuses the winning coordinate.

#3 measured why the station coordinate has to be pinned rather than refreshed:
`getNearestMrtStops` returns one entry per line code for an interchange, in a
varying order, with coordinates up to ~100 m apart (Dhoby Ghaut returns CC1,
NS24 and NE6). If a lookup could overwrite the coordinate, one member would
get different commute minutes on different days, and minutes computed from
different origins would accumulate under a single `COMMUTE#<stationKey>` key,
which is E4's primary metric. Aliases may be merged into an existing record;
the coordinate may not change without an explicit cache refresh.

Because the pinned coordinate can be further from the place than the exit this
lookup happened to return, the 1,000 m selection bound is re-measured after
pinning. A candidate that no longer qualifies moves to `unsupported` with
`STATION_TOO_FAR` instead of being offered as selectable.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from flatsplit_api.errors import ApiError
from flatsplit_api.onemap import (
    MAX_SNAP_METRES,
    SNAP_WARNING_METRES,
    haversine_metres,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table

logger = Logger(child=True)

#: docs/api-contract.md: the Place item expires after 24 hours.
PLACE_TTL_SECONDS = 24 * 60 * 60

_TOO_FAR_MESSAGE = "Choose a nearby MRT station or a more precise address."


def _storable(value: Any) -> Any:
    """DynamoDB rejects floats; JSON conversion keeps coordinate precision."""
    return json.loads(json.dumps(value), parse_float=Decimal)


def _unavailable(action: str, exc: ClientError) -> ApiError:
    logger.warning(
        "Place persistence failed",
        extra={"action": action, "awsCode": exc.response["Error"]["Code"]},
    )
    return ApiError(
        503,
        "SERVICE_UNAVAILABLE",
        "Destination search is unavailable. Try again shortly.",
    )


class PlaceStore:
    """Writes the records `groups.py` reads when a preference is saved."""

    def __init__(
        self, table: Table, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.table = table
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> int:
        return int(self._clock().astimezone(UTC).timestamp())

    def persist(self, found: dict[str, Any]) -> dict[str, Any]:
        """Store every selectable candidate and return the adjusted response."""
        places: list[dict[str, Any]] = []
        unsupported: list[dict[str, Any]] = list(found.get("unsupported") or [])
        for candidate in found.get("places") or []:
            station = self._pinned_station(candidate)
            if station["snapMetres"] > MAX_SNAP_METRES:
                # The pinned coordinate is further away than the exit this
                # lookup returned, so this candidate is no longer selectable.
                unsupported.append(
                    {
                        "label": candidate["label"],
                        "address": candidate["address"],
                        "code": "STATION_TOO_FAR",
                        "message": _TOO_FAR_MESSAGE,
                        "snapMetres": station["snapMetres"],
                    }
                )
                continue
            self._write_place(candidate, station)
            places.append(dict(candidate, station=station))
        return {
            "places": places,
            "unsupported": unsupported,
            "ambiguous": len(places) > 1,
        }

    # ------------------------------------------------------------- stations

    def _pinned_station(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """The station as pinned for this key, re-measured from the place."""
        pinned = self._pin(candidate["station"])
        metres = round(
            haversine_metres(
                candidate["lat"], candidate["lng"], pinned["lat"], pinned["lng"]
            )
        )
        return {
            "stationKey": pinned["stationKey"],
            "codes": pinned["codes"],
            "name": pinned["name"],
            "lat": pinned["lat"],
            "lng": pinned["lng"],
            "snapMetres": metres,
            "snapWarning": metres > SNAP_WARNING_METRES,
        }

    def _pin(self, station: dict[str, Any]) -> dict[str, Any]:
        """Create the station record, or return the winning one unchanged."""
        key = str(station["stationKey"])
        codes = sorted({str(code) for code in station["codes"]})
        candidate = {
            "stationKey": key,
            "codes": codes,
            "name": str(station["name"]),
            "lat": float(station["lat"]),
            "lng": float(station["lng"]),
        }
        item = dict(
            _storable(candidate),
            pk=f"STATION#{key}",
            sk="META",
            pinnedAt=self._clock().astimezone(UTC).isoformat(),
        )
        try:
            self.table.put_item(
                Item=item, ConditionExpression="attribute_not_exists(pk)"
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise _unavailable("pin-station", exc) from exc
            return self._merge_aliases(key, codes)
        return candidate

    def _merge_aliases(self, key: str, codes: list[str]) -> dict[str, Any]:
        """Reuse the pinned record, adding any line codes it does not have yet."""
        try:
            existing: dict[str, Any] | None = self.table.get_item(
                Key={"pk": f"STATION#{key}", "sk": "META"}, ConsistentRead=True
            ).get("Item")
        except ClientError as exc:
            raise _unavailable("read-station", exc) from exc
        if existing is None:
            # Only reachable if the record were deleted between the two calls.
            # STATION# has no ttl, so this is a signal, not an expected state.
            raise ApiError(
                503,
                "SERVICE_UNAVAILABLE",
                "Destination search is unavailable. Try again shortly.",
            )
        pinned_codes = [str(code) for code in existing.get("codes") or []]
        merged = sorted(set(pinned_codes) | set(codes))
        if merged != pinned_codes:
            try:
                self.table.update_item(
                    Key={"pk": f"STATION#{key}", "sk": "META"},
                    UpdateExpression="SET codes = :codes",
                    ConditionExpression="attribute_exists(pk)",
                    ExpressionAttributeValues={":codes": merged},
                )
            except ClientError as exc:
                raise _unavailable("merge-aliases", exc) from exc
        return {
            "stationKey": key,
            "codes": merged,
            "name": str(existing["name"]),
            # The coordinate comes from the winning record, never from this
            # lookup. This is the whole point of the pin.
            "lat": float(existing["lat"]),
            "lng": float(existing["lng"]),
        }

    # ---------------------------------------------------------------- places

    def _write_place(self, candidate: dict[str, Any], station: dict[str, Any]) -> None:
        item = _storable(
            {
                "label": candidate["label"],
                "address": candidate["address"],
                "lat": float(candidate["lat"]),
                "lng": float(candidate["lng"]),
                "station": station,
            }
        )
        try:
            self.table.put_item(
                Item=dict(
                    item,
                    pk=f"PLACE#{candidate['placeId']}",
                    sk="META",
                    ttl=self._now() + PLACE_TTL_SECONDS,
                )
            )
        except ClientError as exc:
            raise _unavailable("write-place", exc) from exc
