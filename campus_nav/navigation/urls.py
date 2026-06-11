"""
URL configuration for the navigation app.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('api/locations/', views.api_locations, name='api_locations'),
    path('api/edges/', views.api_edges, name='api_edges'),
    path('api/find-path/', views.FindPathView.as_view(), name='api_find_path'),
    path('api/toggle-block/', views.ToggleBlockView.as_view(), name='api_toggle_block'),
    path('api/campus-graph/', views.api_campus_graph, name='api_campus_graph'),
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/visualize-dijkstra/', views.VisualizeDijkstraView.as_view(), name='api_visualize_dijkstra'),
]