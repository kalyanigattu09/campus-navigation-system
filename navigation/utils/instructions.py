"""Convert a path of Location objects into human-readable turn instructions."""
from __future__ import annotations

import math
from typing import List

from navigation.models import Edge, Location


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compass bearing in degrees (0=N, 90=E, 180=S, 270=W)."""
    d_lng = lng2 - lng1
    if d_lng == 0 and lat2 == lat1:
        return 0.0
    angle = math.degrees(math.atan2(d_lng, lat2 - lat1))
    return (angle + 360) % 360


def _cardinal(bearing: float) -> str:
    """Map a bearing in degrees to a cardinal direction phrase."""
    dirs = [
        (22.5, "north"),
        (67.5, "northeast"),
        (112.5, "east"),
        (157.5, "southeast"),
        (202.5, "south"),
        (247.5, "southwest"),
        (292.5, "west"),
        (337.5, "northwest"),
        (360.0, "north"),
    ]
    for limit, label in dirs:
        if bearing < limit:
            return label
    return "north"


def _turn(prev_bearing: float, new_bearing: float) -> str:
    """Describe the turn between two bearings."""
    diff = (new_bearing - prev_bearing + 540) % 360 - 180
    if abs(diff) < 20:
        return "Continue straight"
    if abs(diff) < 60:
        return "Bear slightly right" if diff > 0 else "Bear slightly left"
    if abs(diff) < 120:
        return "Turn right" if diff > 0 else "Turn left"
    return "Make a sharp right" if diff > 0 else "Make a sharp left"


def build_steps(locations: List[Location]) -> List[dict]:
    """Build turn-by-turn instructions for a path of locations.

    Each step is a dict suitable for JSON serialisation:
        {instruction: str, distance: float, from: str, to: str}
    """
    if not locations:
        return []

    steps: List[dict] = []

    # First step: announce the start.
    first = locations[0]
    steps.append(
        {
            "step": 1,
            "instruction": f"Start at {first.name}.",
            "distance": 0,
            "from": first.name,
            "to": first.name,
            "from_id": first.id,
            "to_id": first.id,
        }
    )

    if len(locations) == 1:
        steps.append(
            {
                "step": 2,
                "instruction": "You have arrived.",
                "distance": 0,
                "from": first.name,
                "to": first.name,
                "from_id": first.id,
                "to_id": first.id,
            }
        )
        return steps

    prev_bearing: float | None = None

    for i in range(1, len(locations)):
        prev = locations[i - 1]
        curr = locations[i]
        edge = (
            Edge.objects.filter(source=prev, destination=curr).first()
            or Edge.objects.filter(source=curr, destination=prev).first()
        )
        distance = edge.distance if edge else 0.0
        bearing = _bearing(prev.latitude, prev.longitude, curr.latitude, curr.longitude)
        cardinal = _cardinal(bearing)

        if prev_bearing is None:
            verb = "Walk"
        else:
            verb = _turn(prev_bearing, bearing)

        if i == len(locations) - 1:
            instruction = f"{verb} {distance:.0f}m {cardinal} to {curr.name}. You have arrived."
        else:
            instruction = f"{verb} {distance:.0f}m {cardinal} toward {curr.name}."

        steps.append(
            {
                "step": i + 1,
                "instruction": instruction,
                "distance": distance,
                "from": prev.name,
                "to": curr.name,
                "from_id": prev.id,
                "to_id": curr.id,
            }
        )
        prev_bearing = bearing

    return steps
