"""Dijkstra's shortest-path engine with a custom Binary Min-Heap Priority Queue.

Features:
- Custom binary min-heap priority queue with O(log V) push and pop operations.
- O((V + E) log V) time complexity.
- Strict edge-weight validation (non-positive weight rejection).
- Disconnected graph and invalid node error handling.
- Turn-by-turn routing metrics (nodes visited, relaxations, execution latency).
- Dynamic edge-blocking support with bidirectional pair synchronization.
- Alternative path discovery via single-edge penalty exclusion.
- Step-by-step trace generation for algorithm visualization.
"""
from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from django.db.models import Q

from navigation.models import Edge, Location


# Average walking speed in meters per second (1.2 m/s ≈ 4.32 km/h).
WALKING_SPEED_MPS = 1.2

# Graph cache versioning to handle dynamic rerouting and edge invalidations cleanly.
_GRAPH_VERSION = 0


def invalidate_graph_cache() -> None:
    """Increment graph version to signal that adjacency cache should be refreshed."""
    global _GRAPH_VERSION
    _GRAPH_VERSION += 1


def get_graph_version() -> int:
    """Return the current graph version number."""
    return _GRAPH_VERSION


class NoPathException(Exception):
    """Raised when no navigable path exists between requested locations."""


class BinaryMinHeap:
    """Array-backed Binary Min-Heap Priority Queue.

    Maintains the min-heap property:
    For index i, left child is 2*i + 1, right child is 2*i + 2, parent is (i - 1) // 2.
    Complexity:
        - push: O(log V)
        - pop:  O(log V)
        - peek: O(1)
        - size: O(1)
    """

    def __init__(self) -> None:
        self._heap: List[Tuple[float, int, Any]] = []
        self.push_count: int = 0
        self.pop_count: int = 0

    def push(self, priority: float, item: int, payload: Any = None) -> None:
        """Insert (priority, item, payload) into heap and sift up."""
        self.push_count += 1
        entry = (priority, item, payload)
        self._heap.append(entry)
        self._sift_up(len(self._heap) - 1)

    def pop(self) -> Tuple[float, int, Any]:
        """Remove and return the entry with minimum priority."""
        if not self._heap:
            raise IndexError("pop from empty BinaryMinHeap")
        self.pop_count += 1
        min_entry = self._heap[0]
        last_entry = self._heap.pop()
        if self._heap:
            self._heap[0] = last_entry
            self._sift_down(0)
        return min_entry

    def peek(self) -> Tuple[float, int, Any]:
        """Return the minimum entry without removing it."""
        if not self._heap:
            raise IndexError("peek from empty BinaryMinHeap")
        return self._heap[0]

    def _sift_up(self, idx: int) -> None:
        item = self._heap[idx]
        while idx > 0:
            parent_idx = (idx - 1) >> 1
            parent = self._heap[parent_idx]
            if item[0] < parent[0]:
                self._heap[idx] = parent
                idx = parent_idx
            else:
                break
        self._heap[idx] = item

    def _sift_down(self, idx: int) -> None:
        size = len(self._heap)
        item = self._heap[idx]
        half_size = size >> 1
        while idx < half_size:
            left_idx = (idx << 1) + 1
            right_idx = left_idx + 1
            best_idx = left_idx
            best_prio = self._heap[left_idx][0]
            if right_idx < size and self._heap[right_idx][0] < best_prio:
                best_idx = right_idx
                best_prio = self._heap[right_idx][0]
            if best_prio < item[0]:
                self._heap[idx] = self._heap[best_idx]
                idx = best_idx
            else:
                break
        self._heap[idx] = item

    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def snapshot(self) -> List[Tuple[float, int]]:
        """Return a sorted snapshot of (distance, node_id) for visualization."""
        return sorted([(entry[0], entry[1]) for entry in self._heap])


@dataclass
class AlgorithmMetrics:
    """Quantitative performance metrics captured during Dijkstra execution."""

    execution_time_ms: float = 0.0
    nodes_visited: int = 0
    edges_examined: int = 0
    pq_operations: int = 0
    relaxations: int = 0
    queue_type: str = "BinaryMinHeap"


@dataclass
class PathResult:
    """A computed shortest path plus derived stats and metrics."""

    locations: List[Location]
    distance: float
    travel_time: float  # seconds
    edge_count: int
    metrics: AlgorithmMetrics = field(default_factory=AlgorithmMetrics)


@dataclass
class StepTrace:
    """A single algorithm step for visualization."""

    visited_id: int
    distance: float
    queue_snapshot: List[Tuple[float, int]]
    edge_from: Optional[int]
    updated_id: Optional[int]


def build_adjacency(
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
    map_id: Optional[int] = None,
) -> Dict[int, List[Tuple[int, float, int]]]:
    """Build adjacency list: {node_id: [(neighbour_id, distance, edge_id)]}.

    Validates that edge weights are strictly positive and bidirectional pathways
    are populated accurately.

    Args:
        blocked_edge_ids: Edge IDs to treat as blocked for this request.
        include_db_blocked: If True, ignore Edge.is_blocked in the database.
        map_id: Optional CampusMap ID to filter edges by specific map.

    Returns:
        Dictionary mapping node_id to a list of (neighbor_id, distance, edge_id).
    """
    blocked: Set[int] = set(blocked_edge_ids or [])
    adjacency: Dict[int, List[Tuple[int, float, int]]] = {}

    edges_qs = Edge.objects.select_related("source", "destination")
    if map_id is not None:
        edges_qs = edges_qs.filter(campus_map_id=map_id)
    edges = edges_qs.all()
    for edge in edges:
        if edge.id in blocked or (edge.is_blocked and not include_db_blocked):
            continue

        if edge.distance <= 0:
            raise ValueError(
                f"Edge {edge.id} ({edge.source.name} -> {edge.destination.name}) "
                f"has invalid non-positive distance {edge.distance}."
            )

        adjacency.setdefault(edge.source_id, []).append(
            (edge.destination_id, edge.distance, edge.id)
        )
        # Ensure destination is also in adjacency list even if it has no outgoing edges
        adjacency.setdefault(edge.destination_id, [])

    return adjacency


def dijkstra(
    source_id: int,
    destination_id: int,
    adjacency: Optional[Dict[int, List[Tuple[int, float, int]]]] = None,
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
    use_reference_heapq: bool = False,
    map_id: Optional[int] = None,
) -> PathResult:
    """Compute the shortest path using Dijkstra's algorithm.

    Time Complexity: O((V + E) log V)
    Space Complexity: O(V)

    Args:
        source_id: Starting location primary key.
        destination_id: Destination location primary key.
        adjacency: Optional pre-built adjacency structure.
        blocked_edge_ids: Dynamic edges to ignore for this run.
        include_db_blocked: If True, do not filter out database-blocked edges.
        use_reference_heapq: If True, uses Python's heapq as reference implementation.

    Returns:
        PathResult containing the ordered list of Location models, total distance,
        estimated walking time, edge count, and algorithm metrics.

    Raises:
        ValueError: If source_id or destination_id does not exist.
        NoPathException: If no path exists between the source and destination.
    """
    start_time = time.perf_counter()

    # Validate node existence
    source_loc = Location.objects.filter(pk=source_id).first()
    if source_loc is None:
        raise ValueError(f"Source location with ID {source_id} does not exist.")

    dest_loc = Location.objects.filter(pk=destination_id).first()
    if dest_loc is None:
        raise ValueError(f"Destination location with ID {destination_id} does not exist.")

    # Trivial case: source == destination
    if source_id == destination_id:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return PathResult(
            locations=[source_loc],
            distance=0.0,
            travel_time=0.0,
            edge_count=0,
            metrics=AlgorithmMetrics(
                execution_time_ms=elapsed_ms,
                nodes_visited=1,
                edges_examined=0,
                pq_operations=0,
                relaxations=0,
                queue_type="ReferenceHeapq" if use_reference_heapq else "BinaryMinHeap",
            ),
        )

    if adjacency is None:
        adjacency = build_adjacency(blocked_edge_ids, include_db_blocked, map_id=map_id)

    if not adjacency:
        raise NoPathException(
            "No campus map data is available yet. Please contact the campus administrator."
        )

    if source_id not in adjacency or not adjacency.get(source_id):
        # Check if source has any connections at all
        has_conn = any(
            any(nbr == source_id for nbr, _, _ in nbrs)
            for nbrs in adjacency.values()
        )
        if not has_conn:
            raise NoPathException(f"Location '{source_loc.name}' has no active pathways.")

    distances: Dict[int, float] = {source_id: 0.0}
    previous: Dict[int, int] = {}
    visited: Set[int] = set()

    nodes_visited = 0
    edges_examined = 0
    relaxations = 0

    if use_reference_heapq:
        # Standard library heapq implementation for benchmark comparison
        heap: List[Tuple[float, int]] = [(0.0, source_id)]
        pq_ops = 1

        while heap:
            curr_dist, curr_id = heapq.heappop(heap)
            pq_ops += 1

            if curr_id in visited:
                continue
            visited.add(curr_id)
            nodes_visited += 1

            if curr_id == destination_id:
                break

            if curr_dist > distances.get(curr_id, float("inf")):
                continue

            for nbr_id, weight, _ in adjacency.get(curr_id, []):
                edges_examined += 1
                new_dist = curr_dist + weight
                if new_dist < distances.get(nbr_id, float("inf")):
                    distances[nbr_id] = new_dist
                    previous[nbr_id] = curr_id
                    heapq.heappush(heap, (new_dist, nbr_id))
                    pq_ops += 1
                    relaxations += 1
    else:
        # Custom BinaryMinHeap implementation
        pq = BinaryMinHeap()
        pq.push(0.0, source_id)

        while not pq.is_empty():
            curr_dist, curr_id, _ = pq.pop()

            if curr_id in visited:
                continue
            visited.add(curr_id)
            nodes_visited += 1

            if curr_id == destination_id:
                break

            if curr_dist > distances.get(curr_id, float("inf")):
                continue

            for nbr_id, weight, _ in adjacency.get(curr_id, []):
                edges_examined += 1
                new_dist = curr_dist + weight
                if new_dist < distances.get(nbr_id, float("inf")):
                    distances[nbr_id] = new_dist
                    previous[nbr_id] = curr_id
                    pq.push(new_dist, nbr_id)
                    relaxations += 1

        pq_ops = pq.push_count + pq.pop_count

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    if destination_id not in distances or destination_id not in visited:
        raise NoPathException(
            f"No navigable path exists between '{source_loc.name}' and '{dest_loc.name}'."
        )

    # Reconstruct shortest path backwards from destination
    path_ids: List[int] = [destination_id]
    curr = destination_id
    while curr != source_id:
        curr = previous[curr]
        path_ids.append(curr)
    path_ids.reverse()

    loc_map = Location.objects.in_bulk(path_ids)
    if len(loc_map) != len(path_ids):
        raise NoPathException("Computed path references a non-existent location.")

    ordered_locations = [loc_map[pid] for pid in path_ids]
    total_distance = distances[destination_id]
    travel_time = total_distance / WALKING_SPEED_MPS
    edge_count = len(ordered_locations) - 1

    return PathResult(
        locations=ordered_locations,
        distance=round(total_distance, 2),
        travel_time=round(travel_time, 1),
        edge_count=edge_count,
        metrics=AlgorithmMetrics(
            execution_time_ms=round(elapsed_ms, 3),
            nodes_visited=nodes_visited,
            edges_examined=edges_examined,
            pq_operations=pq_ops,
            relaxations=relaxations,
            queue_type="ReferenceHeapq" if use_reference_heapq else "BinaryMinHeap",
        ),
    )


def dijkstra_with_trace(
    source_id: int,
    destination_id: int,
    adjacency: Optional[Dict[int, List[Tuple[int, float, int]]]] = None,
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
    map_id: Optional[int] = None,
) -> List[StepTrace]:
    """Execute Dijkstra while capturing priority queue snapshots for UI visualization."""
    if adjacency is None:
        adjacency = build_adjacency(blocked_edge_ids, include_db_blocked, map_id=map_id)

    distances: Dict[int, float] = {source_id: 0.0}
    previous: Dict[int, int] = {}
    pq = BinaryMinHeap()
    pq.push(0.0, source_id)
    visited: Set[int] = set()
    trace: List[StepTrace] = []

    while not pq.is_empty():
        curr_dist, curr_id, _ = pq.pop()
        if curr_id in visited:
            continue
        visited.add(curr_id)

        trace.append(
            StepTrace(
                visited_id=curr_id,
                distance=curr_dist,
                queue_snapshot=pq.snapshot(),
                edge_from=previous.get(curr_id),
                updated_id=None,
            )
        )

        if curr_id == destination_id:
            break

        for nbr_id, weight, _ in adjacency.get(curr_id, []):
            new_dist = curr_dist + weight
            if new_dist < distances.get(nbr_id, float("inf")):
                distances[nbr_id] = new_dist
                previous[nbr_id] = curr_id
                pq.push(new_dist, nbr_id)
                trace.append(
                    StepTrace(
                        visited_id=curr_id,
                        distance=curr_dist,
                        queue_snapshot=pq.snapshot(),
                        edge_from=curr_id,
                        updated_id=nbr_id,
                    )
                )

    return trace


def find_alternative_path(
    source_id: int,
    destination_id: int,
    primary: PathResult,
    blocked_edge_ids: Optional[Iterable[int]] = None,
    include_db_blocked: bool = False,
    map_id: Optional[int] = None,
) -> Optional[PathResult]:
    """Find a viable alternative path diverging from the primary shortest path.

    Systematically penalizes / removes primary path edges one at a time and
    identifies the shortest valid alternative route if one exists.
    """
    if len(primary.locations) < 2:
        return None

    primary_ids = [loc.id for loc in primary.locations]
    blocked_base = set(blocked_edge_ids or [])
    best_candidate: Optional[PathResult] = None

    for left, right in zip(primary_ids, primary_ids[1:]):
        edge_qs = Edge.objects.filter(
            Q(source_id=left, destination_id=right)
            | Q(source_id=right, destination_id=left)
        )
        if map_id is not None:
            edge_qs = edge_qs.filter(campus_map_id=map_id)
        edge_ids = set(edge_qs.values_list("id", flat=True))
        if not edge_ids:
            continue

        try:
            candidate = dijkstra(
                source_id,
                destination_id,
                blocked_edge_ids=blocked_base | edge_ids,
                include_db_blocked=include_db_blocked,
                map_id=map_id,
            )
        except (NoPathException, ValueError):
            continue

        candidate_ids = [loc.id for loc in candidate.locations]
        if candidate_ids == primary_ids:
            continue

        if best_candidate is None or candidate.distance < best_candidate.distance:
            best_candidate = candidate

    return best_candidate
