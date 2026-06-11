"""Dijkstra's shortest-path engine.

We build an adjacency list from the active (non-blocked) Edge records, then
run a standard min-heap based Dijkstra. Edge weights are physical distances
in meters.

Complexity: O((V + E) log V) thanks to the priority queue.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from django.db.models import Q

from typing import Dict, Iterable, List, Optional, Set, Tuple

from navigation.models import Edge, Location


# Average walking speed (m/s). 1.2 m/s is about 4.32 km/h.
WALKING_SPEED_MPS = 1.2


class NoPathException(Exception):
    """Raised when no path exists between the requested locations."""


@dataclass
class PathResult:
    """A computed shortest path plus derived stats."""

    locations: List[Location]
    distance: float
    travel_time: float  # seconds


@dataclass
class StepTrace:
    """A single step in the algorithm, used by the visualisation."""

    visited_id: int
    distance: float
    queue_snapshot: List[Tuple[float, int]]
    edge_from: Optional[int]  # id of node we relaxed from, if any
    updated_id: Optional[int]  # id of neighbour whose distance improved


def build_adjacency(
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
) -> Dict[int, List[Tuple[int, float, int]]]:
    """Build adjacency list: {node_id: [(neighbour_id, distance, edge_id)]}.

    Edges are treated as undirected (both directions are inserted) so
    navigation works in either direction.

    Args:
        blocked_edge_ids: Optional iterable of edge ids to treat as blocked
            in addition to those already flagged is_blocked=True in the DB.
        include_db_blocked: When true, persisted is_blocked flags are ignored.
            This supports the frontend's "Avoid blocked roads" toggle.
    """
    blocked: Set[int] = set(blocked_edge_ids or [])
    adjacency: Dict[int, List[Tuple[int, float, int]]] = {}

    edges = Edge.objects.select_related("source", "destination").all()
    for edge in edges:
        if edge.id in blocked or (edge.is_blocked and not include_db_blocked):
            continue
        adjacency.setdefault(edge.source_id, []).append(
            (edge.destination_id, edge.distance, edge.id)
        )
        adjacency.setdefault(edge.destination_id, []).append(
            (edge.source_id, edge.distance, edge.id)
        )
    return adjacency


def dijkstra(
    source_id: int,
    destination_id: int,
    adjacency: Optional[Dict[int, List[Tuple[int, float, int]]]] = None,
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
) -> PathResult:
    """Run Dijkstra from source_id to destination_id.

    Args:
        source_id: pk of the start Location.
        destination_id: pk of the target Location.
        adjacency: optional precomputed graph. Built on demand otherwise.
        blocked_edge_ids: optional extra edge ids to ignore this run.
        include_db_blocked: When true, persisted is_blocked flags are ignored.

    Returns:
        PathResult with ordered location list, total distance (m) and time (s).

    Raises:
        NoPathException: if destination is unreachable.
    """
    if source_id == destination_id:
        location = Location.objects.filter(pk=source_id).first()
        if location is None:
            raise NoPathException(f"Location {source_id} does not exist.")
        return PathResult(locations=[location], distance=0.0, travel_time=0.0)

    if adjacency is None:
        adjacency = build_adjacency(blocked_edge_ids, include_db_blocked)

    if source_id not in adjacency and not _has_node(adjacency, source_id):
        # Source can still be a valid node if it has outgoing edges that
        # were pruned, but if it has zero edges at all the search can't start.
        if not adjacency:
            raise NoPathException("Empty graph.")
        if source_id not in adjacency:
            raise NoPathException(f"Source node {source_id} has no connections.")

    distances: Dict[int, float] = {source_id: 0.0}
    previous: Dict[int, int] = {}
    heap: List[Tuple[float, int]] = [(0.0, source_id)]
    seen: Set[int] = set()

    while heap:
        current_dist, current_id = heapq.heappop(heap)
        if current_id in seen:
            continue
        seen.add(current_id)
        if current_id == destination_id:
            break
        for neighbour_id, weight, _ in adjacency.get(current_id, []):
            new_dist = current_dist + weight
            if new_dist < distances.get(neighbour_id, float("inf")):
                distances[neighbour_id] = new_dist
                previous[neighbour_id] = current_id
                heapq.heappush(heap, (new_dist, neighbour_id))

    if destination_id not in distances:
        raise NoPathException(
            f"No path from {source_id} to {destination_id}."
        )

    # Reconstruct the path by walking the predecessor map backwards.
    path_ids: List[int] = [destination_id]
    while path_ids[-1] != source_id:
        path_ids.append(previous[path_ids[-1]])

    path_ids.reverse()
    locations_by_id = Location.objects.in_bulk(path_ids)
    if len(locations_by_id) != len(path_ids):
        raise NoPathException("Path contains a missing location.")
    locations = [locations_by_id[pid] for pid in path_ids]

    total_distance = distances[destination_id]
    travel_time = total_distance / WALKING_SPEED_MPS
    return PathResult(locations=locations, distance=total_distance, travel_time=travel_time)


def dijkstra_with_trace(
    source_id: int,
    destination_id: int,
    adjacency: Optional[Dict[int, List[Tuple[int, float, int]]]] = None,
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
) -> List[StepTrace]:
    """Run Dijkstra but record each relaxation for the visualiser.

    Returns a list of StepTrace entries in the order the algorithm visits
    nodes. The frontend can replay these to show how Dijkstra "discovers"
    the shortest path step by step.
    """
    if adjacency is None:
        adjacency = build_adjacency(blocked_edge_ids, include_db_blocked)

    distances: Dict[int, float] = {source_id: 0.0}
    previous: Dict[int, int] = {}
    heap: List[Tuple[float, int]] = [(0.0, source_id)]
    visited: Set[int] = set()
    trace: List[StepTrace] = []

    while heap:
        current_dist, current_id = heapq.heappop(heap)
        if current_id in visited:
            continue
        visited.add(current_id)
        queue_snapshot = sorted(heap)
        trace.append(
            StepTrace(
                visited_id=current_id,
                distance=current_dist,
                queue_snapshot=queue_snapshot,
                edge_from=previous.get(current_id),
                updated_id=None,
            )
        )
        if current_id == destination_id:
            break
        for neighbour_id, weight, _ in adjacency.get(current_id, []):
            new_dist = current_dist + weight
            if new_dist < distances.get(neighbour_id, float("inf")):
                distances[neighbour_id] = new_dist
                previous[neighbour_id] = current_id
                heapq.heappush(heap, (new_dist, neighbour_id))
                trace.append(
                    StepTrace(
                        visited_id=current_id,
                        distance=current_dist,
                        queue_snapshot=sorted(heap),
                        edge_from=current_id,
                        updated_id=neighbour_id,
                    )
                )

    return trace


def find_alternative_path(
    source_id: int,
    destination_id: int,
    primary: PathResult,
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
) -> Optional[PathResult]:
    """Find a second-best path by removing one primary edge at a time.

    Each candidate rerun blocks one walkway from the primary route, forcing
    Dijkstra to discover a different route if one exists. The cheapest
    different candidate is returned with its real physical distance.

    Returns None if no alternative exists.
    """
    primary_ids = [loc.id for loc in primary.locations]
    blocked_base: Set[int] = set(blocked_edge_ids or [])
    best: Optional[PathResult] = None

    for left, right in zip(primary_ids, primary_ids[1:]):
        pair_edge_ids = set(
            Edge.objects.filter(
                Q(source_id=left, destination_id=right)
                | Q(source_id=right, destination_id=left)
            ).values_list("id", flat=True)
        )
        if not pair_edge_ids:
            continue

        try:
            candidate = dijkstra(
                source_id,
                destination_id,
                blocked_edge_ids=blocked_base | pair_edge_ids,
                include_db_blocked=include_db_blocked,
            )
        except NoPathException:
            continue

        candidate_ids = [loc.id for loc in candidate.locations]
        if candidate_ids == primary_ids:
            continue
        if best is None or candidate.distance < best.distance:
            best = candidate

    return best


def _has_node(adjacency: Dict[int, List[Tuple[int, float, int]]], node_id: int) -> bool:
    """True if node_id appears anywhere in the adjacency structure."""
    if node_id in adjacency:
        return True
    for neighbours in adjacency.values():
        for nid, _, _ in neighbours:
            if nid == node_id:
                return True
    return False
