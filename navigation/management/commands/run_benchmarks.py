"""Management command to execute the Dijkstra and graph benchmark suite.

Usage:
    python manage.py run_benchmarks
    python manage.py run_benchmarks --quick
"""
from __future__ import annotations

from pathlib import Path
from django.core.management.base import BaseCommand

from navigation.benchmark import (
    CSV_REPORT_PATH,
    JSON_REPORT_PATH,
    run_full_benchmark_suite,
)


class Command(BaseCommand):
    help = "Run the quantitative Dijkstra algorithm and campus graph benchmarking suite."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quick",
            action="store_true",
            help="Run a faster benchmark suite with smaller graph limits.",
        )
        parser.add_argument(
            "--trials",
            type=int,
            default=10,
            help="Number of trials per graph size (default: 10).",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing Campus Navigation Benchmarking Suite..."))
        self.stdout.write("Measuring active database graph and synthetic scalability graphs...")

        sizes = [100, 500, 1000] if options["quick"] else [100, 500, 1000, 5000, 10000]

        report = run_full_benchmark_suite()

        self.stdout.write(self.style.SUCCESS("\n======================================================="))
        self.stdout.write(self.style.SUCCESS("           BENCHMARK EXECUTION COMPLETE                "))
        self.stdout.write(self.style.SUCCESS("=======================================================\n"))

        campus = report.get("campus_graph_benchmark", {})
        if "error" not in campus:
            self.stdout.write(self.style.NOTICE("--- Active Campus Database Graph ---"))
            self.stdout.write(f"Vertices (V):               {campus.get('vertices')}")
            self.stdout.write(f"Undirected Pathways (E):    {campus.get('edges')}")
            self.stdout.write(f"Graph Density:              {campus.get('density')}")
            self.stdout.write(f"Custom Min-Heap Mean:       {campus.get('latency_custom_heap', {}).get('mean_ms')} ms")
            self.stdout.write(f"Custom Min-Heap P95:        {campus.get('latency_custom_heap', {}).get('p95_ms')} ms")
            self.stdout.write(f"Reference heapq Mean:       {campus.get('latency_reference_heapq', {}).get('mean_ms')} ms")
            if campus.get("dynamic_rerouting_mean_ms"):
                self.stdout.write(f"Dynamic Rerouting Latency:  {campus.get('dynamic_rerouting_mean_ms')} ms")

        self.stdout.write(self.style.NOTICE("\n--- Synthetic Scalability Suite (V = 100 to 10,000) ---"))
        self.stdout.write(
            f"{'Vertices':<10} {'Edges':<10} {'Custom Mean':<14} {'Custom P95':<14} {'Heapq Mean':<14} {'Correctness'}"
        )
        self.stdout.write("-" * 75)
        for row in report.get("scalability_benchmarks", []):
            v = row["vertices"]
            e = row["edges"]
            c_mean = f"{row['custom_heap']['mean_ms']:.3f} ms"
            c_p95 = f"{row['custom_heap']['p95_ms']:.3f} ms"
            h_mean = f"{row['reference_heapq']['mean_ms']:.3f} ms"
            corr = f"{row['correctness_rate_percent']:.1f}%"
            self.stdout.write(f"{v:<10} {e:<10} {c_mean:<14} {c_p95:<14} {h_mean:<14} {corr}")

        self.stdout.write("\nReports saved to:")
        self.stdout.write(f"  JSON: {JSON_REPORT_PATH}")
        self.stdout.write(f"  CSV:  {CSV_REPORT_PATH}\n")

