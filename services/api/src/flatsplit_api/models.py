"""Public response models shared by every API handler."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["flatsplit-api"] = "flatsplit-api"


class Station(BaseModel):
    """Physical-station identity; persistent coordinate pinning is #14 cache work."""

    stationKey: str
    codes: list[str]
    name: str
    lat: float
    lng: float
    snapMetres: int
    snapWarning: bool


class Place(BaseModel):
    placeId: str
    label: str
    address: str
    station: Station


class UnsupportedPlace(BaseModel):
    label: str
    address: str
    code: Literal["STATION_TOO_FAR", "NO_STATION"]
    message: str
    snapMetres: int | None


class PlacesResponse(BaseModel):
    """Selectable candidates, explicit unsupported results, and ambiguity."""

    places: list[Place]
    unsupported: list[UnsupportedPlace]
    ambiguous: bool
