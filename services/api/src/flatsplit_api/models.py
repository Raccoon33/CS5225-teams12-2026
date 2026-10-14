"""Public response models shared by every API handler."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["flatsplit-api"] = "flatsplit-api"


class Station(BaseModel):
    """The MRT station a destination is snapped to.

    `stationId` is provisional while contract assumption C6 is open in #6: one
    physical interchange can return several OneMap ids under the same name, so
    this field is not yet safe to use as a cache key.
    """

    stationId: str
    name: str
    walkMetres: int


class Place(BaseModel):
    placeId: str
    label: str
    address: str
    station: Station


class PlacesResponse(BaseModel):
    """At most five candidates; an empty list means no match."""

    places: list[Place]
