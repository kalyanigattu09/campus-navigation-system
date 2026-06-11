"""Seed the database with a realistic 17-node, 28-edge campus layout.

Run with: python manage.py seed_campus
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from navigation.models import Edge, Location


# (name, type, lat, lng, map_x, map_y, description)
LOCATIONS_DATA = [
    ("Main Gate", "gate", 28.6139, 77.2090, 0.05, 0.50, "The main entrance of the campus on the east side."),
    ("Admin Block", "building", 28.6145, 77.2080, 0.18, 0.45, "Houses the registrar, accounts and the principal's office."),
    ("Library", "building", 28.6152, 77.2070, 0.32, 0.42, "Three-storey central library with a digital section."),
    ("CS Department", "building", 28.6160, 77.2055, 0.46, 0.38, "Department of Computer Science & Engineering."),
    ("ECE Department", "building", 28.6168, 77.2045, 0.58, 0.34, "Department of Electronics & Communication."),
    ("Mechanical Block", "building", 28.6175, 77.2030, 0.72, 0.30, "Workshops and mechanical engineering labs."),
    ("Auditorium", "landmark", 28.6155, 77.2090, 0.30, 0.62, "1000-seat auditorium used for events and convocation."),
    ("Sports Ground", "facility", 28.6188, 77.2010, 0.88, 0.18, "Cricket, football and athletics track."),
    ("Canteen", "facility", 28.6162, 77.2078, 0.40, 0.55, "Student canteen with indoor and outdoor seating."),
    ("Hostel A", "building", 28.6185, 77.2070, 0.74, 0.58, "Boys' hostel block A."),
    ("Hostel B", "building", 28.6180, 77.2090, 0.66, 0.74, "Girls' hostel block B."),
    ("Medical Center", "facility", 28.6158, 77.2095, 0.26, 0.72, "On-campus clinic and ambulance bay."),
    ("Back Gate", "gate", 28.6195, 77.1995, 0.94, 0.46, "Service and delivery gate on the west side."),
    ("Parking Lot", "facility", 28.6148, 77.2098, 0.18, 0.65, "Two-wheeler and four-wheeler parking."),
    ("Computer Lab 1", "building", 28.6157, 77.2062, 0.42, 0.30, "Undergraduate computing lab, 60 terminals."),
    ("Research Lab", "building", 28.6166, 77.2060, 0.50, 0.46, "Sponsored research labs and project rooms."),
    ("Central Lawn", "landmark", 28.6160, 77.2082, 0.40, 0.50, "Open green space between academic blocks."),
    ("ATM Corner", "facility", 28.6151, 77.2086, 0.28, 0.50, "Bank ATMs and a small stationery shop."),
]


# (source, destination, distance_m, path_name, blocked?)
EDGES_DATA = [
    ("Main Gate", "Admin Block", 120, "Main Drive", False),
    ("Main Gate", "Parking Lot", 80, "Service Lane", False),
    ("Main Gate", "Auditorium", 180, "Front Path", False),
    ("Admin Block", "Library", 140, "Academic Walk", False),
    ("Admin Block", "ATM Corner", 50, "Plaza Path", False),
    ("Library", "CS Department", 130, "Library Lane", False),
    ("Library", "Canteen", 90, "Reading Walk", False),
    ("CS Department", "Computer Lab 1", 60, "CS Annex", False),
    ("CS Department", "Research Lab", 90, "Project Path", False),
    ("Research Lab", "ECE Department", 110, "Research Walk", False),
    ("ECE Department", "Mechanical Block", 160, "East Corridor", False),
    ("Mechanical Block", "Sports Ground", 220, "Sports Road", False),
    ("Sports Ground", "Back Gate", 200, "West Service Road", False),
    ("Back Gate", "Hostel A", 240, "Hostel Road", False),
    ("Hostel A", "Hostel B", 90, "Hostel Link", False),
    ("Hostel B", "Medical Center", 160, "Hostel Walk", False),
    ("Medical Center", "Auditorium", 200, "Service Lane", False),
    ("Auditorium", "Parking Lot", 110, "Front Path", False),
    ("Canteen", "Central Lawn", 60, "Lawn Walk", False),
    ("Central Lawn", "ATM Corner", 90, "Plaza Path", False),
    ("Central Lawn", "CS Department", 120, "Academic Walk", False),
    ("Canteen", "Hostel B", 170, "Hostel Walk", False),
    ("Hostel A", "Canteen", 200, "Service Lane", False),
    ("Research Lab", "Mechanical Block", 230, "Research Link", False),
    ("Auditorium", "Library", 150, "Reading Walk", False),
    ("Back Gate", "Mechanical Block", 150, "Service Road", False),
    ("Medical Center", "Central Lawn", 130, "Lawn Walk", False),
    ("Library", "Research Lab", 170, "Research Walk", False),
]


# Edges we want to mark blocked for the live demo.
DEMO_BLOCKED = {
    ("Library", "Canteen"),
    ("Canteen", "Hostel B"),
    ("Mechanical Block", "Sports Ground"),
    ("Back Gate", "Hostel A"),
}


class Command(BaseCommand):
    help = "Seed the database with a realistic campus layout."

    @transaction.atomic
    def handle(self, *args, **options):
        Edge.objects.all().delete()
        Location.objects.all().delete()

        loc_map: dict[str, Location] = {}
        for name, ltype, lat, lng, x, y, desc in LOCATIONS_DATA:
            loc = Location.objects.create(
                name=name,
                type=ltype,
                latitude=lat,
                longitude=lng,
                map_x=x,
                map_y=y,
                description=desc,
            )
            loc_map[name] = loc

        for src, dst, dist, path_name, _ in EDGES_DATA:
            is_blocked = (src, dst) in DEMO_BLOCKED or (dst, src) in DEMO_BLOCKED
            Edge.objects.create(
                source=loc_map[src],
                destination=loc_map[dst],
                distance=dist,
                path_name=path_name,
                is_blocked=is_blocked,
            )
            # Mirror the edge so navigation works in both directions.
            Edge.objects.create(
                source=loc_map[dst],
                destination=loc_map[src],
                distance=dist,
                path_name=path_name,
                is_blocked=is_blocked,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Location.objects.count()} locations and "
                f"{Edge.objects.count()} directed edges."
            )
        )
