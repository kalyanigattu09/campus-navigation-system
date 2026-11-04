"""HTTP views and REST API endpoints for the Campus Navigation System."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from navigation.models import Edge, Location, RouteLog
from navigation.utils.graph import (
    NoPathException,
    WALKING_SPEED_MPS,
    dijkstra,
    dijkstra_with_trace,
    find_alternative_path,
    get_graph_version,
    invalidate_graph_cache,
)
from navigation.utils.instructions import build_steps


# ---------------------------------------------------------------------------
# Helper Responses & Utilities
# ---------------------------------------------------------------------------


def _error_response(message: str, status: int = 400) -> JsonResponse:
    """Return a consistent error JSON response without internal stack trace."""
    return JsonResponse({"error": message, "success": False}, status=status)


def _parse_json(request: HttpRequest) -> Dict[str, Any]:
    """Safely decode and parse JSON request body."""
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


def _is_admin(user) -> bool:
    """Check if the requesting user has administrative privileges."""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


# ---------------------------------------------------------------------------
# Page Views
# ---------------------------------------------------------------------------


@ensure_csrf_cookie
def home(request: HttpRequest):
    """Render the primary interactive Campus Navigation map page."""
    return render(
        request,
        "navigation/index.html",
        {
            "is_admin": _is_admin(request.user),
            "username": request.user.username if request.user.is_authenticated else "",
        },
    )


@ensure_csrf_cookie
def admin_dashboard(request: HttpRequest):
    """Render the Administrator Management Dashboard."""
    if not _is_admin(request.user):
        return redirect("/admin-login/?next=/dashboard/")

    locations = Location.objects.all().order_by("name")
    edges = Edge.objects.select_related("source", "destination").all().order_by("source__name")
    recent_routes = RouteLog.objects.select_related("source", "destination")[:20]

    stats = {
        "total_locations": locations.count(),
        "total_edges": edges.count() // 2,  # Bidirectional pairs
        "blocked_edges": edges.filter(is_blocked=True).count() // 2,
        "total_routes_logged": RouteLog.objects.count(),
    }

    return render(
        request,
        "navigation/admin_dashboard.html",
        {
            "locations": locations,
            "edges": edges,
            "recent_routes": recent_routes,
            "stats": stats,
            "is_admin": True,
            "username": request.user.username,
        },
    )


@ensure_csrf_cookie
def analytics_view(request: HttpRequest):
    """Render the Performance & Benchmarking Analytics page."""
    return render(
        request,
        "navigation/analytics.html",
        {
            "is_admin": _is_admin(request.user),
            "username": request.user.username if request.user.is_authenticated else "",
        },
    )


def admin_login_view(request: HttpRequest):
    """Handle administrator session login."""
    if request.method == "POST":
        payload = _parse_json(request) if request.content_type == "application/json" else request.POST
        username = payload.get("username", "").strip()
        password = payload.get("password", "").strip()

        user = authenticate(request, username=username, password=password)
        if user is not None and (user.is_staff or user.is_superuser):
            login(request, user)
            if request.content_type == "application/json":
                return JsonResponse({"success": True, "redirect": "/dashboard/"})
            return redirect(request.GET.get("next", "/dashboard/"))
        else:
            if request.content_type == "application/json":
                return _error_response("Invalid administrator credentials.", status=401)
            return render(
                request,
                "navigation/admin_login.html",
                {"error": "Invalid administrator credentials.", "next": request.GET.get("next", "/dashboard/")},
            )

    return render(
        request,
        "navigation/admin_login.html",
        {"next": request.GET.get("next", "/dashboard/")},
    )


def admin_logout_view(request: HttpRequest):
    """Handle administrator session logout."""
    logout(request)
    if request.content_type == "application/json":
        return JsonResponse({"success": True, "redirect": "/"})
    return redirect("/")


# ---------------------------------------------------------------------------
# Location API Endpoints
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def api_locations(request: HttpRequest) -> JsonResponse:
    """List all campus locations or create a new location (admin only)."""
    if request.method == "GET":
        query = request.GET.get("q", "").strip()
        loc_type = request.GET.get("type", "").strip()

        qs = Location.objects.all()
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query))
        if loc_type:
            qs = qs.filter(type=loc_type)

        locations = [loc.to_dict() for loc in qs]
        return JsonResponse({"locations": locations, "count": len(locations), "success": True})

    # POST: Create location
    if not _is_admin(request.user):
        return _error_response("Administrator authorization required to add locations.", status=403)

    payload = _parse_json(request)
    name = str(payload.get("name", "")).strip()
    if not name:
        return _error_response("Location name is required.")

    if Location.objects.filter(name__iexact=name).exists():
        return _error_response(f"A location named '{name}' already exists.")

    try:
        lat = float(payload.get("lat", payload.get("latitude", 0.0)))
        lng = float(payload.get("lng", payload.get("longitude", 0.0)))
        map_x = max(0.0, min(1.0, float(payload.get("x", payload.get("map_x", 0.5)))))
        map_y = max(0.0, min(1.0, float(payload.get("y", payload.get("map_y", 0.5)))))
    except (ValueError, TypeError):
        return _error_response("Coordinates must be valid numbers.")

    ltype = payload.get("type", "building").lower()
    valid_types = {t[0] for t in Location.LOCATION_TYPES}
    if ltype not in valid_types:
        ltype = "building"

    desc = str(payload.get("description", "")).strip()

    location = Location.objects.create(
        name=name,
        type=ltype,
        latitude=lat,
        longitude=lng,
        map_x=map_x,
        map_y=map_y,
        description=desc,
    )
    invalidate_graph_cache()
    return JsonResponse({"location": location.to_dict(), "success": True}, status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_location_detail(request: HttpRequest, pk: int) -> JsonResponse:
    """Retrieve, update, or delete a single campus location."""
    try:
        location = Location.objects.get(pk=pk)
    except Location.DoesNotExist:
        return _error_response(f"Location {pk} not found.", status=404)

    if request.method == "GET":
        return JsonResponse({"location": location.to_dict(), "success": True})

    if not _is_admin(request.user):
        return _error_response("Administrator authorization required.", status=403)

    if request.method == "DELETE":
        with transaction.atomic():
            name = location.name
            location.delete()
            invalidate_graph_cache()
        return JsonResponse({"message": f"Location '{name}' deleted.", "success": True})

    # PUT: Update
    payload = _parse_json(request)
    name = str(payload.get("name", location.name)).strip()
    if not name:
        return _error_response("Location name cannot be empty.")

    if Location.objects.filter(name__iexact=name).exclude(pk=pk).exists():
        return _error_response(f"Another location is already named '{name}'.")

    try:
        location.name = name
        location.type = payload.get("type", location.type)
        if "lat" in payload or "latitude" in payload:
            location.latitude = float(payload.get("lat", payload.get("latitude", location.latitude)))
        if "lng" in payload or "longitude" in payload:
            location.longitude = float(payload.get("lng", payload.get("longitude", location.longitude)))
        if "x" in payload or "map_x" in payload:
            location.map_x = max(0.0, min(1.0, float(payload.get("x", payload.get("map_x", location.map_x)))))
        if "y" in payload or "map_y" in payload:
            location.map_y = max(0.0, min(1.0, float(payload.get("y", payload.get("map_y", location.map_y)))))
        if "description" in payload:
            location.description = str(payload["description"]).strip()
        location.save()
        invalidate_graph_cache()
    except (ValueError, TypeError) as exc:
        return _error_response(f"Invalid input: {exc}")

    return JsonResponse({"location": location.to_dict(), "success": True})


# ---------------------------------------------------------------------------
# Edge API Endpoints
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def api_edges(request: HttpRequest) -> JsonResponse:
    """List all pathways or create a new bidirectional pathway (admin only)."""
    if request.method == "GET":
        edges = Edge.objects.select_related("source", "destination").all()
        return JsonResponse({
            "edges": [edge.to_dict() for edge in edges],
            "count": edges.count(),
            "success": True,
        })

    if not _is_admin(request.user):
        return _error_response("Administrator authorization required to add pathways.", status=403)

    payload = _parse_json(request)
    try:
        source_id = int(payload.get("source_id"))
        dest_id = int(payload.get("destination_id"))
        distance = float(payload.get("distance", 0.0))
    except (ValueError, TypeError):
        return _error_response("source_id, destination_id, and distance must be valid numbers.")

    if source_id == dest_id:
        return _error_response("Source and destination locations cannot be the same.")

    if distance <= 0:
        return _error_response("Pathway distance must be strictly positive.")

    source_loc = Location.objects.filter(pk=source_id).first()
    dest_loc = Location.objects.filter(pk=dest_id).first()
    if not source_loc or not dest_loc:
        return _error_response("One or both specified locations do not exist.", status=404)

    path_name = str(payload.get("path_name", "")).strip()
    is_blocked = bool(payload.get("is_blocked", False))

    with transaction.atomic():
        fwd, _ = Edge.objects.update_or_create(
            source=source_loc,
            destination=dest_loc,
            defaults={"distance": distance, "path_name": path_name, "is_blocked": is_blocked},
        )
        rev, _ = Edge.objects.update_or_create(
            source=dest_loc,
            destination=source_loc,
            defaults={"distance": distance, "path_name": path_name, "is_blocked": is_blocked},
        )
        invalidate_graph_cache()

    return JsonResponse({
        "edge": fwd.to_dict(),
        "paired_edge": rev.to_dict(),
        "success": True,
    }, status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_edge_detail(request: HttpRequest, pk: int) -> JsonResponse:
    """Retrieve, update, or delete a pathway pair."""
    try:
        edge = Edge.objects.select_related("source", "destination").get(pk=pk)
    except Edge.DoesNotExist:
        return _error_response(f"Pathway {pk} not found.", status=404)

    if request.method == "GET":
        return JsonResponse({"edge": edge.to_dict(), "success": True})

    if not _is_admin(request.user):
        return _error_response("Administrator authorization required.", status=403)

    pair_edges = Edge.objects.filter(
        Q(source_id=edge.source_id, destination_id=edge.destination_id)
        | Q(source_id=edge.destination_id, destination_id=edge.source_id)
    )

    if request.method == "DELETE":
        with transaction.atomic():
            count = pair_edges.delete()[0]
            invalidate_graph_cache()
        return JsonResponse({"message": f"Pathway deleted ({count} directed edges removed).", "success": True})

    # PUT: Update distance / name / block status
    payload = _parse_json(request)
    updates: Dict[str, Any] = {}
    if "distance" in payload:
        try:
            dist = float(payload["distance"])
            if dist <= 0:
                return _error_response("Distance must be positive.")
            updates["distance"] = dist
        except (ValueError, TypeError):
            return _error_response("Invalid distance number.")

    if "path_name" in payload:
        updates["path_name"] = str(payload["path_name"]).strip()

    if "is_blocked" in payload:
        updates["is_blocked"] = bool(payload["is_blocked"])

    if updates:
        with transaction.atomic():
            pair_edges.update(**updates)
            edge.refresh_from_db()
            invalidate_graph_cache()

    return JsonResponse({"edge": edge.to_dict(), "success": True})


# ---------------------------------------------------------------------------
# Graph & Pathfinding API Endpoints
# ---------------------------------------------------------------------------


@require_GET
def api_campus_graph(request: HttpRequest) -> JsonResponse:
    """Return combined graph representation and network statistics for Canvas."""
    locations = [loc.to_dict() for loc in Location.objects.all().order_by("name")]
    edges = [
        edge.to_dict()
        for edge in Edge.objects.select_related("source", "destination").all().order_by("source__name")
    ]

    v = len(locations)
    e = len(edges) // 2  # Bidirectional pairs
    max_edges = (v * (v - 1)) / 2 if v > 1 else 1
    density = round(e / max_edges, 4) if v > 1 else 0.0

    stats = {
        "total_locations": v,
        "total_edges": e,
        "directed_edge_count": len(edges),
        "blocked_edges": sum(1 for item in edges if item["is_blocked"]) // 2,
        "graph_density": density,
        "graph_version": get_graph_version(),
    }
    return JsonResponse({"locations": locations, "edges": edges, "stats": stats, "success": True})


@require_POST
def api_find_path(request: HttpRequest) -> JsonResponse:
    """Calculate the shortest route between two campus locations using Dijkstra's algorithm."""
    payload = _parse_json(request)
    try:
        source_id = int(payload.get("source_id"))
        dest_id = int(payload.get("destination_id"))
    except (TypeError, ValueError):
        return _error_response("source_id and destination_id are required integers.")

    avoid_blocked = bool(payload.get("avoid_blocked", True))
    use_heapq = bool(payload.get("use_heapq", False))

    blocked_ids: List[int] = []
    for raw in payload.get("blocked_ids") or []:
        try:
            blocked_ids.append(int(raw))
        except (TypeError, ValueError):
            continue

    try:
        primary = dijkstra(
            source_id,
            dest_id,
            blocked_edge_ids=blocked_ids,
            include_db_blocked=not avoid_blocked,
            use_reference_heapq=use_heapq,
        )
    except ValueError as val_err:
        return _error_response(str(val_err), status=400)
    except NoPathException as no_path_err:
        return _error_response(str(no_path_err), status=404)

    # Calculate genuine alternative route if one exists
    alternative_payload = None
    alt = find_alternative_path(
        source_id,
        dest_id,
        primary,
        blocked_edge_ids=blocked_ids,
        include_db_blocked=not avoid_blocked,
    )
    if alt is not None and alt.distance != primary.distance:
        alternative_payload = {
            "path": [loc.to_dict() for loc in alt.locations],
            "distance": alt.distance,
            "time": alt.travel_time,
            "time_minutes": round(alt.travel_time / 60.0, 1),
            "edge_count": alt.edge_count,
        }

    # Generate step-by-step navigation instructions
    steps = build_steps(primary.locations)

    # Record route calculation audit log asynchronously/safely
    try:
        RouteLog.objects.create(
            source_id=source_id,
            destination_id=dest_id,
            distance=primary.distance,
            travel_time=primary.travel_time,
            execution_time_ms=primary.metrics.execution_time_ms,
            avoid_blocked=avoid_blocked,
        )
    except Exception:
        pass  # Non-blocking for navigation response

    return JsonResponse({
        "path": [loc.to_dict() for loc in primary.locations],
        "distance": primary.distance,
        "time": primary.travel_time,
        "time_minutes": round(primary.travel_time / 60.0, 1),
        "walking_speed_mps": WALKING_SPEED_MPS,
        "edge_count": primary.edge_count,
        "steps": steps,
        "alternative": alternative_payload,
        "metrics": {
            "execution_time_ms": primary.metrics.execution_time_ms,
            "nodes_visited": primary.metrics.nodes_visited,
            "edges_examined": primary.metrics.edges_examined,
            "pq_operations": primary.metrics.pq_operations,
            "relaxations": primary.metrics.relaxations,
            "queue_type": primary.metrics.queue_type,
        },
        "graph_version": get_graph_version(),
        "success": True,
    })


@require_POST
def api_toggle_block(request: HttpRequest) -> JsonResponse:
    """Toggle the blocked status of a pathway in both directions."""
    payload = _parse_json(request)
    edge_id = payload.get("edge_id")
    if edge_id is None:
        return _error_response("edge_id is required.")

    is_blocked = bool(payload.get("is_blocked", True))

    try:
        edge = Edge.objects.get(pk=int(edge_id))
    except (Edge.DoesNotExist, TypeError, ValueError):
        return _error_response(f"Edge {edge_id} not found.", status=404)

    # Synchronize bidirectional pair
    pair_edges = Edge.objects.filter(
        Q(source_id=edge.source_id, destination_id=edge.destination_id)
        | Q(source_id=edge.destination_id, destination_id=edge.source_id)
    )

    with transaction.atomic():
        pair_edges.update(is_blocked=is_blocked)
        edge.refresh_from_db()
        invalidate_graph_cache()

    return JsonResponse({
        "edge": edge.to_dict(),
        "updated_edge_ids": list(pair_edges.values_list("id", flat=True)),
        "is_blocked": is_blocked,
        "graph_version": get_graph_version(),
        "success": True,
    })


@require_POST
def api_visualize(request: HttpRequest) -> JsonResponse:
    """Return a step-by-step trace of Dijkstra execution for priority-queue replay."""
    payload = _parse_json(request)
    try:
        source_id = int(payload.get("source_id"))
        dest_id = int(payload.get("destination_id"))
    except (TypeError, ValueError):
        return _error_response("source_id and destination_id are required integers.")

    avoid_blocked = bool(payload.get("avoid_blocked", True))
    blocked_ids: List[int] = []
    for raw in payload.get("blocked_ids") or []:
        try:
            blocked_ids.append(int(raw))
        except (TypeError, ValueError):
            continue

    try:
        trace = dijkstra_with_trace(
            source_id,
            dest_id,
            blocked_edge_ids=blocked_ids,
            include_db_blocked=not avoid_blocked,
        )
    except Exception as exc:
        return _error_response(f"Visualization trace failed: {exc}")

    serialized = [
        {
            "visited_id": entry.visited_id,
            "distance": round(entry.distance, 2),
            "edge_from": entry.edge_from,
            "updated_id": entry.updated_id,
            "queue": [{"distance": round(d, 2), "node_id": nid} for d, nid in entry.queue_snapshot],
        }
        for entry in trace
    ]

    return JsonResponse({"trace": serialized, "total_steps": len(serialized), "success": True})


@require_GET
def api_recent_activity(request: HttpRequest) -> JsonResponse:
    """Return recent route calculations and network activity."""
    recent_routes = [
        r.to_dict()
        for r in RouteLog.objects.select_related("source", "destination").all()[:25]
    ]
    return JsonResponse({"recent_routes": recent_routes, "success": True})


@require_GET
def api_benchmark_results(request: HttpRequest) -> JsonResponse:
    """Return stored benchmark results for the performance analytics dashboard."""
    from navigation.benchmark import load_cached_benchmark_results

    results = load_cached_benchmark_results()
    if results is None:
        return JsonResponse({
            "available": False,
            "message": "Run the benchmark suite to generate performance analytics.",
        })
    return JsonResponse({"available": True, "results": results, "success": True})


@require_POST
def api_run_benchmarks(request: HttpRequest) -> JsonResponse:
    """Trigger execution of the benchmarking suite and return updated results."""
    from navigation.benchmark import run_full_benchmark_suite

    try:
        results = run_full_benchmark_suite()
        return JsonResponse({"results": results, "success": True})
    except Exception as exc:
        return _error_response(f"Benchmark execution failed: {exc}", status=500)



# ---------------------------------------------------------------------------
# Campus Map Management API Endpoints
# ---------------------------------------------------------------------------

@require_GET
def api_maps(request: HttpRequest) -> JsonResponse:
    """List all campus maps with active indicator."""
    from navigation.models import CampusMap
    maps = [m.to_dict() for m in CampusMap.objects.all()]
    active_map = CampusMap.get_active_map()
    return JsonResponse({
        "maps": maps,
        "active_map_id": active_map.id if active_map else None,
        "count": len(maps),
        "success": True,
    })


@require_POST
def api_map_set_active(request: HttpRequest, map_id: int) -> JsonResponse:
    """Switch the active campus map (admin only)."""
    if not _is_admin(request.user):
        return _error_response("Administrator authorization required.", status=403)

    from navigation.models import CampusMap
    try:
        new_active = CampusMap.objects.get(pk=map_id)
    except CampusMap.DoesNotExist:
        return _error_response(f"Map {map_id} not found.", status=404)

    with transaction.atomic():
        CampusMap.objects.update(is_active=False)
        new_active.is_active = True
        new_active.save()
        invalidate_graph_cache()

    return JsonResponse({"map": new_active.to_dict(), "success": True})


@require_POST
def api_map_upload_preview(request: HttpRequest) -> JsonResponse:
    """Parse and validate an uploaded campus map file without writing to DB.
    Returns validation report: {valid, errors, warnings, stats, preview}.
    """
    if not _is_admin(request.user):
        return _error_response("Administrator authorization required.", status=403)

    if "file" not in request.FILES:
        return _error_response("No file uploaded. Send multipart/form-data with 'file' field.")

    uploaded_file = request.FILES["file"]
    filename = uploaded_file.name
    file_bytes = uploaded_file.read()

    if len(file_bytes) > 10 * 1024 * 1024:  # 10 MB limit
        return _error_response("Uploaded file exceeds the 10 MB size limit.")

    from navigation.utils.map_parser import parse_and_validate_map_data
    payload, errors, warnings = parse_and_validate_map_data(file_bytes, filename)

    if errors:
        return JsonResponse({
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "stats": None,
            "preview": None,
            "success": False,
        })

    # Build preview (first 10 locations and 10 edges)
    preview = {
        "locations": payload["locations"][:10],
        "edges": payload["edges"][:10],
        "map_name": payload["map_name"],
        "description": payload["description"],
    }

    return JsonResponse({
        "valid": True,
        "errors": [],
        "warnings": warnings,
        "stats": payload["stats"],
        "preview": preview,
        "payload_hash": str(hash(str(payload))),  # for simple re-submit check
        "success": True,
    })


@require_POST
def api_map_upload_confirm(request: HttpRequest) -> JsonResponse:
    """Commit a validated campus map file payload into the database.
    
    Expects multipart/form-data with:
    - file: the same file as sent to preview
    - map_name (optional): override map name
    - replace_existing (optional): "true" to replace map with same name
    """
    if not _is_admin(request.user):
        return _error_response("Administrator authorization required.", status=403)

    if "file" not in request.FILES:
        return _error_response("No file uploaded.")

    uploaded_file = request.FILES["file"]
    filename = uploaded_file.name
    file_bytes = uploaded_file.read()

    if len(file_bytes) > 10 * 1024 * 1024:
        return _error_response("Uploaded file exceeds the 10 MB size limit.")

    from navigation.utils.map_parser import parse_and_validate_map_data
    from navigation.models import CampusMap, Location, Edge

    payload, errors, warnings = parse_and_validate_map_data(file_bytes, filename)
    if errors:
        return JsonResponse({"valid": False, "errors": errors, "success": False})

    override_name = request.POST.get("map_name", "").strip()
    if override_name:
        payload["map_name"] = override_name

    replace_existing = request.POST.get("replace_existing", "false").lower() == "true"

    with transaction.atomic():
        existing = CampusMap.objects.filter(name__iexact=payload["map_name"]).first()
        if existing and not replace_existing:
            return JsonResponse({
                "conflict": True,
                "existing_map_id": existing.id,
                "existing_map_name": existing.name,
                "message": f"A map named '{existing.name}' already exists. Set replace_existing=true to overwrite it.",
                "success": False,
            })

        if existing and replace_existing:
            # Delete old map and all its data (cascades via FK)
            existing.delete()

        # Deactivate previous active maps
        CampusMap.objects.update(is_active=False)

        # Create the new map
        campus_map = CampusMap.objects.create(
            name=payload["map_name"],
            description=payload.get("description", ""),
            is_active=True,
        )

        # Create Location objects
        name_to_location = {}
        for loc_data in payload["locations"]:
            loc = Location.objects.create(
                campus_map=campus_map,
                name=loc_data["name"],
                type=loc_data["type"],
                latitude=loc_data["latitude"],
                longitude=loc_data["longitude"],
                map_x=loc_data["map_x"],
                map_y=loc_data["map_y"],
                description=loc_data.get("description", ""),
            )
            name_to_location[loc_data["name"].lower()] = loc

        # Create bidirectional Edge objects
        edges_created = 0
        for edge_data in payload["edges"]:
            src = name_to_location.get(edge_data["source"].lower())
            dst = name_to_location.get(edge_data["destination"].lower())
            if not src or not dst:
                continue
            Edge.objects.create(
                campus_map=campus_map,
                source=src,
                destination=dst,
                distance=edge_data["distance"],
                path_name=edge_data.get("path_name", ""),
                is_blocked=edge_data.get("is_blocked", False),
            )
            Edge.objects.create(
                campus_map=campus_map,
                source=dst,
                destination=src,
                distance=edge_data["distance"],
                path_name=edge_data.get("path_name", ""),
                is_blocked=edge_data.get("is_blocked", False),
            )
            edges_created += 1

        invalidate_graph_cache()

    return JsonResponse({
        "map": campus_map.to_dict(),
        "stats": {
            "locations_created": len(name_to_location),
            "pathways_created": edges_created,
        },
        "warnings": warnings,
        "success": True,
    }, status=201)


@require_GET
def api_map_template(request: HttpRequest) -> JsonResponse:
    """Return a downloadable sample map data template in the requested format."""
    from django.http import HttpResponse
    from navigation.utils.map_parser import generate_template_json, generate_template_csv, generate_template_xlsx

    fmt = request.GET.get("format", "json").lower()

    if fmt == "json":
        content = generate_template_json()
        response = HttpResponse(content, content_type="application/json")
        response["Content-Disposition"] = 'attachment; filename="campus_map_template.json"'
        return response
    elif fmt == "csv":
        content = generate_template_csv()
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="campus_map_template.csv"'
        return response
    elif fmt == "xlsx":
        content = generate_template_xlsx()
        response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="campus_map_template.xlsx"'
        return response
    else:
        return _error_response(f"Unknown format '{fmt}'. Use json, csv, or xlsx.")


@require_GET
def api_map_detail(request: HttpRequest, map_id: int) -> JsonResponse:
    """Return full detail for a single campus map including all its locations and edges."""
    from navigation.models import CampusMap
    try:
        campus_map = CampusMap.objects.get(pk=map_id)
    except CampusMap.DoesNotExist:
        return _error_response(f"Map {map_id} not found.", status=404)

    locations = [loc.to_dict() for loc in campus_map.locations.all().order_by("name")]
    edges = [edge.to_dict() for edge in campus_map.edges.select_related("source", "destination").all()]

    return JsonResponse({
        "map": campus_map.to_dict(),
        "locations": locations,
        "edges": edges,
        "success": True,
    })


@require_POST
def api_map_delete(request: HttpRequest, map_id: int) -> JsonResponse:
    """Delete a campus map and all its associated data (admin only)."""
    if not _is_admin(request.user):
        return _error_response("Administrator authorization required.", status=403)

    from navigation.models import CampusMap
    try:
        campus_map = CampusMap.objects.get(pk=map_id)
    except CampusMap.DoesNotExist:
        return _error_response(f"Map {map_id} not found.", status=404)

    if CampusMap.objects.count() <= 1:
        return _error_response("Cannot delete the last remaining campus map.")

    name = campus_map.name
    was_active = campus_map.is_active
    with transaction.atomic():
        campus_map.delete()
        if was_active:
            # Promote remaining map
            remaining = CampusMap.objects.first()
            if remaining:
                remaining.is_active = True
                remaining.save()
        invalidate_graph_cache()

    return JsonResponse({"message": f"Map '{name}' and all its data have been deleted.", "success": True})
