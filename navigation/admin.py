"""Admin site registration for Campus Navigation models."""
from django.contrib import admin

from navigation.models import CampusMap, Edge, Location, RouteLog


@admin.register(CampusMap)
class CampusMapAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "total_locations_display", "total_pathways_display", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")

    def total_locations_display(self, obj):
        return obj.locations.count()
    total_locations_display.short_description = "Locations (V)"

    def total_pathways_display(self, obj):
        return obj.edges.count() // 2
    total_pathways_display.short_description = "Pathways (E)"


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "campus_map", "type", "latitude", "longitude", "map_x", "map_y")
    list_filter = ("campus_map", "type")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "campus_map", "source", "destination", "distance", "path_name", "is_blocked")
    list_filter = ("campus_map", "is_blocked")
    search_fields = ("path_name", "source__name", "destination__name")
    actions = ["mark_blocked", "mark_open"]

    @admin.action(description="Mark selected pathways as BLOCKED")
    def mark_blocked(self, request, queryset):
        queryset.update(is_blocked=True)

    @admin.action(description="Mark selected pathways as OPEN (unblocked)")
    def mark_open(self, request, queryset):
        queryset.update(is_blocked=False)


@admin.register(RouteLog)
class RouteLogAdmin(admin.ModelAdmin):
    list_display = ("__str__", "campus_map", "distance", "travel_time", "execution_time_ms", "avoid_blocked", "created_at")
    list_filter = ("campus_map", "avoid_blocked", "created_at")
