"""
Models for the Campus Navigation System.

Defines Location and Edge models representing the campus graph.
"""
from django.db import models


class LocationType(models.TextChoices):
    """Enumeration of location types."""
    BUILDING = 'building', 'Building'
    LANDMARK = 'landmark', 'Landmark'
    GATE = 'gate', 'Gate'


class Location(models.Model):
    """
    Represents a location on campus (building, landmark, or gate).

    Attributes:
        id: Auto-incrementing primary key.
        name: Human-readable name of the location.
        type: Type of location (building, landmark, or gate).
        latitude: Geographic latitude coordinate.
        longitude: Geographic longitude coordinate.
        description: Optional description of the location.
    """
    name = models.CharField(max_length=100, unique=True)
    type = models.CharField(
        max_length=20,
        choices=LocationType.choices,
        default=LocationType.BUILDING
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['type']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.type})"

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'description': self.description,
        }


class Edge(models.Model):
    """
    Represents a path/edge between two locations.

    Attributes:
        source: Starting location (ForeignKey to Location).
        destination: Ending location (ForeignKey to Location).
        distance: Path distance in meters.
        is_blocked: Whether the path is currently blocked.
        path_name: Optional descriptive name for the path.
    """
    source = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='outgoing_edges'
    )
    destination = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='incoming_edges'
    )
    distance = models.FloatField(help_text="Distance in meters")
    is_blocked = models.BooleanField(default=False)
    path_name = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        ordering = ['source__name', 'destination__name']
        indexes = [
            models.Index(fields=['source', 'destination']),
            models.Index(fields=['is_blocked']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'destination'],
                name='unique_edge_per_pair'
            )
        ]

    def __str__(self):
        status = "BLOCKED" if self.is_blocked else "OPEN"
        return f"{self.source.name} → {self.destination.name} ({self.distance}m) [{status}]"

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'source_id': self.source_id,
            'source_name': self.source.name,
            'destination_id': self.destination_id,
            'destination_name': self.destination.name,
            'distance': self.distance,
            'is_blocked': self.is_blocked,
            'path_name': self.path_name,
        }