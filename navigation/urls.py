"""URL routes for the navigation app."""
from django.urls import path

from navigation import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/locations/", views.api_locations, name="api_locations"),
    path("api/edges/", views.api_edges, name="api_edges"),
    path("api/campus-graph/", views.api_campus_graph, name="api_campus_graph"),
    path("api/find-path/", views.api_find_path, name="api_find_path"),
    path("api/toggle-block/", views.api_toggle_block, name="api_toggle_block"),
    path("api/visualize/", views.api_visualize, name="api_visualize"),
]
