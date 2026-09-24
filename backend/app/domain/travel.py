import math
from dataclasses import dataclass
from typing import Protocol

from app.db.enums import Transport

SPEED_KMH: dict[Transport, float] = {
    Transport.WALK: 4.5,
    Transport.TRANSIT: 14.0,
    Transport.SCOOTER: 12.0,
}
DETOUR = 1.4
OVERHEAD_MIN = 3
EARTH_RADIUS_KM = 6371.0

@dataclass(frozen=True)
class Point:
    lat: float
    lon: float

def haversine_km(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))

class TravelEstimator(Protocol):
    def minutes(self, a: Point, b: Point, transport: Transport) -> int: ...

class HaversineEstimator:
    def minutes(self, a: Point, b: Point, transport: Transport) -> int:
        km = haversine_km(a, b) * DETOUR
        return math.ceil(km / SPEED_KMH[transport] * 60) + OVERHEAD_MIN

def default_estimator() -> TravelEstimator:
    return HaversineEstimator()
