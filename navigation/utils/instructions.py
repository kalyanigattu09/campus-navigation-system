"""Convert a sequence of Location objects into clear, non-technical turn-by-turn navigation instructions."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from navigation.models import Edge, Location


def _vector_bearing(x1: float, y1: float, x2: float, y2: float) -> Optional[float]:
    """Calculate bearing in degrees from (x1, y1) to (x2, y2).

    Returns bearing in [0, 360) where 0=North, 90=East, 180=South, 270=West.
    Returns None if points are collinear or identical.
    """
    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) < 1e-7 and abs(dy) < 1e-7:
        return None
    # math.atan2(dx, dy) produces angle clockwise from north (assuming +y is North, +x is East)
    angle = math.degrees(math.atan2(dx, dy))
    return (angle + 360.0) % 360.0


def _cardinal_direction(bearing: float) -> str:
    """Map bearing degrees to a cardinal direction label."""
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


def _turn_description(prev_bearing: float, curr_bearing: float) -> str:
    """Determine turn phrasing based on angle divergence between segments."""
    diff = (curr_bearing - prev_bearing + 540.0) % 360.0 - 180.0
    abs_diff = abs(diff)

    if abs_diff < 25:
        return "Continue straight"
    elif abs_diff < 70:
        return "Bear slightly right" if diff > 0 else "Bear slightly left"
    elif abs_diff < 125:
        return "Turn right" if diff > 0 else "Turn left"
    else:
        return "Make a sharp right" if diff > 0 else "Make a sharp left"


def build_steps(locations: List[Location]) -> List[Dict[str, Any]]:
    """Generate human-readable, step-by-step navigation instructions.

    Args:
        locations: Ordered list of Location objects representing the path.

    Returns:
        List of instruction dictionaries with step number, text, distance,
        from/to locations, and optional pathway name.
    """
    if not locations:
        return []

    steps: List[Dict[str, Any]] = []
    start = locations[0]

    # Initial departure instruction
    steps.append({
        "step": 1,
        "instruction": f"Start at {start.name}.",
        "distance": 0.0,
        "from": start.name,
        "to": start.name,
        "from_id": start.id,
        "to_id": start.id,
        "path_name": "",
        "action": "start",
    })

    if len(locations) == 1:
        steps.append({
            "step": 2,
            "instruction": f"You are already at {start.name}.",
            "distance": 0.0,
            "from": start.name,
            "to": start.name,
            "from_id": start.id,
            "to_id": start.id,
            "path_name": "",
            "action": "arrive",
        })
        return steps

    prev_bearing: Optional[float] = None

    for i in range(1, len(locations)):
        prev_loc = locations[i - 1]
        curr_loc = locations[i]

        # Retrieve edge connecting previous and current node
        edge = (
            Edge.objects.filter(source=prev_loc, destination=curr_loc).first()
            or Edge.objects.filter(source=curr_loc, destination=prev_loc).first()
        )
        distance = edge.distance if edge else 0.0
        path_name = edge.path_name if (edge and edge.path_name) else ""

        # Determine bearing using real lat/lng if available, falling back to map_x/y
        bearing: Optional[float] = None
        if abs(prev_loc.latitude) > 1e-5 or abs(prev_loc.longitude) > 1e-5:
            bearing = _vector_bearing(
                prev_loc.longitude, prev_loc.latitude, curr_loc.longitude, curr_loc.latitude
            )
        if bearing is None:
            # Fallback to normalized map layout coordinates
            bearing = _vector_bearing(prev_loc.map_x, prev_loc.map_y, curr_loc.map_x, curr_loc.map_y)

        # Build turn or movement phrasing
        path_phrase = f" along {path_name}" if path_name else " along the pathway"

        if bearing is not None:
            cardinal = f" {_cardinal_direction(bearing)}"
            if prev_bearing is None:
                verb = "Walk"
            else:
                verb = _turn_description(prev_bearing, bearing)
        else:
            cardinal = ""
            verb = "Walk" if prev_bearing is None else "Continue"

        is_last = (i == len(locations) - 1)
        if is_last:
            instruction = f"{verb} {distance:.0f}m{cardinal}{path_phrase} to {curr_loc.name}. Arrive at your destination."
            action = "arrive"
        else:
            instruction = f"{verb} {distance:.0f}m{cardinal}{path_phrase} toward {curr_loc.name}."
            action = "walk"

        steps.append({
            "step": i + 1,
            "instruction": instruction,
            "distance": round(distance, 1),
            "from": prev_loc.name,
            "to": curr_loc.name,
            "from_id": prev_loc.id,
            "to_id": curr_loc.id,
            "path_name": path_name,
            "action": action,
        })

        if bearing is not None:
            prev_bearing = bearing

    return steps
