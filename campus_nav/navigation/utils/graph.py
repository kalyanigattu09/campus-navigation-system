"""
Dijkstra's Algorithm Implementation for Campus Navigation.

This module provides the core pathfinding engine using Dijkstra's algorithm
with a min-heap priority queue for optimal performance.

Time Complexity: O((V + E) log V) where V = vertices (locations), E = edges (paths)
Space Complexity: O(V) for distances, previous nodes, and the priority queue.

The min-heap (via Python's heapq) ensures we always extract the node with the
minimum tentative distance in O(log V) time, which is the key optimization
over a naive O(V^2) implementation.
"""
import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from navigation.models import Edge, Location


class NoPathException(Exception):
    """Raised when no path exists between source and destination."""
    def __init__(self, source_id: int, destination_id: int):
        self.source_id = source_id
        self.destination_id = destination_id
        super().__init__(
            f"No path exists between location {source_id} and {destination_id}"
        )


@dataclass
class DijkstraResult:
    """Container for Dijkstra algorithm results."""
    distance: float
    path: List[Location]
    visited_order: List[int] = field(default_factory=list)
    pq_snapshots: List[List[Tuple[float, int]]] = field(default_factory=list)


class GraphEngine:
    """
    Graph engine for campus navigation using Dijkstra's algorithm.

    Builds an adjacency list from non-blocked Edge records and provides
    shortest path computation with support for dynamic edge blocking.
    """

    WALKING_SPEED_MPS = 1.2  # meters per second

    def __init__(self, blocked_edge_ids: Optional[Set[int]] = None):
        """
        Initialize the graph engine.

        Args:
            blocked_edge_ids: Set of edge IDs to treat as blocked (override DB).
        """
        self.blocked_edge_ids = blocked_edge_ids or set()
        self._adjacency_list: Dict[int, List[Tuple[int, float, int]]] = {}
        self._locations: Dict[int, Location] = {}
        self._build_graph()

    def _build_graph(self) -> None:
        """Build adjacency list from all non-blocked edges in database."""
        self._adjacency_list.clear()
        self._locations.clear()

        # Load all locations
        for location in Location.objects.all():
            self._locations[location.id] = location
            self._adjacency_list[location.id] = []

        # Load all non-blocked edges
        edges = Edge.objects.select_related('source', 'destination').all()
        for edge in edges:
            if edge.id in self.blocked_edge_ids or edge.is_blocked:
                continue
            self._adjacency_list[edge.source_id].append(
                (edge.destination_id, edge.distance, edge.id)
            )
            # Add reverse edge for bidirectional traversal
            self._adjacency_list[edge.destination_id].append(
                (edge.source_id, edge.distance, edge.id)
            )

    def refresh(self, blocked_edge_ids: Optional[Set[int]] = None) -> None:
        """
        Rebuild the graph with updated blocked edges.

        Args:
            blocked_edge_ids: New set of blocked edge IDs.
        """
        if blocked_edge_ids is not None:
            self.blocked_edge_ids = blocked_edge_ids
        self._build_graph()

    def find_shortest_path(
        self,
        source_id: int,
        destination_id: int,
        blocked_edge_ids: Optional[Set[int]] = None
    ) -> DijkstraResult:
        """
        Find the shortest path using Dijkstra's algorithm.

        Args:
            source_id: Starting location ID.
            destination_id: Target location ID.
            blocked_edge_ids: Additional edges to block for this query.

        Returns:
            DijkstraResult with distance, path, and visualization data.

        Raises:
            NoPathException: If no path exists between source and destination.
            ValueError: If source or destination doesn't exist.
        """
        if blocked_edge_ids:
            self.refresh(self.blocked_edge_ids | blocked_edge_ids)

        if source_id not in self._locations:
            raise ValueError(f"Source location {source_id} not found")
        if destination_id not in self._locations:
            raise ValueError(f"Destination location {destination_id} not found")

        if source_id == destination_id:
            return DijkstraResult(
                distance=0.0,
                path=[self._locations[source_id]],
                visited_order=[source_id]
            )

        # Dijkstra's algorithm with min-heap priority queue
        # distances[node] = shortest known distance from source
        distances: Dict[int, float] = {node: float('inf') for node in self._adjacency_list}
        distances[source_id] = 0.0

        # previous[node] = previous node on shortest path from source
        previous: Dict[int, Optional[int]] = {node: None for node in self._adjacency_list}

        # Min-heap: (distance, node_id)
        # Using heapq gives us O(log V) extract-min and O(log V) decrease-key
        priority_queue: List[Tuple[float, int]] = [(0.0, source_id)]
        heapq.heapify(priority_queue)

        visited: Set[int] = set()
        visited_order: List[int] = []
        pq_snapshots: List[List[Tuple[float, int]]] = []

        while priority_queue:
            # Capture PQ state for visualization
            pq_snapshots.append(priority_queue.copy())

            current_dist, current_node = heapq.heappop(priority_queue)

            if current_node in visited:
                continue

            visited.add(current_node)
            visited_order.append(current_node)

            # Early exit if we reached destination
            if current_node == destination_id:
                break

            # If we popped a stale entry (distance > known distance), skip
            if current_dist > distances[current_node]:
                continue

            # Relax edges
            for neighbor, weight, edge_id in self._adjacency_list[current_node]:
                if neighbor in visited:
                    continue

                new_dist = current_dist + weight
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    previous[neighbor] = current_node
                    heapq.heappush(priority_queue, (new_dist, neighbor))

        # Check if destination was reached
        if distances[destination_id] == float('inf'):
            raise NoPathException(source_id, destination_id)

        # Reconstruct path
        path_nodes = []
        current = destination_id
        while current is not None:
            path_nodes.append(self._locations[current])
            current = previous[current]
        path_nodes.reverse()

        return DijkstraResult(
            distance=distances[destination_id],
            path=path_nodes,
            visited_order=visited_order,
            pq_snapshots=pq_snapshots
        )

    def get_estimated_time(self, distance_meters: float) -> float:
        """
        Calculate estimated walking time.

        Args:
            distance_meters: Distance in meters.

        Returns:
            Estimated time in minutes.
        """
        return (distance_meters / self.WALKING_SPEED_MPS) / 60.0

    def get_all_locations(self) -> List[Location]:
        """Get all locations sorted by name."""
        return list(self._locations.values())

    def get_graph_data(self) -> dict:
        """
        Get full graph data for frontend rendering.

        Returns:
            Dictionary with nodes and edges for visualization.
        """
        nodes = []
        for loc in self._locations.values():
            nodes.append({
                'id': loc.id,
                'name': loc.name,
                'type': loc.type,
                'latitude': loc.latitude,
                'longitude': loc.longitude,
                'description': loc.description,
            })

        edges = []
        seen = set()
        for source_id, neighbors in self._adjacency_list.items():
            for dest_id, distance, edge_id in neighbors:
                # Avoid duplicates for bidirectional edges
                key = tuple(sorted([source_id, dest_id]))
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    'source': source_id,
                    'target': dest_id,
                    'distance': distance,
                    'edge_id': edge_id,
                    'is_blocked': edge_id in self.blocked_edge_ids,
                })

        return {
            'nodes': nodes,
            'edges': edges,
            'stats': {
                'total_locations': len(nodes),
                'total_paths': len(edges),
                'blocked_roads': sum(1 for e in edges if e['is_blocked']),
            }
        }


def find_shortest_path(
    source_id: int,
    destination_id: int,
    blocked_edge_ids: Optional[Set[int]] = None
) -> DijkstraResult:
    """
    Convenience function to find shortest path.

    Args:
        source_id: Starting location ID.
        destination_id: Target location ID.
        blocked_edge_ids: Set of edge IDs to block.

    Returns:
        DijkstraResult with distance, path, and metadata.
    """
    engine = GraphEngine(blocked_edge_ids)
    return engine.find_shortest_path(source_id, destination_id, blocked_edge_ids)