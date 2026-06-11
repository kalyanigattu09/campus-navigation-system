"""HTTP views for the navigation app: pages + JSON API endpoints."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from navigation.models import Edge, Location
from navigation.utils.graph import (
    NoPathException,
    WALKING_SPEED_MPS,
    dijkstra,
    dijkstra_with_trace,
    find_alternative_path,
)
from navigation.utils.instructions import build_steps


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


def home(request: HttpRequest):
    """Render the single-page campus map UI."""
    return render(request, "navigation/index.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _location_payload(loc: Location) -> Dict[str, Any]:
    return {
        "id": loc.id,
        "name": loc.name,
        "type": loc.type,
        "lat": loc.latitude,
        "lng": loc.longitude,
        "x": loc.map_x,
        "y": loc.map_y,
        "description": loc.description,
    }


def _edge_payload(edge: Edge) -> Dict[str, Any]:
    return {
        "id": edge.id,
        "source": edge.source_id,
        "destination": edge.destination_id,
        "distance": edge.distance,
        "is_blocked": edge.is_blocked,
        "path_name": edge.path_name,
    }


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _parse_json(request: HttpRequest) -> Dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def _parse_blocked_ids(payload: Dict[str, Any]) -> List[int]:
    """Return valid integer edge ids from a request payload."""
    blocked_ids: List[int] = []
    for raw in payload.get("blocked_ids") or []:
        try:
            blocked_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return blocked_ids


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@require_GET
def api_locations(request: HttpRequest) -> JsonResponse:
    """Return every Location as a JSON array."""
    locations = [_location_payload(loc) for loc in Location.objects.all()]
    return JsonResponse({"locations": locations})


@require_GET
def api_edges(request: HttpRequest) -> JsonResponse:
    """Return every Edge (with its blocked status) as JSON."""
    edges = [_edge_payload(edge) for edge in Edge.objects.select_related("source", "destination")]
    return JsonResponse({"edges": edges})


@require_GET
def api_campus_graph(request: HttpRequest) -> JsonResponse:
    """Combined graph payload used by the canvas renderer."""
    locations = [_location_payload(loc) for loc in Location.objects.all()]
    edges = [_edge_payload(edge) for edge in Edge.objects.select_related("source", "destination")]
    stats = {
        "total_locations": len(locations),
        "total_edges": len(edges),
        "blocked_edges": sum(1 for e in edges if e["is_blocked"]),
    }
    return JsonResponse({"locations": locations, "edges": edges, "stats": stats})


@csrf_exempt
@require_POST
def api_find_path(request: HttpRequest) -> JsonResponse:
    """Compute a shortest path between two locations."""
    payload = _parse_json(request)
    try:
        source_id = int(payload.get("source_id"))
        destination_id = int(payload.get("destination_id"))
    except (TypeError, ValueError):
        return _error("source_id and destination_id are required integers.")

    avoid_blocked = bool(payload.get("avoid_blocked", True))
    blocked_ids = _parse_blocked_ids(payload)
    emergency = bool(payload.get("emergency"))

    try:
        primary = dijkstra(
            source_id,
            destination_id,
            blocked_edge_ids=blocked_ids,
            include_db_blocked=not avoid_blocked,
        )
    except NoPathException as exc:
        return _error(str(exc), status=404)

    # For emergency mode, mildly bias the path by re-running with a
    # small inflation factor on the primary route's edges to find an
    # alternate, "less crowded" direction. We just return the alternate
    # in that case if one exists.
    if emergency:
        alt = find_alternative_path(
            source_id,
            destination_id,
            primary,
            blocked_edge_ids=blocked_ids,
            include_db_blocked=not avoid_blocked,
        )
        if alt is not None:
            primary = alt

    alternative_payload = None
    alt = find_alternative_path(
        source_id,
        destination_id,
        primary,
        blocked_edge_ids=blocked_ids,
        include_db_blocked=not avoid_blocked,
    )
    if alt is not None and alt.distance != primary.distance:
        alternative_payload = {
            "path": [_location_payload(loc) for loc in alt.locations],
            "distance": alt.distance,
            "time": alt.travel_time,
        }

    steps = build_steps(primary.locations)
    return JsonResponse(
        {
            "path": [_location_payload(loc) for loc in primary.locations],
            "distance": primary.distance,
            "time": primary.travel_time,
            "time_minutes": primary.travel_time / 60.0,
            "walking_speed_mps": WALKING_SPEED_MPS,
            "steps": steps,
            "alternative": alternative_payload,
        }
    )


@csrf_exempt
@require_POST
def api_toggle_block(request: HttpRequest) -> JsonResponse:
    """Flip an edge's is_blocked flag."""
    payload = _parse_json(request)
    edge_id = payload.get("edge_id")
    if edge_id is None:
        return _error("edge_id is required.")

    is_blocked = bool(payload.get("is_blocked", True))

    try:
        edge = Edge.objects.get(pk=int(edge_id))
    except (Edge.DoesNotExist, TypeError, ValueError):
        return _error("Edge not found.", status=404)

    pair_edges = Edge.objects.filter(
        source_id=edge.source_id,
        destination_id=edge.destination_id,
    ) | Edge.objects.filter(
        source_id=edge.destination_id,
        destination_id=edge.source_id,
    )
    pair_edges.update(is_blocked=is_blocked)
    edge.refresh_from_db()
    return JsonResponse(
        {
            "edge": _edge_payload(edge),
            "updated_edge_ids": list(pair_edges.values_list("id", flat=True)),
        }
    )


@csrf_exempt
@require_POST
def api_visualize(request: HttpRequest) -> JsonResponse:
    """Return a step-by-step trace of Dijkstra for the visualiser."""
    payload = _parse_json(request)
    try:
        source_id = int(payload.get("source_id"))
        destination_id = int(payload.get("destination_id"))
    except (TypeError, ValueError):
        return _error("source_id and destination_id are required integers.")

    avoid_blocked = bool(payload.get("avoid_blocked", True))
    blocked_ids = _parse_blocked_ids(payload)

    trace = dijkstra_with_trace(
        source_id,
        destination_id,
        blocked_edge_ids=blocked_ids,
        include_db_blocked=not avoid_blocked,
    )
    serialized: List[Dict[str, Any]] = []
    for entry in trace:
        serialized.append(
            {
                "visited_id": entry.visited_id,
                "distance": entry.distance,
                "edge_from": entry.edge_from,
                "updated_id": entry.updated_id,
                "queue": [
                    {"distance": d, "node_id": nid} for d, nid in entry.queue_snapshot
                ],
            }
        )
    return JsonResponse({"trace": serialized})
