"""
Turn-by-turn instruction generator for campus navigation.

Converts a path (list of Location objects) into human-readable
step-by-step walking directions.
"""
import math
from typing import List, Optional

from navigation.models import Location


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the bearing from point 1 to point 2.

    Args:
        lat1, lon1: Starting coordinates (degrees).
        lat2, lon2: Ending coordinates (degrees).

    Returns:
        Bearing in degrees (0 = North, 90 = East, 180 = South, 270 = West).
    """
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)

    # Calculate bearing
    y = math.sin(delta_lon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - \
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)

    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def bearing_to_direction(bearing: float) -> str:
    """
    Convert bearing to cardinal direction.

    Args:
        bearing: Bearing in degrees.

    Returns:
        Cardinal direction string (N, NE, E, SE, S, SW, W, NW).
    """
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    index = round(bearing / 45) % 8
    return directions[index]


def bearing_to_turn_instruction(prev_bearing: float, curr_bearing: float) -> str:
    """
    Determine turn instruction based on bearing change.

    Args:
        prev_bearing: Previous segment bearing.
        curr_bearing: Current segment bearing.

    Returns:
        Turn instruction string.
    """
    diff = (curr_bearing - prev_bearing + 360) % 360

    if diff < 22.5 or diff > 337.5:
        return "Continue straight"
    elif diff < 67.5:
        return "Turn slightly right"
    elif diff < 112.5:
        return "Turn right"
    elif diff < 157.5:
        return "Turn sharply right"
    elif diff < 202.5:
        return "Make a U-turn"
    elif diff < 247.5:
        return "Turn sharply left"
    elif diff < 292.5:
        return "Turn left"
    elif diff < 337.5:
        return "Turn slightly left"
    return "Continue straight"


def format_distance(meters: float) -> str:
    """
    Format distance in human-readable form.

    Args:
        meters: Distance in meters.

    Returns:
        Formatted string (e.g., "120 m", "1.2 km").
    """
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{int(round(meters))} m"


def generate_instructions(path: List[Location]) -> List[dict]:
    """
    Generate turn-by-turn instructions from a path.

    Args:
        path: Ordered list of Location objects representing the route.

    Returns:
        List of instruction dictionaries with step number, text, distance, etc.
    """
    if len(path) < 2:
        return [{
            'step': 1,
            'instruction': f"You are already at {path[0].name}.",
            'distance': 0,
            'distance_text': "0 m",
            'location': path[0].to_dict() if path else None,
        }]

    instructions = []
    total_distance = 0.0

    # Start instruction
    instructions.append({
        'step': 1,
        'instruction': f"Start at {path[0].name}",
        'distance': 0,
        'distance_text': "0 m",
        'location': path[0].to_dict(),
        'type': 'start',
    })

    # Calculate bearings for each segment
    bearings = []
    distances = []
    for i in range(len(path) - 1):
        curr = path[i]
        nxt = path[i + 1]
        bearing = calculate_bearing(curr.latitude, curr.longitude,
                                    nxt.latitude, nxt.longitude)
        # Approximate distance using haversine formula
        dist = haversine_distance(curr.latitude, curr.longitude,
                                  nxt.latitude, nxt.longitude)
        bearings.append(bearing)
        distances.append(dist)

    # Generate intermediate instructions
    for i in range(len(path) - 1):
        curr = path[i]
        nxt = path[i + 1]
        dist = distances[i]
        total_distance += dist

        if i == 0:
            # First segment
            direction = bearing_to_direction(bearings[0])
            instruction = f"Walk {format_distance(dist)} {direction.lower()} to {nxt.name}"
            inst_type = 'walk'
        else:
            # Subsequent segments - include turn instruction
            turn = bearing_to_turn_instruction(bearings[i - 1], bearings[i])
            direction = bearing_to_direction(bearings[i])
            instruction = f"{turn}, walk {format_distance(dist)} {direction.lower()} to {nxt.name}"
            inst_type = 'turn'

        instructions.append({
            'step': i + 2,
            'instruction': instruction,
            'distance': dist,
            'distance_text': format_distance(dist),
            'location': nxt.to_dict(),
            'type': inst_type,
        })

    # Final arrival instruction
    instructions.append({
        'step': len(instructions) + 1,
        'instruction': f"You have arrived at {path[-1].name}.",
        'distance': 0,
        'distance_text': "0 m",
        'location': path[-1].to_dict(),
        'type': 'arrival',
    })

    # Add total distance to each instruction for reference
    for inst in instructions:
        inst['total_distance'] = total_distance
        inst['total_distance_text'] = format_distance(total_distance)

    return instructions


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points using Haversine formula.

    Args:
        lat1, lon1: First point coordinates in degrees.
        lat2, lon2: Second point coordinates in degrees.

    Returns:
        Distance in meters.
    """
    R = 6371000  # Earth radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def get_alternative_path(
    path: List[Location],
    graph_engine,
    source_id: int,
    destination_id: int
) -> Optional[List[Location]]:
    """
    Find an alternative path by temporarily blocking edges from the primary path.

    Args:
        path: Primary path (list of Locations).
        graph_engine: GraphEngine instance.
        source_id: Source location ID.
        destination_id: Destination location ID.

    Returns:
        Alternative path as list of Locations, or None if no alternative exists.
    """
    if len(path) < 2:
        return None

    # Import here to avoid circular import
    from navigation.utils.graph import NoPathException

    # Get edges used in primary path
    primary_edges = set()
    for i in range(len(path) - 1):
        edges = graph_engine._adjacency_list.get(path[i].id, [])
        for neighbor, _, edge_id in edges:
            if neighbor == path[i + 1].id:
                primary_edges.add(edge_id)

    # Try finding path with primary edges blocked
    try:
        result = graph_engine.find_shortest_path(
            source_id,
            destination_id,
            blocked_edge_ids=primary_edges
        )
        return result.path
    except NoPathException:
        return None