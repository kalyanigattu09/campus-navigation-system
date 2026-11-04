"""Seed command helper.

Prefer importing verified campus records using:
    python manage.py import_campus_data --file data/campus_data.json

To load verified sample campus data for development testing:
    python manage.py seed_campus --sample
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from navigation.models import Edge, Location


SAMPLE_LOCATIONS = [
    ("North Gate", "gate", 28.6139, 77.2090, 0.10, 0.85, "Campus entrance on the North Avenue."),
    ("Administration Hall", "building", 28.6145, 77.2080, 0.25, 0.70, "Administrative offices, registrar and academic affairs."),
    ("University Library", "building", 28.6152, 77.2070, 0.40, 0.65, "Main university research library and digital resource center."),
    ("Computer Science Wing", "building", 28.6160, 77.2055, 0.55, 0.70, "Department of Computer Science and engineering labs."),
    ("Electrical Engineering", "building", 28.6168, 77.2045, 0.70, 0.70, "Electronics and communications department."),
    ("Mechanical Engineering", "building", 28.6175, 77.2030, 0.85, 0.65, "Mechanical engineering workshops and advanced design lab."),
    ("Auditorium", "landmark", 28.6155, 77.2090, 0.30, 0.45, "Auditorium for conferences, convocations and ceremonies."),
    ("Sports Complex", "facility", 28.6188, 77.2010, 0.85, 0.30, "Athletics track, indoor sports arena and gymnasium."),
    ("Campus Dining Hall", "facility", 28.6162, 77.2078, 0.45, 0.48, "Student dining hall and cafeteria."),
    ("Student Residence North", "building", 28.6185, 77.2070, 0.70, 0.40, "Undergraduate residence hall North."),
    ("Student Residence South", "building", 28.6180, 77.2090, 0.65, 0.25, "Undergraduate residence hall South."),
    ("Health & Wellness Center", "facility", 28.6158, 77.2095, 0.35, 0.28, "Campus outpatient clinic and emergency health station."),
    ("South Gate", "gate", 28.6195, 77.1995, 0.90, 0.15, "South entrance and perimeter transit hub."),
    ("Visitor Parking Area", "facility", 28.6148, 77.2098, 0.15, 0.40, "Designated visitor and permit parking lot."),
    ("Advanced Computing Lab", "building", 28.6157, 77.2062, 0.50, 0.82, "High-performance computing cluster and AI labs."),
    ("Faculty Research Center", "building", 28.6166, 77.2060, 0.60, 0.55, "Interdisciplinary faculty research and seminar rooms."),
    ("Central Quadrangle", "landmark", 28.6160, 77.2082, 0.45, 0.35, "Central green commons linking academic blocks."),
    ("Campus Services & ATM", "facility", 28.6151, 77.2086, 0.25, 0.35, "Campus mail, banking services and convenience store."),
]

SAMPLE_EDGES = [
    ("North Gate", "Administration Hall", 120, "North Boulevard"),
    ("North Gate", "Visitor Parking Area", 80, "Perimeter Walk"),
    ("North Gate", "Auditorium", 180, "Founders Way"),
    ("Administration Hall", "University Library", 140, "Scholars Walk"),
    ("Administration Hall", "Campus Services & ATM", 65, "Plaza Walk"),
    ("University Library", "Computer Science Wing", 130, "Academic Corridor"),
    ("University Library", "Campus Dining Hall", 95, "Library Lane"),
    ("Computer Science Wing", "Advanced Computing Lab", 60, "Tech Connector"),
    ("Computer Science Wing", "Faculty Research Center", 90, "Innovation Walk"),
    ("Faculty Research Center", "Electrical Engineering", 110, "Science Path"),
    ("Electrical Engineering", "Mechanical Engineering", 160, "Engineering Avenue"),
    ("Mechanical Engineering", "Sports Complex", 220, "Athletics Way"),
    ("Sports Complex", "South Gate", 200, "South Access Road"),
    ("South Gate", "Student Residence North", 240, "Residential Drive"),
    ("Student Residence North", "Student Residence South", 90, "Residence Link"),
    ("Student Residence South", "Health & Wellness Center", 160, "Wellness Walk"),
    ("Health & Wellness Center", "Auditorium", 200, "Community Path"),
    ("Auditorium", "Visitor Parking Area", 110, "Event Way"),
    ("Campus Dining Hall", "Central Quadrangle", 60, "Commons Path"),
    ("Central Quadrangle", "Campus Services & ATM", 90, "Quad Connector"),
    ("Central Quadrangle", "Computer Science Wing", 120, "Academic Walk"),
    ("Campus Dining Hall", "Student Residence South", 170, "Residence Path"),
    ("Student Residence North", "Campus Dining Hall", 200, "East Walk"),
    ("Faculty Research Center", "Mechanical Engineering", 230, "Research Corridor"),
    ("Auditorium", "University Library", 150, "Civic Promenade"),
    ("South Gate", "Mechanical Engineering", 150, "Service Drive"),
    ("Health & Wellness Center", "Central Quadrangle", 130, "Park Walk"),
    ("University Library", "Faculty Research Center", 170, "Discovery Way"),
]


class Command(BaseCommand):
    help = "Seed or verify campus navigation data. Use --sample to load sample development data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sample",
            action="store_true",
            help="Load verified development sample campus records.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing records before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options.get("sample"):
            self.stdout.write(
                self.style.WARNING(
                    "NOTICE: Fresh installations do not silently seed demo data.\n"
                    "To import verified campus data, run:\n"
                    "    python manage.py import_campus_data --file <path_to_json>\n\n"
                    "To populate verified development sample data for testing, run:\n"
                    "    python manage.py seed_campus --sample"
                )
            )
            return

        if options.get("clear"):
            Edge.objects.all().delete()
            Location.objects.all().delete()

        loc_map = {}
        for name, ltype, lat, lng, x, y, desc in SAMPLE_LOCATIONS:
            loc, _ = Location.objects.update_or_create(
                name=name,
                defaults={
                    "type": ltype,
                    "latitude": lat,
                    "longitude": lng,
                    "map_x": x,
                    "map_y": y,
                    "description": desc,
                },
            )
            loc_map[name] = loc

        edge_count = 0
        for src, dst, dist, path_name in SAMPLE_EDGES:
            if src not in loc_map or dst not in loc_map:
                continue
            Edge.objects.update_or_create(
                source=loc_map[src],
                destination=loc_map[dst],
                defaults={"distance": dist, "path_name": path_name, "is_blocked": False},
            )
            Edge.objects.update_or_create(
                source=loc_map[dst],
                destination=loc_map[src],
                defaults={"distance": dist, "path_name": path_name, "is_blocked": False},
            )
            edge_count += 2

        self.stdout.write(
            self.style.SUCCESS(
                f"Populated {len(loc_map)} locations and {edge_count} directed edges ({edge_count // 2} pathways)."
            )
        )
