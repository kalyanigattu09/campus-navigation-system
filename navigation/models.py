"""Models for the navigation app: campus locations and the paths between them."""
from django.db import models


class Location(models.Model):
    """A point of interest on campus."""

    LOCATION_TYPES = [
        ("gate", "Gate"),
        ("building", "Building"),
        ("landmark", "Landmark"),
        ("facility", "Facility"),
    ]

    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=LOCATION_TYPES, default="building")
    latitude = models.FloatField(help_text="Latitude in degrees (for reference)")
    longitude = models.FloatField(help_text="Longitude in degrees (for reference)")
    description = models.TextField(blank=True, default="")

    # Synthetic coordinates (0..1) used by the canvas to lay the campus out
    # as a graph. We keep lat/lng for real-world fidelity while these
    # normalised coords keep the renderer responsive at any scale.
    map_x = models.FloatField(default=0.0)
    map_y = models.FloatField(default=0.0)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_type_display()})"


class Edge(models.Model):
    """A bidirectional walkway connecting two locations."""

    source = models.ForeignKey(
        Location, related_name="outgoing_edges", on_delete=models.CASCADE
    )
    destination = models.ForeignKey(
        Location, related_name="incoming_edges", on_delete=models.CASCADE
    )
    distance = models.FloatField(help_text="Distance in meters")
    is_blocked = models.BooleanField(default=False)
    path_name = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["source__name", "destination__name"]
        # Prevent duplicate directed edges between the same pair.
        constraints = [
            models.UniqueConstraint(
                fields=["source", "destination"], name="unique_edge_pair"
            )
        ]

    def __str__(self) -> str:
        status = "BLOCKED" if self.is_blocked else "OPEN"
        return f"{self.source} to {self.destination} ({self.distance:.0f}m, {status})"
