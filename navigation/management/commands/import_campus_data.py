"""Import campus locations and pathways from a verified JSON or CSV file.

Usage:
    python manage.py import_campus_data --file path/to/campus_data.json [--clear]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from navigation.models import Edge, Location


class Command(BaseCommand):
    help = "Import verified campus locations and pathways from a JSON data file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="Path to the JSON data file containing campus locations and edges.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing locations and pathways before importing.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise CommandError(f"Failed to read or parse JSON file: {exc}")

        locations_data: List[Dict[str, Any]] = data.get("locations", [])
        edges_data: List[Dict[str, Any]] = data.get("edges", [])

        if not locations_data:
            raise CommandError("The data file must contain a non-empty 'locations' list.")

        valid_types = {choice[0] for choice in Location.LOCATION_TYPES}

        with transaction.atomic():
            if options.get("clear"):
                Edge.objects.all().delete()
                Location.objects.all().delete()
                self.stdout.write(self.style.WARNING("Cleared existing campus data."))

            loc_map: Dict[str, Location] = {}

            # Import locations
            for loc_info in locations_data:
                name = str(loc_info.get("name", "")).strip()
                if not name:
                    raise CommandError("Each location must have a non-empty 'name'.")

                ltype = loc_info.get("type", "building").lower()
                if ltype not in valid_types:
                    ltype = "building"

                try:
                    lat = float(loc_info.get("latitude", 0.0))
                    lng = float(loc_info.get("longitude", 0.0))
                    map_x = float(loc_info.get("map_x", 0.5))
                    map_y = float(loc_info.get("map_y", 0.5))
                except (ValueError, TypeError) as exc:
                    raise CommandError(f"Invalid coordinates for location '{name}': {exc}")

                # Clamp map_x, map_y to [0.0, 1.0]
                map_x = max(0.0, min(1.0, map_x))
                map_y = max(0.0, min(1.0, map_y))

                desc = str(loc_info.get("description", "")).strip()

                location, _ = Location.objects.update_or_create(
                    name=name,
                    defaults={
                        "type": ltype,
                        "latitude": lat,
                        "longitude": lng,
                        "map_x": map_x,
                        "map_y": map_y,
                        "description": desc,
                    },
                )
                loc_map[name] = location

            # Import edges
            edge_count = 0
            for edge_info in edges_data:
                src_name = str(edge_info.get("source", "")).strip()
                dst_name = str(edge_info.get("destination", "")).strip()
                if src_name not in loc_map or dst_name not in loc_map:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping edge between '{src_name}' and '{dst_name}': node not found."
                        )
                    )
                    continue

                if src_name == dst_name:
                    continue

                try:
                    distance = float(edge_info.get("distance", 0.0))
                except (ValueError, TypeError):
                    raise CommandError(f"Invalid distance for edge '{src_name}' -> '{dst_name}'.")

                if distance <= 0:
                    raise CommandError(f"Distance must be positive for edge '{src_name}' -> '{dst_name}'.")

                path_name = str(edge_info.get("path_name", "")).strip()
                is_blocked = bool(edge_info.get("is_blocked", False))

                src_loc = loc_map[src_name]
                dst_loc = loc_map[dst_name]

                # Create forward edge
                Edge.objects.update_or_create(
                    source=src_loc,
                    destination=dst_loc,
                    defaults={
                        "distance": distance,
                        "path_name": path_name,
                        "is_blocked": is_blocked,
                    },
                )
                # Create reverse edge for bidirectional pathway
                Edge.objects.update_or_create(
                    source=dst_loc,
                    destination=src_loc,
                    defaults={
                        "distance": distance,
                        "path_name": path_name,
                        "is_blocked": is_blocked,
                    },
                )
                edge_count += 2

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully imported {len(loc_map)} locations and {edge_count} directed edges ({edge_count // 2} pathways)."
                )
            )

