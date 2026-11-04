"""Models for the navigation app: campus maps, locations, pathways, and route audit logs."""
from __future__ import annotations

from typing import Any, Dict, Optional
from django.db import models


class CampusMap(models.Model):
    """Represents a campus map network layout."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(
        default=True, help_text="Designates this map as the active/default campus map"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self) -> str:
        status = " (Active)" if self.is_active else ""
        return f"{self.name}{status}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "total_locations": self.locations.count(),
            "total_pathways": self.edges.count() // 2,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    def get_active_map(cls) -> Optional[CampusMap]:
        """Return the currently active campus map, or the first available map."""
        active = cls.objects.filter(is_active=True).first()
        if not active:
            active = cls.objects.first()
        return active


class Location(models.Model):
    """A point of interest or waypoint on a campus map."""

    LOCATION_TYPES = [
        ("gate", "Gate"),
        ("building", "Building"),
        ("landmark", "Landmark"),
        ("facility", "Facility"),
    ]

    campus_map = models.ForeignKey(
        CampusMap,
        related_name="locations",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=LOCATION_TYPES, default="building")
    latitude = models.FloatField(default=0.0, help_text="Latitude in degrees (for reference)")
    longitude = models.FloatField(default=0.0, help_text="Longitude in degrees (for reference)")
    description = models.TextField(blank=True, default="")

    # Normalized layout coordinates (0.0 to 1.0) for responsive HTML5 Canvas rendering
    map_x = models.FloatField(default=0.5)
    map_y = models.FloatField(default=0.5)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["campus_map", "name"], name="unique_location_per_map"
            )
        ]

    def __str__(self) -> str:
        map_tag = f" [{self.campus_map.name}]" if self.campus_map else ""
        return f"{self.name} ({self.get_type_display()}){map_tag}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert Location instance to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "map_id": self.campus_map_id,
            "name": self.name,
            "type": self.type,
            "lat": self.latitude,
            "lng": self.longitude,
            "x": self.map_x,
            "y": self.map_y,
            "description": self.description,
        }


class Edge(models.Model):
    """A pathway connecting two campus locations on a map."""

    campus_map = models.ForeignKey(
        CampusMap,
        related_name="edges",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    source = models.ForeignKey(
        Location, related_name="outgoing_edges", on_delete=models.CASCADE
    )
    destination = models.ForeignKey(
        Location, related_name="incoming_edges", on_delete=models.CASCADE
    )
    distance = models.FloatField(help_text="Walking distance in meters")
    is_blocked = models.BooleanField(default=False)
    path_name = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["source__name", "destination__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["campus_map", "source", "destination"],
                name="unique_edge_pair_per_map",
            )
        ]

    def __str__(self) -> str:
        status = "BLOCKED" if self.is_blocked else "OPEN"
        return f"{self.source.name} -> {self.destination.name} ({self.distance:.0f}m, {status})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert Edge instance to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "map_id": self.campus_map_id,
            "source": self.source_id,
            "source_name": self.source.name,
            "destination": self.destination_id,
            "destination_name": self.destination.name,
            "distance": self.distance,
            "is_blocked": self.is_blocked,
            "path_name": self.path_name,
        }


class RouteLog(models.Model):
    """Audit log of actual shortest-path calculations."""

    campus_map = models.ForeignKey(
        CampusMap,
        related_name="route_logs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    source = models.ForeignKey(
        Location, related_name="route_logs_origin", on_delete=models.SET_NULL, null=True
    )
    destination = models.ForeignKey(
        Location, related_name="route_logs_target", on_delete=models.SET_NULL, null=True
    )
    distance = models.FloatField(default=0.0)
    travel_time = models.FloatField(default=0.0)
    execution_time_ms = models.FloatField(default=0.0)
    avoid_blocked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        src = self.source.name if self.source else "Unknown"
        dst = self.destination.name if self.destination else "Unknown"
        return f"Route {src} -> {dst} ({self.distance:.0f}m, {self.execution_time_ms:.2f}ms) at {self.created_at}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "map_id": self.campus_map_id,
            "source_name": self.source.name if self.source else "Unknown",
            "destination_name": self.destination.name if self.destination else "Unknown",
            "distance": self.distance,
            "travel_time": self.travel_time,
            "execution_time_ms": self.execution_time_ms,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
