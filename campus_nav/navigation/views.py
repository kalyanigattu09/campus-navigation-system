"""
Views for the Campus Navigation System.

Provides RESTful API endpoints and the main page view.
"""
import json
from typing import Any, Dict, List

from django.http import JsonResponse, HttpRequest
from django.shortcuts import render
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from navigation.models import Location, Edge
from navigation.utils.graph import GraphEngine, NoPathException, find_shortest_path
from navigation.utils.instructions import generate_instructions, get_alternative_path


def home(request: HttpRequest):
    """
    Render the main campus navigation page.

    GET / → Renders the map interface with location dropdowns.
    """
    return render(request, 'navigation/index.html')


def api_locations(request: HttpRequest) -> JsonResponse:
    """
    GET /api/locations/ → JSON list of all locations.

    Returns:
        JSON array of location objects.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    locations = Location.objects.all().order_by('name')
    data = [loc.to_dict() for loc in locations]
    return JsonResponse({'locations': data, 'count': len(data)})


def api_edges(request: HttpRequest) -> JsonResponse:
    """
    GET /api/edges/ → JSON list of all edges with blocked status.

    Returns:
        JSON array of edge objects.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    edges = Edge.objects.select_related('source', 'destination').all().order_by('source__name', 'destination__name')
    data = [edge.to_dict() for edge in edges]
    return JsonResponse({'edges': data, 'count': len(data)})


@method_decorator(csrf_exempt, name='dispatch')
class FindPathView(View):
    """
    POST /api/find-path/ → Find shortest path between two locations.

    Accepts JSON: {source_id, destination_id, blocked_ids:[]}
    Returns: {path:[{id,name,lat,lng}], distance, time, steps:[]}
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        source_id = data.get('source_id')
        destination_id = data.get('destination_id')
        blocked_ids = set(data.get('blocked_ids', []))

        if source_id is None or destination_id is None:
            return JsonResponse(
                {'error': 'source_id and destination_id are required'},
                status=400
            )

        try:
            source_id = int(source_id)
            destination_id = int(destination_id)
        except (ValueError, TypeError):
            return JsonResponse(
                {'error': 'source_id and destination_id must be integers'},
                status=400
            )

        try:
            engine = GraphEngine(blocked_edge_ids=blocked_ids)
            result = engine.find_shortest_path(source_id, destination_id)

            # Generate turn-by-turn instructions
            steps = generate_instructions(result.path)

            # Get alternative path
            alt_path = get_alternative_path(result.path, engine, source_id, destination_id)
            alternative = None
            if alt_path:
                alt_distance = sum(
                    engine._adjacency_list[alt_path[i].id][
                        next(j for j, (n, _, _) in enumerate(engine._adjacency_list[alt_path[i].id]) if n == alt_path[i+1].id)
                    ][1]
                    for i in range(len(alt_path) - 1)
                )
                alternative = {
                    'path': [loc.to_dict() for loc in alt_path],
                    'distance': alt_distance,
                    'time': engine.get_estimated_time(alt_distance),
                }

            response_data = {
                'path': [loc.to_dict() for loc in result.path],
                'distance': result.distance,
                'distance_text': f"{result.distance:.0f} m" if result.distance < 1000 else f"{result.distance/1000:.1f} km",
                'time': engine.get_estimated_time(result.distance),
                'time_text': f"{engine.get_estimated_time(result.distance):.1f} min",
                'steps': steps,
                'alternative': alternative,
                'visited_order': result.visited_order,
            }
            return JsonResponse(response_data)

        except NoPathException as e:
            return JsonResponse({'error': str(e)}, status=404)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ToggleBlockView(View):
    """
    POST /api/toggle-block/ → Toggle edge blocked status.

    Accepts JSON: {edge_id, is_blocked}
    Returns: Updated edge object.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        edge_id = data.get('edge_id')
        is_blocked = data.get('is_blocked')

        if edge_id is None or is_blocked is None:
            return JsonResponse(
                {'error': 'edge_id and is_blocked are required'},
                status=400
            )

        try:
            edge = Edge.objects.get(id=edge_id)
        except Edge.DoesNotExist:
            return JsonResponse({'error': 'Edge not found'}, status=404)

        edge.is_blocked = bool(is_blocked)
        edge.save()

        return JsonResponse({'edge': edge.to_dict()})


def api_campus_graph(request: HttpRequest) -> JsonResponse:
    """
    GET /api/campus-graph/ → Full graph data for frontend rendering.

    Returns:
        JSON with nodes, edges, and stats.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    engine = GraphEngine()
    data = engine.get_graph_data()
    return JsonResponse(data)


def api_stats(request: HttpRequest) -> JsonResponse:
    """
    GET /api/stats/ → Live statistics for the ticker.

    Returns:
        JSON with total locations, paths, blocked roads.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    total_locations = Location.objects.count()
    total_paths = Edge.objects.count()
    blocked_roads = Edge.objects.filter(is_blocked=True).count()

    return JsonResponse({
        'total_locations': total_locations,
        'total_paths': total_paths,
        'blocked_roads': blocked_roads,
    })


@method_decorator(csrf_exempt, name='dispatch')
class VisualizeDijkstraView(View):
    """
    POST /api/visualize-dijkstra/ → Get Dijkstra visualization data.

    Accepts JSON: {source_id, destination_id, blocked_ids:[]}
    Returns: Step-by-step visualization data including visited nodes,
             priority queue snapshots, and final path.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        source_id = data.get('source_id')
        destination_id = data.get('destination_id')
        blocked_ids = set(data.get('blocked_ids', []))

        if source_id is None or destination_id is None:
            return JsonResponse(
                {'error': 'source_id and destination_id are required'},
                status=400
            )

        try:
            source_id = int(source_id)
            destination_id = int(destination_id)
        except (ValueError, TypeError):
            return JsonResponse(
                {'error': 'source_id and destination_id must be integers'},
                status=400
            )

        try:
            engine = GraphEngine(blocked_edge_ids=blocked_ids)
            result = engine.find_shortest_path(source_id, destination_id)

            # Build detailed visualization data
            steps = []
            distances = {node: float('inf') for node in engine._adjacency_list}
            distances[source_id] = 0.0

            for i, node_id in enumerate(result.visited_order):
                node = engine._locations[node_id]
                step_data = {
                    'step': i + 1,
                    'visited_node': node.to_dict(),
                    'current_distance': distances[node_id],
                    'queue_snapshot': [
                        {'node': engine._locations[nid].to_dict() if nid in engine._locations else {'id': nid}, 'distance': dist}
                        for dist, nid in result.pq_snapshots[i] if i < len(result.pq_snapshots)
                    ] if i < len(result.pq_snapshots) else [],
                }
                steps.append(step_data)

                # Update distances for next iteration (simplified)
                for neighbor, weight, _ in engine._adjacency_list.get(node_id, []):
                    new_dist = distances[node_id] + weight
                    if new_dist < distances[neighbor]:
                        distances[neighbor] = new_dist

            return JsonResponse({
                'steps': steps,
                'final_path': [loc.to_dict() for loc in result.path],
                'total_distance': result.distance,
                'visited_order': result.visited_order,
            })

        except NoPathException as e:
            return JsonResponse({'error': str(e)}, status=404)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)