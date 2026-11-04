"""Comprehensive Benchmarking Suite for Dijkstra Algorithm & Priority Queue.

Measures:
1. Real Campus Graph Metrics (V, E, density, components).
2. Algorithm Performance (Execution time, nodes visited, edges examined, PQ ops, relaxations).
3. Routing & Dynamic Rerouting Latency (Primary vs rerouted path latency, no-path detection).
4. Scalability Suite on deterministic synthetic graphs (V = 100, 500, 1,000, 5,000, 10,000).
5. Head-to-Head Comparison: Custom BinaryMinHeap vs Python Standard heapq Reference.
6. Quantitative statistical reporting: Min, Mean, Median, P95, P99, Memory delta.
"""
from __future__ import annotations

import csv
import json
import math
import os
import platform
import random
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from navigation.models import Edge, Location
from navigation.utils.graph import (
    BinaryMinHeap,
    NoPathException,
    WALKING_SPEED_MPS,
    build_adjacency,
    dijkstra,
)


REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
JSON_REPORT_PATH = REPORTS_DIR / "benchmark_results.json"
CSV_REPORT_PATH = REPORTS_DIR / "benchmark_results.csv"


def _percentile(data: List[float], p: float) -> float:
    """Calculate the p-th percentile of a list of floats (0 to 100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (len(sorted_data) - 1) * (p / 100.0)
    floor_idx = int(math.floor(idx))
    ceil_idx = int(math.ceil(idx))
    if floor_idx == ceil_idx:
        return sorted_data[int(idx)]
    d0 = sorted_data[floor_idx] * (ceil_idx - idx)
    d1 = sorted_data[ceil_idx] * (idx - floor_idx)
    return d0 + d1


def generate_synthetic_graph(
    num_vertices: int,
    avg_degree: int = 4,
    seed: int = 42,
) -> Dict[int, List[Tuple[int, float, int]]]:
    """Deterministically generate a connected, weighted graph for benchmarking.

    Uses a geometric 2D layout where vertices are placed on a plane and
    connected to nearby neighbors to mimic realistic pathway networks.
    """
    rng = random.Random(seed + num_vertices)
    # Generate points in [0, 1000] x [0, 1000]
    points = [(rng.uniform(0, 1000), rng.uniform(0, 1000)) for _ in range(num_vertices)]
    adjacency: Dict[int, List[Tuple[int, float, int]]] = {i: [] for i in range(num_vertices)}
    edge_id_counter = 1

    # Guarantee connectivity with a randomized spanning tree
    shuffled = list(range(num_vertices))
    rng.shuffle(shuffled)
    for i in range(1, num_vertices):
        u = shuffled[i]
        # connect to an already connected vertex (preferably close)
        v = shuffled[rng.randint(0, i - 1)]
        dx = points[u][0] - points[v][0]
        dy = points[u][1] - points[v][1]
        dist = max(10.0, round(math.hypot(dx, dy), 1))
        adjacency[u].append((v, dist, edge_id_counter))
        adjacency[v].append((u, dist, edge_id_counter + 1))
        edge_id_counter += 2

    # Add extra random edges to achieve requested average degree
    target_edges = (num_vertices * avg_degree) // 2
    current_edges = num_vertices - 1
    existing_pairs = {
        (min(u, v), max(u, v))
        for u in adjacency
        for v, _, _ in adjacency[u]
    }

    attempts = 0
    max_attempts = num_vertices * 10
    while current_edges < target_edges and attempts < max_attempts:
        attempts += 1
        u = rng.randint(0, num_vertices - 1)
        v = rng.randint(0, num_vertices - 1)
        if u == v:
            continue
        pair = (min(u, v), max(u, v))
        if pair in existing_pairs:
            continue
        existing_pairs.add(pair)
        dx = points[u][0] - points[v][0]
        dy = points[u][1] - points[v][1]
        dist = max(10.0, round(math.hypot(dx, dy), 1))
        adjacency[u].append((v, dist, edge_id_counter))
        adjacency[v].append((u, dist, edge_id_counter + 1))
        edge_id_counter += 2
        current_edges += 1

    return adjacency


def run_synthetic_dijkstra(
    adjacency: Dict[int, List[Tuple[int, float, int]]],
    source: int,
    destination: int,
    use_heapq: bool = False,
) -> Tuple[float, float, int, int, int]:
    """Execute in-memory Dijkstra on synthetic adjacency list.

    Returns:
        (total_distance, elapsed_ms, nodes_visited, edges_examined, relaxations)
    """
    import heapq

    start = time.perf_counter()
    distances: Dict[int, float] = {source: 0.0}
    visited: set = set()
    nodes_visited = 0
    edges_examined = 0
    relaxations = 0

    if use_heapq:
        heap = [(0.0, source)]
        while heap:
            curr_dist, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.add(u)
            nodes_visited += 1
            if u == destination:
                break
            if curr_dist > distances.get(u, float("inf")):
                continue
            for v, weight, _ in adjacency.get(u, []):
                edges_examined += 1
                nd = curr_dist + weight
                if nd < distances.get(v, float("inf")):
                    distances[v] = nd
                    heapq.heappush(heap, (nd, v))
                    relaxations += 1
    else:
        pq = BinaryMinHeap()
        pq.push(0.0, source)
        while not pq.is_empty():
            curr_dist, u, _ = pq.pop()
            if u in visited:
                continue
            visited.add(u)
            nodes_visited += 1
            if u == destination:
                break
            if curr_dist > distances.get(u, float("inf")):
                continue
            for v, weight, _ in adjacency.get(u, []):
                edges_examined += 1
                nd = curr_dist + weight
                if nd < distances.get(v, float("inf")):
                    distances[v] = nd
                    pq.push(nd, v)
                    relaxations += 1

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return distances.get(destination, float("inf")), elapsed_ms, nodes_visited, edges_examined, relaxations


def benchmark_active_campus_graph(iterations: int = 30) -> Dict[str, Any]:
    """Benchmark routing performance on the actual database-backed campus graph."""
    locations = list(Location.objects.all())
    edges = list(Edge.objects.all())

    v = len(locations)
    e = len(edges) // 2
    if v < 2:
        return {
            "error": "Insufficient campus locations in database. Please import map data.",
            "vertices": v,
            "edges": e,
        }

    max_edges = (v * (v - 1)) / 2 if v > 1 else 1
    density = round(e / max_edges, 4)

    # Sample source-destination pairs
    rng = random.Random(101)
    pairs = []
    loc_ids = [loc.id for loc in locations]
    while len(pairs) < min(15, v * (v - 1)):
        src, dst = rng.sample(loc_ids, 2)
        if (src, dst) not in pairs:
            pairs.append((src, dst))

    latencies_custom: List[float] = []
    latencies_heapq: List[float] = []
    visited_counts: List[int] = []
    relax_counts: List[int] = []
    successful_routes = 0

    adjacency = build_adjacency()

    for src, dst in pairs:
        for _ in range(iterations // len(pairs) or 1):
            try:
                res_custom = dijkstra(src, dst, adjacency=adjacency, use_reference_heapq=False)
                res_heapq = dijkstra(src, dst, adjacency=adjacency, use_reference_heapq=True)
                latencies_custom.append(res_custom.metrics.execution_time_ms)
                latencies_heapq.append(res_heapq.metrics.execution_time_ms)
                visited_counts.append(res_custom.metrics.nodes_visited)
                relax_counts.append(res_custom.metrics.relaxations)
                successful_routes += 1
            except NoPathException:
                pass

    # Dynamic rerouting benchmark
    reroute_latencies: List[float] = []
    if pairs and edges:
        test_edge = edges[0]
        # Benchmark with edge dynamically blocked
        for src, dst in pairs[:5]:
            try:
                t0 = time.perf_counter()
                dijkstra(src, dst, blocked_edge_ids=[test_edge.id])
                reroute_latencies.append((time.perf_counter() - t0) * 1000.0)
            except NoPathException:
                pass

    return {
        "graph_type": "Production Campus Database",
        "vertices": v,
        "edges": e,
        "directed_edges": len(edges),
        "density": density,
        "tested_pairs": len(pairs),
        "total_queries": len(latencies_custom),
        "success_rate_percent": round(100.0 * successful_routes / max(1, len(latencies_custom)), 1),
        "latency_custom_heap": {
            "min_ms": round(min(latencies_custom) if latencies_custom else 0.0, 3),
            "mean_ms": round(sum(latencies_custom) / max(1, len(latencies_custom)), 3),
            "median_ms": round(_percentile(latencies_custom, 50), 3),
            "p95_ms": round(_percentile(latencies_custom, 95), 3),
            "p99_ms": round(_percentile(latencies_custom, 99), 3),
        },
        "latency_reference_heapq": {
            "min_ms": round(min(latencies_heapq) if latencies_heapq else 0.0, 3),
            "mean_ms": round(sum(latencies_heapq) / max(1, len(latencies_heapq)), 3),
            "median_ms": round(_percentile(latencies_heapq, 50), 3),
            "p95_ms": round(_percentile(latencies_heapq, 95), 3),
        },
        "avg_nodes_visited": round(sum(visited_counts) / max(1, len(visited_counts)), 1),
        "avg_relaxations": round(sum(relax_counts) / max(1, len(relax_counts)), 1),
        "dynamic_rerouting_mean_ms": round(
            sum(reroute_latencies) / max(1, len(reroute_latencies)), 3
        ) if reroute_latencies else None,
    }


def benchmark_scalability_suite(
    sizes: Optional[List[int]] = None,
    trials_per_size: int = 10,
) -> List[Dict[str, Any]]:
    """Run scalability benchmarks across deterministic synthetic graphs.

    Tests sizes: 100, 500, 1,000, 5,000, 10,000 vertices.
    Compares Custom BinaryMinHeap vs Python heapq Reference for correctness & speed.
    """
    if sizes is None:
        sizes = [100, 500, 1000, 5000, 10000]

    results = []

    for n in sizes:
        adj = generate_synthetic_graph(num_vertices=n, avg_degree=4, seed=42)
        edge_count = sum(len(nbrs) for nbrs in adj.values()) // 2
        density = round(edge_count / ((n * (n - 1)) / 2), 6)

        rng = random.Random(n * 7)
        custom_latencies: List[float] = []
        heapq_latencies: List[float] = []
        visited_list: List[int] = []
        relax_list: List[int] = []
        correctness_matches = 0

        # Memory profiling
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        for _ in range(trials_per_size):
            src = rng.randint(0, n - 1)
            dst = rng.randint(0, n - 1)
            while dst == src:
                dst = rng.randint(0, n - 1)

            # Custom BinaryMinHeap
            dist_custom, time_custom, vis, exam, rel = run_synthetic_dijkstra(
                adj, src, dst, use_heapq=False
            )
            # Reference heapq
            dist_heapq, time_heapq, _, _, _ = run_synthetic_dijkstra(
                adj, src, dst, use_heapq=True
            )

            # Verify identical path cost
            if abs(dist_custom - dist_heapq) < 1e-4:
                correctness_matches += 1

            custom_latencies.append(time_custom)
            heapq_latencies.append(time_heapq)
            visited_list.append(vis)
            relax_list.append(rel)

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        mem_diff_kb = sum(
            stat.size_diff for stat in snapshot_after.compare_to(snapshot_before, "filename")
        ) / 1024.0

        results.append({
            "vertices": n,
            "edges": edge_count,
            "density": density,
            "trials": trials_per_size,
            "correctness_rate_percent": round(100.0 * correctness_matches / trials_per_size, 1),
            "custom_heap": {
                "mean_ms": round(sum(custom_latencies) / trials_per_size, 3),
                "median_ms": round(_percentile(custom_latencies, 50), 3),
                "p95_ms": round(_percentile(custom_latencies, 95), 3),
                "min_ms": round(min(custom_latencies), 3),
                "max_ms": round(max(custom_latencies), 3),
            },
            "reference_heapq": {
                "mean_ms": round(sum(heapq_latencies) / trials_per_size, 3),
                "median_ms": round(_percentile(heapq_latencies, 50), 3),
                "p95_ms": round(_percentile(heapq_latencies, 95), 3),
                "min_ms": round(min(heapq_latencies), 3),
                "max_ms": round(max(heapq_latencies), 3),
            },
            "avg_nodes_visited": round(sum(visited_list) / trials_per_size, 1),
            "avg_relaxations": round(sum(relax_list) / trials_per_size, 1),
            "memory_delta_kb": round(max(0.0, mem_diff_kb), 2),
        })

    return results


def run_full_benchmark_suite(
    output_json: Optional[Path] = None,
    output_csv: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute complete benchmarking suite and persist structured JSON and CSV reports."""
    json_path = output_json or JSON_REPORT_PATH
    csv_path = output_csv or CSV_REPORT_PATH
    json_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    system_env = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
    }

    campus_bench = benchmark_active_campus_graph(iterations=30)
    scalability_bench = benchmark_scalability_suite(
        sizes=[100, 500, 1000, 5000, 10000], trials_per_size=10
    )

    report: Dict[str, Any] = {
        "benchmark_suite": "Campus Navigation Dijkstra & Min-Heap Benchmarking Suite",
        "generated_at": timestamp,
        "environment": system_env,
        "methodology": {
            "complexity_guarantee": "O((V + E) log V)",
            "heap_structure": "Custom Array-Backed BinaryMinHeap with Sift-Up/Sift-Down",
            "reference_baseline": "Python Standard Library heapq",
            "scalability_topology": "Deterministic Connected Planar-Geometric Graph (avg degree 4)",
            "timing_mechanism": "time.perf_counter() with microsecond precision",
        },
        "campus_graph_benchmark": campus_bench,
        "scalability_benchmarks": scalability_bench,
    }

    # Save JSON report
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Save CSV report for scalability benchmarks
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Vertices",
            "Edges",
            "Density",
            "Trials",
            "Correctness %",
            "Custom Mean (ms)",
            "Custom Median (ms)",
            "Custom P95 (ms)",
            "Heapq Mean (ms)",
            "Heapq Median (ms)",
            "Heapq P95 (ms)",
            "Avg Nodes Visited",
            "Avg Relaxations",
            "Memory Delta (KB)",
        ])
        for row in scalability_bench:
            writer.writerow([
                row["vertices"],
                row["edges"],
                row["density"],
                row["trials"],
                row["correctness_rate_percent"],
                row["custom_heap"]["mean_ms"],
                row["custom_heap"]["median_ms"],
                row["custom_heap"]["p95_ms"],
                row["reference_heapq"]["mean_ms"],
                row["reference_heapq"]["median_ms"],
                row["reference_heapq"]["p95_ms"],
                row["avg_nodes_visited"],
                row["avg_relaxations"],
                row["memory_delta_kb"],
            ])

    return report


def load_cached_benchmark_results() -> Optional[Dict[str, Any]]:
    """Load pre-generated benchmark results from disk if available."""
    if JSON_REPORT_PATH.exists():
        try:
            with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

