"""URL configuration for the campus_nav project."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("navigation.urls")),
]
