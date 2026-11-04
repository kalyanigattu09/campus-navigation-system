"""URL routes for the navigation app."""
from django.urls import path

from navigation import views

urlpatterns = [
    # Pages
    path("", views.home, name="home"),
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("admin-login/", views.admin_login_view, name="admin_login"),
    path("admin-logout/", views.admin_logout_view, name="admin_logout"),

    # REST API — Locations
    path("api/locations/", views.api_locations, name="api_locations"),
    path("api/locations/<int:pk>/", views.api_location_detail, name="api_location_detail"),

    # REST API — Edges / Pathways
    path("api/edges/", views.api_edges, name="api_edges"),
    path("api/edges/<int:pk>/", views.api_edge_detail, name="api_edge_detail"),

    # REST API — Graph & Pathfinding
    path("api/campus-graph/", views.api_campus_graph, name="api_campus_graph"),
    path("api/find-path/", views.api_find_path, name="api_find_path"),
    path("api/toggle-block/", views.api_toggle_block, name="api_toggle_block"),
    path("api/visualize/", views.api_visualize, name="api_visualize"),

    # REST API — Campus Maps (Multi-Map Management)
    path("api/maps/", views.api_maps, name="api_maps"),
    path("api/maps/<int:map_id>/", views.api_map_detail, name="api_map_detail"),
    path("api/maps/<int:map_id>/set-active/", views.api_map_set_active, name="api_map_set_active"),
    path("api/maps/<int:map_id>/delete/", views.api_map_delete, name="api_map_delete"),
    path("api/maps/upload-preview/", views.api_map_upload_preview, name="api_map_upload_preview"),
    path("api/maps/upload-confirm/", views.api_map_upload_confirm, name="api_map_upload_confirm"),
    path("api/maps/template/", views.api_map_template, name="api_map_template"),

    # REST API — Analytics & Monitoring
    path("api/recent-activity/", views.api_recent_activity, name="api_recent_activity"),
    path("api/benchmark-results/", views.api_benchmark_results, name="api_benchmark_results"),
    path("api/run-benchmarks/", views.api_run_benchmarks, name="api_run_benchmarks"),
]
